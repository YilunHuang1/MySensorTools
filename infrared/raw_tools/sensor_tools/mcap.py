"""Schema-aware MCAP iteration; preserve recorded and source timestamps separately."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from mcap.reader import make_reader

from .flatbuffer import DecodeError, Schema


ALIASES = {'uwb/data': 'uwb/ranging', 'x5/vlog_batch': 'x5/vlog', 's100/vlog_batch': 's100/vlog'}


def logical_topic(topic: str) -> str:
    parts = topic.strip('/').split('/')
    if len(parts) >= 4 and parts[0] == 'aorta' and parts[2] == 'pub':
        topic = '/'.join(parts[3:])
    else:
        topic = '/'.join(parts)
    return ALIASES.get(topic, topic)


def topic_matches(recorded: str, requested: str) -> bool:
    if requested.strip('/').startswith('aorta/'):
        return recorded.strip('/') == requested.strip('/')
    return logical_topic(recorded) == logical_topic(requested)


def plain(value):
    """Normalize generated ROS objects without converting large byte arrays to lists."""
    if isinstance(value, (str, int, float, bool, bytes, type(None))):
        return value
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if hasattr(value, 'dtype'):
        return value.tobytes() if str(value.dtype) == 'uint8' else value.tolist()
    if hasattr(value, '__slots__'):
        return {key: plain(getattr(value, key)) for key in value.__slots__ if not key.startswith('_')}
    if hasattr(value, '__dict__'):
        return {key: plain(item) for key, item in vars(value).items() if not key.startswith('_')}
    raise DecodeError(f'unsupported decoded value: {type(value).__name__}')


class Decoder:
    def __init__(self):
        self.schemas = {}
        self.ros = None

    def decode(self, schema, channel, data: bytes):
        encoding = channel.message_encoding.lower()
        if schema is None:
            raise DecodeError(f'{channel.topic}: missing schema')
        if encoding in ('flatbuffer', 'flatbuffers'):
            if schema.encoding.lower() not in ('flatbuffer', 'flatbuffers'):
                raise DecodeError(f'{channel.topic}: incompatible schema encoding {schema.encoding}')
            key = hashlib.sha256(schema.data).digest()
            if key not in self.schemas:
                self.schemas[key] = Schema(schema.data)
            return self.schemas[key].decode(data)
        if encoding == 'cdr':
            if schema.encoding != 'ros2msg':
                raise DecodeError(f'{channel.topic}: CDR requires ros2msg schema')
            if self.ros is None:
                from mcap_ros2.decoder import DecoderFactory
                self.ros = DecoderFactory()
            decoder = self.ros.decoder_for(channel.message_encoding, schema)
            if decoder is None:
                raise DecodeError(f'{channel.topic}: unsupported ROS schema {schema.name}')
            try:
                return plain(decoder(data))
            except Exception as error:
                raise DecodeError(f'{channel.topic}: invalid CDR payload: {error}') from error
        if encoding == 'json':
            try:
                result = json.loads(data)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise DecodeError(f'{channel.topic}: invalid JSON') from error
            if not isinstance(result, dict):
                raise DecodeError('message must be an object')
            return result
        raise DecodeError(f'{channel.topic}: unsupported message encoding {channel.message_encoding}')


@dataclass(frozen=True)
class Record:
    topic: str
    schema_name: str
    encoding: str
    log_time_ns: int
    publish_time_ns: int
    data: dict


def channels(path):
    with Path(path).open('rb') as stream:
        reader = make_reader(stream)
        summary = reader.get_summary()
        if summary is not None:
            return list(summary.channels.values())
        found = {}
        for _, channel, _ in reader.iter_messages(log_time_order=False):
            found[channel.id] = channel
        return list(found.values())


def iter_records(path, topics: Iterable[str] | None = None, start_time_ns=None, end_time_ns=None):
    """Select logical aliases or exact Aorta channels. Reject ambiguous group selection."""
    selected = None
    if topics is not None:
        requested = list(topics)
        available = channels(path)
        selected = []
        for topic in requested:
            matches = [channel.topic for channel in available if topic_matches(channel.topic, topic)]
            groups = {name.strip('/').split('/')[1] for name in matches
                      if name.strip('/').startswith('aorta/')}
            if len(groups) > 1 and not topic.strip('/').startswith('aorta/'):
                raise ValueError(f'ambiguous Aorta groups for {topic}; select a full recorded channel')
            selected.extend(matches)
        if not selected:
            return
    decoder = Decoder()
    with Path(path).open('rb') as stream:
        reader = make_reader(stream)
        for schema, channel, message in reader.iter_messages(
                topics=selected, start_time=start_time_ns, end_time=end_time_ns):
            try:
                payload = decoder.decode(schema, channel, message.data)
            except (ValueError, IndexError, TypeError) as error:
                raise DecodeError(f'{channel.topic} @ {message.log_time}: {error}') from error
            if not isinstance(payload, dict):
                raise DecodeError(f'{channel.topic}: expected message object')
            yield Record(channel.topic, schema.name, channel.message_encoding,
                         message.log_time, message.publish_time, payload)


def stamp_ns(value) -> int | None:
    if not isinstance(value, dict):
        return None
    sec = value.get('sec', value.get('secs'))
    nsec = value.get('nanosec', value.get('nsec', value.get('nsecs')))
    if sec is None or nsec is None:
        return None
    if not 0 <= int(nsec) < 1_000_000_000:
        raise DecodeError('timestamp nanoseconds outside [0, 1e9)')
    return int(sec) * 1_000_000_000 + int(nsec)


def source_time_ns(data: dict, fallback: int | None = None) -> int | None:
    header = data.get('header') or {}
    for value in (header.get('stamp'), data.get('timestamp'), data.get('stamp')):
        result = stamp_ns(value)
        if result is not None:
            return result
    return fallback


def vector3(value):
    if isinstance(value, dict) and all(axis in value for axis in ('x', 'y', 'z')):
        return tuple(float(value[axis]) for axis in ('x', 'y', 'z'))
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(float(item) for item in value)
    raise DecodeError('expected a three-axis vector')


def imu_fields(record: Record):
    data = record.data
    if 'angular_velocity' not in data or 'linear_acceleration' not in data:
        raise DecodeError(f'{record.topic}: {record.schema_name} is not an IMU message')
    timestamp = source_time_ns(data, record.publish_time_ns)
    frame_id = (data.get('header') or {}).get('frame_id', data.get('frame_id', ''))
    return timestamp, frame_id, vector3(data['angular_velocity']), vector3(data['linear_acceleration'])


def log_entries(record: Record):
    data = record.data
    entries = data.get('logs', data.get('entries'))
    if entries is None:
        entries = [data]
    if not isinstance(entries, list):
        raise DecodeError('invalid log batch')
    for item in entries:
        if not isinstance(item, dict) or not ('message' in item or 'msg' in item):
            raise DecodeError(f'{record.topic}: {record.schema_name} is not a supported log message')
        level = item.get('level', 0)
        if record.schema_name in ('foxglove.Log', 'aorta.topic.log.LogBatch'):
            level = int(level) * 10
        yield (source_time_ns(item, source_time_ns(data, record.publish_time_ns)),
               level, item.get('name', ''), item.get('message', item.get('msg', '')),
               item.get('file', ''), item.get('function', ''), item.get('line', 0))


def uwb_fields(record: Record):
    data = record.data
    required = ('distance', 'angle', 'pitch', 'distance_filtered', 'angle_filtered')
    if not all(key in data for key in required):
        raise DecodeError(f'{record.topic}: {record.schema_name} is not a ranging message')
    timestamp = source_time_ns(data, record.publish_time_ns)
    header = data.get('header') or {}
    result = {key: data[key] for key in required}
    rssi = data.get('rssi') or []
    result.update(stamp_sec=timestamp // 1_000_000_000, stamp_nsec=timestamp % 1_000_000_000,
                  timestamp_sec=timestamp / 1e9, timestamp_ns=timestamp,
                  frame_id=header.get('frame_id', data.get('frame_id', '')),
                  rssi=rssi, rssi_len=data.get('rssi_len', len(rssi)),
                  pos_confidence=data.get('pos_confidence'), sync_cnt=data.get('sync_cnt'),
                  has_living_body=data.get('has_living_body'), has_head_touch=data.get('has_head_touch'),
                  source_schema=record.schema_name, source_encoding=record.encoding,
                  log_time_ns=record.log_time_ns, publish_time_ns=record.publish_time_ns)
    return result
