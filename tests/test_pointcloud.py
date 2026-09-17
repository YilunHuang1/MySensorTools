import struct
import pytest
from sensor_tools.pointcloud import statistics


def test_ros_row_padding_big_endian_and_nan():
    message = dict(width=1, height=2, point_step=12, row_step=16, is_bigendian=True,
                   fields=[dict(name=n, offset=i*4, datatype=7, count=1) for i,n in enumerate(['x','y','z'])],
                   data=struct.pack('>fffIfffI',3,4,0,999,float('nan'),0,0,888))
    result=statistics(message)
    assert result['valid_points'] == 1
    assert result['nan_points'] == 1
    assert result['mean_distance'] == 5


def test_foxglove_unaligned_double_timestamp():
    fields = [dict(name=n, offset=i*4, type=7) for i,n in enumerate(['x','y','z','intensity'])]
    fields += [dict(name='ring', offset=16, type=3), dict(name='timestamp', offset=18, type=8)]
    message = dict(point_stride=26, fields=fields,
                   data=struct.pack('<ffffHd',1,2,2,30,15,100.2) + struct.pack('<ffffHd',0,0,0,0,0,100.1))
    result=statistics(message)
    assert result['valid_points'] == result['zero_points'] == 1
    assert result['mean_distance'] == 3
    assert result['last_point_timestamp'] == 100.1
    assert result['within_frame_time_regressions'] == 1
    message['data'] += b'x'
    with pytest.raises(ValueError,match='multiple'):
        statistics(message)


def test_lidar_packet_crosses_transport_boundaries():
    from sensor_tools.lidar import PacketStream
    first = b'\xee\xff\x01\x01\x00\x00' + bytes(74)
    second = b'\xee\xff\x01\x01\x00\x01' + bytes(28)
    stream = PacketStream()
    assert stream.feed(b'partial' + first[:22]) == []
    assert stream.feed(first[22:] + second[:3]) == [('pointcloud', first)]
    assert stream.feed(second[3:]) == [('imu', second)]
    assert not stream.pending
    assert stream.discarded_bytes == 7


def test_nonfinite_timestamp_does_not_shift_first_point_boundary():
    fields = [dict(name=n, offset=i*8, type=8) for i,n in enumerate(['x','y','z','timestamp'])]
    data = struct.pack('<dddddddd',1,2,3,float('nan'),4,5,6,100.)
    with pytest.raises(ValueError, match='boundaries are unknown'):
        statistics(dict(point_stride=32,fields=fields,data=data))
