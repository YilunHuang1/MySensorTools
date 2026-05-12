"""
tests/test_uwb.py — Tests for uwb.data_parser and uwb.diagnosis.
"""

import pytest
from uwb.data_parser import UWBDataParser, UWBRecord
from uwb.diagnosis import UWBDiagnoser


def _rec(ts, x, y, z=1.0, quality=0.9, tag="A"):
    return UWBRecord(timestamp=ts, tag_id=tag, x=x, y=y, z=z, quality=quality)


class TestUWBDataParser:
    def test_group_by_tag(self):
        records = [
            _rec(0.0, 1.0, 2.0, tag="A"),
            _rec(0.1, 1.1, 2.1, tag="B"),
            _rec(0.2, 1.2, 2.2, tag="A"),
        ]
        parser = UWBDataParser()
        groups = parser.group_by_tag(records)
        assert set(groups.keys()) == {"A", "B"}
        assert len(groups["A"]) == 2
        assert len(groups["B"]) == 1


class TestUWBDiagnoser:
    def test_no_faults_on_clean_data(self):
        data = [_rec(i * 0.1, x=float(i) * 0.01, y=0.0) for i in range(20)]
        diagnoser = UWBDiagnoser()
        faults = diagnoser.diagnose(data)
        assert faults == []

    def test_detects_empty(self):
        diagnoser = UWBDiagnoser()
        faults = diagnoser.diagnose([])
        assert len(faults) == 1

    def test_detects_position_jump(self):
        data = [_rec(0.0, 0.0, 0.0), _rec(0.1, 50.0, 0.0)]
        diagnoser = UWBDiagnoser(max_jump=2.0)
        faults = diagnoser.diagnose(data)
        assert any("jump" in f.lower() for f in faults)

    def test_detects_z_out_of_bounds(self):
        data = [_rec(0.0, 0.0, 0.0, z=10.0)]
        diagnoser = UWBDiagnoser(max_z=5.0)
        faults = diagnoser.diagnose(data)
        assert any("z-coordinate" in f.lower() for f in faults)

    def test_detects_low_quality(self):
        data = [_rec(0.0, 0.0, 0.0, quality=0.1)]
        diagnoser = UWBDiagnoser(min_quality=0.3)
        faults = diagnoser.diagnose(data)
        assert any("quality" in f.lower() for f in faults)

    def test_detects_timestamp_gap(self):
        data = [_rec(0.0, 0.0, 0.0), _rec(10.0, 0.1, 0.0)]
        diagnoser = UWBDiagnoser(max_timestamp_gap=1.0)
        faults = diagnoser.diagnose(data)
        assert any("gap" in f.lower() for f in faults)

    def test_detects_non_monotonic_timestamp(self):
        data = [_rec(1.0, 0.0, 0.0), _rec(0.5, 0.1, 0.0)]
        diagnoser = UWBDiagnoser()
        faults = diagnoser.diagnose(data)
        assert any("non-monotonic" in f.lower() for f in faults)
