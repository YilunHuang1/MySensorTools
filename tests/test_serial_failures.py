"""Serial fault paths are simulated; these tests never open a device."""
import binascii
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'uwb/smoke_test'))
import serial_comm as serial
import checks_standalone as checks
from report import CheckStatus


def packet(payload):
    return b'\x55\xaa\x00' + struct.pack('<H', len(payload)) + payload + struct.pack('>H', binascii.crc_hqx(payload, 0))


def test_bad_crc_and_partial_tlv_cannot_be_valid_response():
    comm = serial.SerialComm('unused')
    good = packet(b'\x00\x02\x24\x00')
    corrupt = good[:-1] + bytes([good[-1] ^ 1])
    malformed = packet(b'\x00\x02\x24')
    comm._buffer.extend(corrupt + malformed + good)
    response = comm._try_parse()
    assert response.crc_ok and response.tlvs == [serial.TLV(0, b'\x24\x00')]
    assert comm.total_packets_received == 3
    assert comm.crc_errors == comm.protocol_errors == 1
    assert checks.check_crc_integrity(comm).status == CheckStatus.FAIL


def test_header_fragment_after_noise_is_retained():
    comm = serial.SerialComm('unused')
    good = packet(b'\x00\x02\x24\x00')
    comm._buffer.extend(b'junkjunk' + good[:1])
    assert comm._try_parse() is None
    comm._buffer.extend(good[1:])
    assert comm._try_parse().tlvs == [serial.TLV(0, b'\x24\x00')]


def test_c5_declared_length_does_not_consume_next_tlv():
    value = bytes(34)
    payload = b'\xc5\x22' + value + b'\x59\x04\x01\x00\x03\x00'
    assert serial.parse_tlvs(payload) == [serial.TLV(0xc5, value), serial.TLV(0x59, b'\x01\x00\x03\x00')]
    with pytest.raises(ValueError):
        serial.parse_tlvs(b'\x53\xff\x00')


def test_closed_or_short_write_is_not_success():
    comm = serial.SerialComm('unused')
    with pytest.raises(RuntimeError, match='not open'):
        comm.send([serial.TLV(0, b'')])
    comm._ser = SimpleNamespace(is_open=True, write=lambda _: 1)
    with pytest.raises(OSError, match='short serial write'):
        comm.send([serial.TLV(0, b'')])


class FakeBench:
    def __init__(self, acknowledged):
        self.acknowledged = acknowledged
        self.sent = []
    def drain(self):
        pass
    def send(self, tlvs):
        self.sent.extend(tlvs)
    def receive(self, **kwargs):
        return serial.SerialPacket(0, [serial.TLV(0, b'\x24\x00')]) if self.acknowledged else None
    def receive_many(self, **kwargs):
        raise OSError('simulated disconnect')


def test_configuration_timeout_never_starts_ranging(monkeypatch):
    ticks = iter(range(100))
    monkeypatch.setattr(checks.time, 'monotonic', lambda: next(ticks))
    comm = FakeBench(False)
    result, _, _ = checks.check_ranging(comm)
    assert result.status == CheckStatus.FAIL
    assert [tlv.type for tlv in comm.sent] == [0x24]


def test_disconnect_still_attempts_stop(monkeypatch):
    monkeypatch.setattr(checks.time, 'sleep', lambda _: None)
    comm = FakeBench(True)
    with pytest.raises(OSError, match='disconnect'):
        checks.check_ranging(comm)
    assert comm.sent[-1] == checks.cmd_stop_ranging()[0]
    assert comm.sent[-2] == checks.cmd_start_ranging()[0]


def test_no_error_status_is_normal_but_reported_errors_still_count():
    assert checks._make_error_result('errors', []).status == CheckStatus.PASS
    assert checks._make_error_result('errors', [0]).status == CheckStatus.PASS
    assert checks._make_error_result('errors', [next(iter(checks.CRITICAL_ERROR_CODES))]).status == CheckStatus.FAIL
    assert checks._make_error_result('errors', [0xff]).status == CheckStatus.WARN


def test_quality_never_drops_invalid_frames_or_invents_rate_limit():
    frames = [checks.AoaFrame(distance=1., angle=359. if index % 2 else 1., pos_confidence=90) for index in range(6)]
    result = checks.check_data_quality(frames, duration=1.)
    assert result.status == CheckStatus.WARN
    assert abs(result.data['circular_mean_angle']) < 1e-8
    assert checks.check_data_quality(frames, duration=1., min_frame_rate=5.).status == CheckStatus.PASS
    frames[0].distance = float('nan')
    assert checks.check_data_quality(frames, duration=1., min_frame_rate=5.).status == CheckStatus.FAIL


def test_corrupt_length_cannot_swallow_following_valid_frame():
    comm = serial.SerialComm('unused')
    good = packet(b'\x00\x02\x24\x00')
    # This invalid outer frame claims the entire valid frame as its payload/tail.
    comm._buffer.extend(b'\x55\xaa\x00' + struct.pack('<H',len(good)) + b'xx' + good)
    response = comm._try_parse()
    assert response is not None and response.tlvs == [serial.TLV(0,b'\x24\x00')]
    assert comm.crc_errors == 1
