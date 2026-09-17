import binascii
import struct
import sys
from pathlib import Path
import pytest
from sensor_tools.uwb_serial import Framer, packet_tlvs, ranging

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'uwb/ble_tools'))
from PacketParser import PacketParser
from CmdBuilder import CmdBuilder
from SerialHandlerStandalone import RangingStats


def frame(payload):
    return b'\x55\xaa\x00' + struct.pack('<H', len(payload)) + payload + struct.pack('>H', binascii.crc_hqx(payload, 0))


def c5():
    return struct.pack('<IIIHfffBbbbbbbB', 123, 456, 789, 1, 2., -179., 30., 2, -80, -81, -82, -83, -84, -85, 91)


def test_multi_tlv_and_confidence_offset():
    value = c5()
    packet = frame(b'\x00\x00' + bytes([0xc5, len(value)]) + value + bytes([0xc5, len(value)]) + value)
    rows = PacketParser.parse_all(packet)
    assert len(rows) == 2
    assert rows[0]['pos_confidence'] == 91
    assert rows[0]['rssi_np'] == -84
    assert rows[0]['rssi_values'] == (-80, -81)
    with pytest.raises(ValueError,match='CRC'):
        packet_tlvs(packet[:-1] + bytes([packet[-1] ^ 1]))


def test_fragmented_serial_stream_and_bad_packet_recovery():
    packet=frame(b'\x59\x03\x01\x03\x00')
    decoder=Framer()
    assert decoder.feed(b'junk'+packet[:6]) == []
    assert decoder.feed(packet[6:]) == [packet]
    corrupt=packet[:-1]+bytes([packet[-1]^1])
    assert decoder.feed(corrupt + packet) == [packet]
    assert decoder.invalid_frames == 1


def test_truncation_is_not_zero_confidence():
    with pytest.raises(ValueError,match='RSSI vector'):
        ranging(c5()[:28])
    with pytest.raises(ValueError,match='extension'):
        ranging(c5()[:30])
    assert ranging(c5()[:26])['pos_confidence'] is None
    with pytest.raises(ValueError,match='TLV length'):
        packet_tlvs(frame(b'\xc5\xff\x00'))


def test_apple_config_rejects_short_and_unimplemented():
    with pytest.raises(ValueError):
        CmdBuilder.build_apple_fira_cmd(b'\x00')
    with pytest.raises(NotImplementedError):
        CmdBuilder.build_fira_cmd({})
    packet, session = CmdBuilder.build_apple_fira_cmd(bytes(29))
    assert len(packet)==43 and session==bytes(4)
    assert packet_tlvs(packet)[0][0] == 0x24


def test_fps_uses_real_stats_class(monkeypatch):
    times=iter([100.,100.05,100.1])
    monkeypatch.setattr('SerialHandlerStandalone.time.monotonic', lambda:next(times))
    stats=RangingStats()
    for _ in range(3): stats.update(1,0,0)
    assert stats.fps() == pytest.approx(20)


def test_circular_stats_do_not_average_wrap_to_180():
    stats = RangingStats()
    stats.update(1., 359., 0.)
    stats.update(1., 1., 0.)
    assert stats.angle_stats()['avg'] == pytest.approx(0., abs=1e-8)
    assert stats.angle_stats()['std'] == pytest.approx(1., abs=.01)


def test_underreported_c5_firmware_length_and_following_tlv():
    value = struct.pack('<IIIHfff',123,456,789,1,2.,-179.,30.)
    value += bytes([6]) + struct.pack('<10bB',-70,-71,-72,-73,-74,-75,-80,-81,-82,-83,95)
    assert len(value) == 0x26
    encoded = frame(b'\xc5\x22' + value + b'\x59\x03\x01\x03\x00')
    parsed = packet_tlvs(encoded)
    assert [kind for kind,_ in parsed] == [0xc5,0x59]
    assert ranging(parsed[0][1])['pos_confidence'] == 95
    rows = PacketParser.parse_all(encoded)
    assert len(rows) == 1 and rows[0]['rssi_values'] == (-70,-71,-72,-73,-74,-75)
