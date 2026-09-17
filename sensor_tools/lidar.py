"""Transport adapter for raw LiDAR packets; protocol decoding stays in the tools."""
from dataclasses import dataclass
from .mcap import iter_records, source_time_ns
from .flatbuffer import DecodeError


@dataclass(frozen=True)
class PacketMessage:
    data: bytes
    publish_time: int
    log_time: int
    source_time: int
    topic: str


class PacketStream:
    """Reassemble serial hardware packets across MCAP/Aorta message boundaries.

    A transport message is an arbitrary serial read (often 1024 bytes), not a
    hardware packet boundary. A final incomplete packet is retained in pending.
    """
    def __init__(self):
        self.pending = bytearray()
        self.discarded_bytes = 0

    def feed(self, chunk):
        self.pending.extend(chunk)
        output = []
        while len(self.pending) >= 2:
            if self.pending[:2] == b'\xee\xdd':
                kind, length = 'fault', 41
            elif self.pending[:2] == b'\xee\xff':
                if len(self.pending) < 6:
                    break
                dtype = self.pending[5]
                if dtype not in (0, 1):
                    self.discarded_bytes += 1
                    del self.pending[0]
                    continue
                kind, length = ('pointcloud', 80) if dtype == 0 else ('imu', 34)
            else:
                self.discarded_bytes += 1
                del self.pending[0]
                continue
            if len(self.pending) < length:
                break
            output.append((kind, bytes(self.pending[:length])))
            del self.pending[:length]
        return output


def iter_packet_messages(path, topic='/lidar_packets'):
    streams = {}
    for record in iter_records(path, [topic]):
        value = record.data.get('data')
        if not isinstance(value, (bytes, bytearray, list, tuple)):
            raise DecodeError(f'{record.topic}: schema {record.schema_name} has no byte data field')
        try:
            data = bytes(value)
        except (ValueError, TypeError) as error:
            raise DecodeError('invalid LiDAR byte sequence') from error
        if not data:
            raise DecodeError(f'{record.topic}: empty LiDAR packet')
        stream = streams.setdefault(record.topic, PacketStream())
        for _, packet in stream.feed(data):
            yield PacketMessage(packet, record.publish_time_ns, record.log_time_ns,
                                source_time_ns(record.data, record.publish_time_ns), record.topic)


class ResolutionTracker:
    """Require 300 consecutive packets before locking/changing angular resolution."""
    def __init__(self, stable_packets=300):
        if stable_packets < 1:
            raise ValueError('stable_packets must be positive')
        self.threshold = stable_packets
        self.candidate = None
        self.count = 0
        self.locked = None

    def update(self, resolution):
        if resolution not in (60, 120):
            raise ValueError('expected 60 or 120 hundredths of a degree')
        if resolution == self.candidate:
            self.count += 1
        else:
            self.candidate, self.count = resolution, 1
        if self.count >= self.threshold:
            self.locked = resolution
        return self.locked if self.locked is not None else resolution
