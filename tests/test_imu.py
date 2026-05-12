"""
tests/test_imu.py — Tests for imu.data_parser and imu.diagnosis.
"""

import pytest
from imu.data_parser import IMUDataParser, IMURecord
from imu.diagnosis import IMUDiagnoser


def _make_record(ts, ax, ay, az, gx=0.0, gy=0.0, gz=0.0):
    return IMURecord(
        timestamp=ts,
        acc_x=ax, acc_y=ay, acc_z=az,
        gyro_x=gx, gyro_y=gy, gyro_z=gz,
    )


def _normal_record(ts=0.0):
    """Return an IMU record that looks like the sensor is lying flat (gravity on Z)."""
    return _make_record(ts, ax=0.0, ay=0.0, az=9.81)


class TestIMUDataParser:
    def test_parse_records(self):
        raw = [
            {"timestamp": "0.0", "acc_x": "0.0", "acc_y": "0.0", "acc_z": "9.81",
             "gyro_x": "0.1", "gyro_y": "-0.1", "gyro_z": "0.0"},
        ]
        parser = IMUDataParser()
        records = parser.parse_records(raw)
        assert len(records) == 1
        assert records[0].acc_z == pytest.approx(9.81)
        assert records[0].gyro_x == pytest.approx(0.1)

    def test_parse_records_with_orientation(self):
        raw = [
            {"timestamp": "1.0", "acc_x": "0.1", "acc_y": "-0.1", "acc_z": "9.8",
             "gyro_x": "0.0", "gyro_y": "0.0", "gyro_z": "0.05",
             "roll": "1.5", "pitch": "-0.5", "yaw": "90.0"},
        ]
        parser = IMUDataParser()
        records = parser.parse_records(raw)
        assert records[0].roll == pytest.approx(1.5)
        assert records[0].yaw == pytest.approx(90.0)


class TestIMUDiagnoser:
    def test_no_faults_on_clean_data(self):
        # Vary acc/gyro slightly so the stuck-sensor check does not fire.
        import math
        data = [
            _make_record(
                i * 0.01,
                ax=math.sin(i * 0.1) * 0.1,
                ay=math.cos(i * 0.1) * 0.1,
                az=9.81 + math.sin(i * 0.2) * 0.05,
                gx=math.sin(i * 0.3) * 0.5,
                gy=math.cos(i * 0.3) * 0.5,
                gz=math.sin(i * 0.4) * 0.3,
            )
            for i in range(50)
        ]
        diagnoser = IMUDiagnoser()
        faults = diagnoser.diagnose(data)
        assert faults == []

    def test_detects_empty_data(self):
        diagnoser = IMUDiagnoser()
        faults = diagnoser.diagnose([])
        assert len(faults) == 1
        assert "No IMU data" in faults[0]

    def test_detects_acc_saturation(self):
        rec = _make_record(0.0, ax=200.0, ay=0.0, az=9.81)
        diagnoser = IMUDiagnoser(acc_saturation=160.0)
        faults = diagnoser.diagnose([rec])
        assert any("saturation" in f.lower() for f in faults)

    def test_detects_gyro_saturation(self):
        rec = _make_record(0.0, ax=0.0, ay=0.0, az=9.81, gx=2500.0)
        diagnoser = IMUDiagnoser(gyro_saturation=2000.0)
        faults = diagnoser.diagnose([rec])
        assert any("gyro" in f.lower() and "saturation" in f.lower() for f in faults)

    def test_detects_abnormal_gravity(self):
        # |a| = sqrt(3) ≈ 1.73 m/s², far from 9.81 m/s²
        rec = _make_record(0.0, ax=1.0, ay=1.0, az=1.0)
        diagnoser = IMUDiagnoser(gravity=9.81, gravity_tol=1.5)
        faults = diagnoser.diagnose([rec])
        assert any("gravity" in f.lower() for f in faults)

    def test_detects_timestamp_gap(self):
        data = [_normal_record(0.0), _normal_record(5.0)]
        diagnoser = IMUDiagnoser(max_timestamp_gap=0.5)
        faults = diagnoser.diagnose(data)
        assert any("gap" in f.lower() for f in faults)

    def test_detects_non_monotonic_timestamp(self):
        data = [_normal_record(1.0), _normal_record(0.5)]
        diagnoser = IMUDiagnoser()
        faults = diagnoser.diagnose(data)
        assert any("non-monotonic" in f.lower() for f in faults)

    def test_detects_stuck_sensor(self):
        data = [_make_record(i * 0.01, 0.0, 0.0, 0.0) for i in range(10)]
        diagnoser = IMUDiagnoser()
        faults = diagnoser.diagnose(data)
        assert any("stuck" in f.lower() for f in faults)
