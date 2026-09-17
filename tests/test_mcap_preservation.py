"""Roundtrip messages, empty channels, metadata and attachments through both tools."""
import importlib.util
import json
from pathlib import Path
import struct
import sys

from mcap.reader import make_reader
from mcap.writer import Writer
import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def snapshot(path):
    with path.open('rb') as stream:
        reader = make_reader(stream)
        summary = reader.get_summary()
        channels = {c.topic: (c.message_encoding, c.metadata, summary.schemas[c.schema_id].data) for c in summary.channels.values()}
        messages = [(c.topic, m.log_time, m.publish_time, m.sequence, m.data) for _, c, m in reader.iter_messages(log_time_order=False)]
        metadata = [(m.name, m.metadata) for m in reader.iter_metadata()]
        attachments = [(a.name, a.create_time, a.log_time, a.media_type, a.data) for a in reader.iter_attachments()]
    return channels, messages, metadata, attachments


def fixture(path, lidar, collision=None):
    packets = bytearray()
    for angle in [35900, 0, 60]:
        packet = bytearray(80)
        packet[:2] = b'\xee\xff'
        struct.pack_into('<H', packet, 16, angle)
        for channel in range(16):
            struct.pack_into('<HB', packet, 18 + channel * 3, 1000, 30)
        struct.pack_into('<I', packet, 76, lidar.crc32mpeg2(packet, 76))
        packets.extend(packet)
    with path.open('wb') as stream:
        writer = Writer(stream); writer.start()
        sid = writer.register_schema('example.Ranging', 'jsonschema', b'{"type":"object"}')
        uwb = writer.register_channel('/uwb/data', 'json', sid, metadata={'source': 'synthetic'})
        raw = writer.register_channel('/lidar_packets', 'json', sid)
        writer.register_channel(collision or '/empty', 'json', sid, metadata={'empty': 'true'})
        for index in range(4):
            body = dict(distance=1., distance_filtered=float(index*index), angle=float(index), angle_filtered=float(index), pitch=0.)
            # Physical order differs from log-time order, but source time increases.
            writer.add_message(uwb, 10-index, json.dumps(body).encode(), (index+1)*1_000_000_000, index)
        writer.add_message(raw, 20, json.dumps({'data': list(packets)}).encode(), 20)
        writer.add_metadata('test', {'source': 'synthetic'})
        writer.add_attachment(1, 2, 'note.txt', 'text/plain', b'fixture attachment')
        writer.finish()


@pytest.mark.parametrize('kind', ['uwb', 'lidar'])
def test_converter_preserves_every_original_record(tmp_path, monkeypatch, kind):
    lidar = module('lidar_preservation', 'lidar/packets_parse/foxglove/mcap_add_lidar_points.py')
    source, output = tmp_path/'input.mcap', tmp_path/'output.mcap'
    fixture(source, lidar)
    if kind == 'uwb':
        uwb = module('uwb_preservation', 'uwb/rosbag_tools/uwb.py')
        assert uwb.process(source, output) == (5, 6)
    else:
        monkeypatch.setattr(sys, 'argv', ['converter', str(source), str(output)])
        lidar.main()
    before, after = snapshot(source), snapshot(output)
    assert all(after[0][topic] == info for topic, info in before[0].items())
    assert [row for row in after[1] if row[0] in before[0]] == before[1]
    assert after[2:] == before[2:]


def test_empty_derived_channel_collision_is_rejected(tmp_path):
    lidar = module('lidar_collision', 'lidar/packets_parse/foxglove/mcap_add_lidar_points.py')
    uwb = module('uwb_collision', 'uwb/rosbag_tools/uwb.py')
    source, output = tmp_path/'input.mcap', tmp_path/'output.mcap'
    fixture(source, lidar, collision='/uwb/derived/dist_accel')
    with pytest.raises(ValueError, match='already exists'):
        uwb.process(source, output)
    assert not output.exists()
