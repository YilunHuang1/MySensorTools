"""
tests/test_common_log_parser.py — Tests for common.log_parser.
"""

import pytest
from common.log_parser import SensorLogParser, LogEntry

SAMPLE_LOG = """\
[2024-01-15 10:00:00.000] [INFO] [LiDAR] Sensor initialised
[2024-01-15 10:00:01.100] [ERROR] [IMU] Accelerometer saturation on X-axis
[2024-01-15 10:00:02.200] [WARN] [UWB] Low signal quality for tag A
[2024-01-15 10:00:03.300] [DEBUG] [Stereo] Frame 42 received
"""


@pytest.fixture
def parser():
    return SensorLogParser()


@pytest.fixture
def entries(parser):
    return parser.parse_text(SAMPLE_LOG)


def test_parse_text_returns_correct_count(entries):
    assert len(entries) == 4


def test_entry_fields(entries):
    entry = entries[1]
    assert entry.level == "ERROR"
    assert entry.sensor == "IMU"
    assert "Accelerometer saturation" in entry.message


def test_filter_by_level_exact(parser, entries):
    errors = parser.filter_by_level(entries, "ERROR", min_severity=False)
    assert len(errors) == 1
    assert errors[0].level == "ERROR"


def test_filter_by_level_min_severity(parser, entries):
    # WARN and above should return WARN + ERROR (2 entries)
    result = parser.filter_by_level(entries, "WARN")
    levels = {e.level for e in result}
    assert "WARN" in levels
    assert "ERROR" in levels
    assert "DEBUG" not in levels
    assert "INFO" not in levels


def test_filter_by_sensor(parser, entries):
    imu_entries = parser.filter_by_sensor(entries, "IMU")
    assert len(imu_entries) == 1
    assert imu_entries[0].sensor == "IMU"


def test_filter_by_sensor_case_insensitive(parser, entries):
    lidar_entries = parser.filter_by_sensor(entries, "lidar")
    assert len(lidar_entries) == 1


def test_parse_text_unparseable_lines_skipped(parser):
    bad_log = "this line has no structure\n" + SAMPLE_LOG
    entries = parser.parse_text(bad_log)
    assert len(entries) == 4  # bad line silently skipped
