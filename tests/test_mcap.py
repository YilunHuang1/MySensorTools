"""Synthetic file-format tests; fixtures contain no production schemas or data."""
import struct
from pathlib import Path

import flatbuffers
import pytest
from mcap.writer import Writer

from sensor_tools.flatbuffer import Schema, DecodeError
from sensor_tools.mcap import iter_records, imu_fields, log_entries, topic_matches, uwb_fields, Record


def offset_vector(b, offsets):
    b.StartVector(4, len(offsets), 4)
    for offset in reversed(offsets):
        b.PrependUOffsetTRelative(offset)
    return b.EndVector()


def field(b, name, base, slot, *, element=0, index=-1, default=0, optional=False):
    name = b.CreateString(name)
    b.StartObject(6)
    b.PrependInt8Slot(0, base, 0)
    b.PrependInt8Slot(1, element, 0)
    b.PrependInt32Slot(2, index, -1)
    type_ = b.EndObject()
    b.StartObject(14)
    b.PrependUOffsetTRelativeSlot(0, name, 0)
    b.PrependUOffsetTRelativeSlot(1, type_, 0)
    b.PrependUint16Slot(2, slot, 0)
    b.PrependUint16Slot(3, 4 + slot * 2, 0)
    b.PrependInt64Slot(4, default, 0)
    b.PrependBoolSlot(11, optional, False)
    return b.EndObject()


def object_(b, name, fields):
    name = b.CreateString(name)
    fields = offset_vector(b, fields)
    b.StartObject(8)
    b.PrependUOffsetTRelativeSlot(0, name, 0)
    b.PrependUOffsetTRelativeSlot(1, fields, 0)
    return b.EndObject()


def schema_bytes():
    b = flatbuffers.Builder(512)
    child = object_(b, 'example.Child', [field(b, 'value', 12, 0)])
    sample = object_(b, 'example.Sample', [field(b, 'number', 8, 0, default=7),
        field(b, 'label', 13, 1), field(b, 'data', 14, 2, element=4),
        field(b, 'child', 15, 3, index=0), field(b, 'optional', 7, 4, optional=True),
        field(b, 'enabled', 2, 5)])
    objects = offset_vector(b, [child, sample])
    enums = offset_vector(b, [])
    b.StartObject(8)
    b.PrependUOffsetTRelativeSlot(0, objects, 0)
    b.PrependUOffsetTRelativeSlot(1, enums, 0)
    b.PrependUOffsetTRelativeSlot(4, sample, 0)
    b.Finish(b.EndObject(), file_identifier=b'BFBS')
    return bytes(b.Output())


def payload():
    b = flatbuffers.Builder(128)
    label = b.CreateString('hello sensor')
    data = b.CreateByteVector(bytes([0, 128, 255]))
    b.StartObject(1)
    b.PrependFloat64Slot(0, 1.25, 0)
    child = b.EndObject()
    b.StartObject(6)
    b.PrependUint32Slot(0, 42, 7)
    b.PrependUOffsetTRelativeSlot(1, label, 0)
    b.PrependUOffsetTRelativeSlot(2, data, 0)
    b.PrependUOffsetTRelativeSlot(3, child, 0)
    b.PrependBoolSlot(5, True, False)
    b.Finish(b.EndObject())
    return bytes(b.Output())


def write_flat_mcap(path, topic='aorta/default/pub/example', *, groups=None):
    with path.open('wb') as stream:
        w = Writer(stream)
        w.start()
        sid = w.register_schema(name='example.Sample', encoding='flatbuffer', data=schema_bytes())
        for name in groups or [topic]:
            cid = w.register_channel(topic=name, message_encoding='flatbuffer', schema_id=sid)
            w.add_message(cid, log_time=200, publish_time=100, data=payload())
        w.finish()


def test_bfbs_reader():
    assert Schema(schema_bytes()).decode(payload()) == {
        'number': 42, 'label': 'hello sensor', 'data': bytes([0, 128, 255]),
        'child': {'value': 1.25}, 'optional': None, 'enabled': True}


def test_defaults():
    b = flatbuffers.Builder(32)
    b.StartObject(6)
    b.Finish(b.EndObject())
    assert Schema(schema_bytes()).decode(bytes(b.Output())) == {
        'number': 7, 'label': '', 'data': [], 'child': None, 'optional': None, 'enabled': False}


@pytest.mark.parametrize('length', [0, 3, 8, 20, 40])
def test_truncated_payload_rejected(length):
    with pytest.raises(DecodeError):
        Schema(schema_bytes()).decode(payload()[:length])


def test_schema_required():
    with pytest.raises(DecodeError, match='BFBS'):
        Schema(b'not a binary schema')


def test_mcap_timestamps_and_selection(tmp_path):
    path = tmp_path / 'sample.mcap'
    write_flat_mcap(path)
    records = list(iter_records(path, ['/example']))
    assert len(records) == 1
    assert (records[0].log_time_ns, records[0].publish_time_ns) == (200, 100)
    assert list(iter_records(path, ['missing'])) == []
    assert list(iter_records(path, ['example'], start_time_ns=201)) == []
    assert len(list(iter_records(path, ['example'], end_time_ns=201))) == 1


def test_groups_must_be_explicit(tmp_path):
    path = tmp_path / 'groups.mcap'
    write_flat_mcap(path, groups=['aorta/one/pub/example', 'aorta/two/pub/example'])
    with pytest.raises(ValueError, match='ambiguous'):
        list(iter_records(path, ['example']))
    assert len(list(iter_records(path, ['aorta/one/pub/example']))) == 1


@pytest.mark.parametrize('recorded', ['/uwb/data', 'uwb/ranging', 'aorta/default/pub/uwb/ranging'])
def test_uwb_alias(recorded):
    assert topic_matches(recorded, '/uwb/data')


def test_uwb_missing_fields_are_not_fabricated():
    r = Record('uwb/ranging', 'example.Ranging', 'flatbuffer', 300, 200,
               dict(distance=2., angle=-2., pitch=3., distance_filtered=1.9, angle_filtered=-1.))
    data = uwb_fields(r)
    assert data['has_living_body'] is None
    assert data['sync_cnt'] is None
    assert data['timestamp_ns'] == 200
    assert data['log_time_ns'] == 300


def test_imu_timestamp_and_units_preserved():
    r = Record('imu_raw', 'example.Imu', 'flatbuffer', 300, 200,
               dict(timestamp={'sec': 0, 'nsec': 100}, frame_id='body',
                    angular_velocity={'x': 180, 'y': 0, 'z': 0},
                    linear_acceleration={'x': 0, 'y': 0, 'z': 1}))
    assert imu_fields(r) == (100, 'body', (180., 0., 0.), (0., 0., 1.))


def test_log_levels():
    r = Record('x5/vlog', 'foxglove.Log', 'flatbuffer', 300, 200,
               dict(timestamp={'sec': 0, 'nsec': 100}, level=2, name='sensor', message='ready'))
    assert list(log_entries(r)) == [(100, 20, 'sensor', 'ready', '', '', 0)]


ROS_LOG_SCHEMA = '''builtin_interfaces/Time stamp
uint8 level
string name
string msg
string file
string function
uint32 line
================================================================================
MSG: builtin_interfaces/Time
int32 sec
uint32 nanosec
'''


def cdr_log():
    data = bytearray(b'\x00\x01\x00\x00' + struct.pack('<iIB', 1, 234, 20))
    for value in ['sensor', 'ready', 'test.py', 'main']:
        data.extend(b'\0' * (-(len(data) - 4) % 4))
        encoded = value.encode() + b'\0'
        data.extend(struct.pack('<I', len(encoded)) + encoded)
    data.extend(b'\0' * (-(len(data) - 4) % 4))
    data.extend(struct.pack('<I', 9))
    return bytes(data)


def test_ros_cdr_log(tmp_path):
    p = tmp_path / 'ros.mcap'
    with p.open('wb') as stream:
        w = Writer(stream)
        w.start()
        s = w.register_schema(name='rcl_interfaces/msg/Log', encoding='ros2msg', data=ROS_LOG_SCHEMA.encode())
        c = w.register_channel('/x5/vlog', 'cdr', s)
        w.add_message(c, log_time=2_000_000_000, publish_time=1_000_000_234, data=cdr_log())
        w.finish()
    r = next(iter_records(p, ['x5/vlog']))
    assert list(log_entries(r)) == [(1_000_000_234, 20, 'sensor', 'ready', 'test.py', 'main', 9)]
