"""
tests/test_infrared.py — Tests for infrared.data_parser and infrared.diagnosis.
"""

import numpy as np
import pytest

from infrared.data_parser import InfraredDataParser
from infrared.diagnosis import InfraredDiagnoser


def _make_frame(ts=0.0, temp_val=25.0, shape=(8, 8)):
    parser = InfraredDataParser()
    mat = np.full(shape, temp_val, dtype=float)
    return parser.from_matrix(ts, mat)


class TestInfraredFrame:
    def test_properties(self):
        frame = _make_frame(temp_val=30.0)
        assert frame.min_temp == pytest.approx(30.0)
        assert frame.max_temp == pytest.approx(30.0)
        assert frame.mean_temp == pytest.approx(30.0)


class TestInfraredDiagnoser:
    def test_no_faults_on_clean_frame(self):
        frame = _make_frame(temp_val=25.0)
        diagnoser = InfraredDiagnoser()
        faults = diagnoser.diagnose(frame)
        assert faults == []

    def test_detects_thermal_runaway(self):
        frame = _make_frame(temp_val=300.0)
        diagnoser = InfraredDiagnoser(thermal_runaway_threshold=200.0)
        faults = diagnoser.diagnose(frame)
        assert any("thermal runaway" in f.lower() for f in faults)

    def test_detects_out_of_range_temperature(self):
        parser = InfraredDataParser()
        mat = np.full((4, 4), 600.0)  # > max_temp default 550
        frame = parser.from_matrix(0.0, mat)
        diagnoser = InfraredDiagnoser(max_temp=550.0)
        faults = diagnoser.diagnose(frame)
        assert any("out of sensor range" in f.lower() for f in faults)

    def test_detects_nan_pixels(self):
        parser = InfraredDataParser()
        mat = np.full((10, 10), 25.0)
        mat[0, :] = np.nan  # 10 % NaN
        frame = parser.from_matrix(0.0, mat)
        diagnoser = InfraredDiagnoser(nan_ratio=0.05)
        faults = diagnoser.diagnose(frame)
        assert any("nan" in f.lower() for f in faults)

    def test_detects_stuck_pixels(self):
        # All frames identical → every pixel has zero variance
        frames = [_make_frame(ts=float(i), temp_val=25.0) for i in range(5)]
        diagnoser = InfraredDiagnoser()
        faults = diagnoser.diagnose_sequence(frames)
        assert any("stuck" in f.lower() for f in faults)
