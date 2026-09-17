import importlib.util
from pathlib import Path
import struct
import sys

import numpy as np
import pytest

from sensor_tools.images import image_array
from sensor_tools.lidar import ResolutionTracker
from sensor_tools.pcd import read_pcd, xyzi

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_mono_padding():
    image = image_array(bytes([1, 2, 99, 3, 4, 99]), 2, 2, 'mono8', step=3)
    np.testing.assert_array_equal(image, [[1, 2], [3, 4]])


@pytest.mark.parametrize('data,width,height,encoding,step', [
    (b'123', 2, 2, 'mono8', None), (b'12345', 2, 2, 'mono8', None),
    (b'1234', 2, 2, 'mono8', 1), (b'1234', 0, 2, 'mono8', None),
    (b'1234', 1, 2, 'yuyv', None), (b'1234', 2, 1, 'nv12', None),
    (b'1234', 2, 2, 'unknown', None)])
def test_invalid_images(data, width, height, encoding, step):
    with pytest.raises(ValueError):
        image_array(data, width, height, encoding, step)


def test_yuyv_and_nv12():
    image = image_array(bytes([128, 128, 128, 128]), 2, 1, 'yuyv')
    assert image.shape == (1, 2, 3)
    assert int(image[0, 0, 0]) == int(image[0, 0, 1]) == int(image[0, 0, 2])
    image = image_array(bytes([128] * 6), 2, 2, 'nv12')
    assert image.shape == (2, 2, 3)


def test_pcd_float64_with_timestamp(tmp_path):
    p = tmp_path / 'five.pcd'
    header = b'VERSION 0.7\nFIELDS x y z intensity timestamp\nSIZE 8 8 8 8 8\nTYPE F F F F F\nCOUNT 1 1 1 1 1\nWIDTH 2\nHEIGHT 1\nPOINTS 2\nDATA binary\n'
    values = np.array([[1., 2., 3., 4., 1789617750.123456], [5., 6., 7., 8., 1789617750.123478]], '<f8')
    p.write_bytes(header + values.tobytes())
    read = read_pcd(p)
    np.testing.assert_array_equal(read['timestamp'], values[:, 4])
    np.testing.assert_array_equal(xyzi(p), values[:, :4])
    p.write_bytes(header + values.tobytes()[:-1])
    with pytest.raises(ValueError, match='byte count'):
        read_pcd(p)


def test_ascii_pcd_field_order(tmp_path):
    p = tmp_path / 'reordered.pcd'
    p.write_text('FIELDS intensity z y x\nSIZE 4 4 4 4\nTYPE F F F F\nWIDTH 1\nHEIGHT 1\nPOINTS 1\nDATA ascii\n4 3 2 1\n')
    np.testing.assert_array_equal(xyzi(p), [[1, 2, 3, 4]])


def test_pcd_missing_header_terminates(tmp_path):
    p = tmp_path / 'broken.pcd'
    p.write_text('VERSION 0.7\n')
    with pytest.raises(ValueError, match='header'):
        read_pcd(p)


def test_resolution_lock_and_change():
    tracker = ResolutionTracker()
    for _ in range(299):
        assert tracker.update(60) == 60
    assert tracker.locked is None
    assert tracker.update(60) == 60
    for _ in range(299):
        assert tracker.update(120) == 60
    assert tracker.update(120) == 120
    assert tracker.update(60) == 120
    assert tracker.update(120) == 120


def test_angular_acceleration_wrap_and_duplicates():
    module = load('uwb_derived_test', 'uwb/rosbag_tools/uwb.py')
    calc = module.Derivative(circular=True)
    assert calc.update(359., 0) is None
    assert calc.update(1., 1_000_000_000) is None
    assert calc.update(100., 1_000_000_000) is None
    assert calc.update(3., 2_000_000_000) == 0.
    distance = module.Derivative()
    assert distance.update(0., 0) is None
    assert distance.update(1., 1_000_000_000) is None
    assert distance.update(9., 3_000_000_000) == 2.


def test_imu_registered_units_do_not_change_data():
    module = load('imu_analyzer_test', 'imu/mcap_analysis/analyze_imu_mcap.py')
    sample = module.ImuSample('imu_raw', 2, 1, 'body', (0., 0., 1.), (180., 0., 0.))
    assert sample.acc_norm == 1.


def test_lidar_partial_channel_timestamp():
    module = load('lidar_timing_test', 'lidar/packets_parse/extract_lidar_pcd_with_ts.py')
    module.init_trig_tables()
    data = bytearray(80)
    data[0:2] = b'\xee\xff'
    data[6:12] = bytes([126, 9, 17, 12, 0, 0])
    struct.pack_into('<I', data, 12, 500_000)
    struct.pack_into('<H', data, 16, 600)
    # The last nonzero channel is 10, so its time is the packet timestamp.
    for channel in range(11):
        struct.pack_into('<HB', data, 18 + channel * 3, 1000, 50)
    struct.pack_into('<I', data, 76, module.crc32_mpeg2_padded(data, 76))
    _, timestamp, points = module.decode_point_cloud_packet_with_ts(bytes(data), [0]*16, [0]*16)
    assert len(points) == 16
    assert points[10].timestamp == timestamp
    assert points[0].timestamp == pytest.approx(timestamp - module.INTRA_BLOCK_OFFSET[10], abs=1e-7)
    assert np.isnan(points[15].x)
    assert module.parse_pkt_lidar_ts(b'') is None
    data[7:9] = bytes([2, 30])
    assert module.parse_pkt_lidar_ts(data) is None


def test_clean_config_false_is_false(tmp_path):
    module = load('uwb_clean_test', 'uwb/mcap_tools/vis_ansys/mcap_to_csv.py')
    p = tmp_path / 'clean.ini'
    p.write_text('[clean]\ndrop_zero_distance=false\nangle_normalize=false\n')
    config = module.load_clean_config(p)
    assert not config.drop_zero_distance and not config.angle_normalize


def test_timestamp_pcd_preserves_regression_order(tmp_path):
    module = load('lidar_pcd_order_test', 'lidar/packets_parse/extract_lidar_pcd_with_ts.py')
    points = [module.PointWithTs(1., 2., 3., 4., 10.), module.PointWithTs(5., 6., 7., 8., 9.)]
    for binary in [False, True]:
        path = tmp_path / f'{binary}.pcd'
        module.save_pcd_with_timestamp(path, points, binary=binary)
        decoded = read_pcd(path)
        np.testing.assert_array_equal(decoded['timestamp'], [10., 9.])
        np.testing.assert_array_equal(decoded['x'], [1., 5.])


def test_sequence_check_excludes_corrupted_counter(monkeypatch, capsys):
    from types import SimpleNamespace
    module = load('lidar_sequence_test', 'lidar/packets_parse/scripts/check_sequence.py')
    packets = []
    for counter in (10, 11, 12):
        packet = bytearray(80)
        packet[:2] = b'\xee\xff'
        struct.pack_into('<H', packet, 74, counter)
        struct.pack_into('<I', packet, 76, module.crc32_mpeg2_padded(packet, 76))
        if counter == 11:
            packet[74] ^= 0xff
        packets.append(SimpleNamespace(data=bytes(packet)))
    monkeypatch.setattr(module, 'iter_packet_messages', lambda *args: iter(packets))
    rows = module.extract_packets('unused.mcap', '/lidar_packets')
    assert [row[2] for row in rows] == [10, 12]
    assert 'CRC-invalid packets excluded: 1' in capsys.readouterr().out
