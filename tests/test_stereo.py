"""
tests/test_stereo.py — Tests for stereo.data_parser and stereo.diagnosis.
"""

import numpy as np
import pytest

from stereo.data_parser import StereoDataParser
from stereo.diagnosis import StereoDiagnoser


class TestStereoDiagnoser:
    def _make_frame(self, invalid_ratio=0.0, depth_min=0.5, depth_max=50.0, ts=0.0):
        parser = StereoDataParser()
        H, W = 10, 10
        disp = np.ones((H, W)) * 5.0
        depth = np.ones((H, W)) * 3.0
        n_invalid = int(invalid_ratio * H * W)
        for i in range(n_invalid):
            disp[i // W, i % W] = np.nan
        return parser.parse_matrix(ts, disp, depth)

    def test_no_faults_on_clean_frame(self):
        frame = self._make_frame(invalid_ratio=0.0)
        diagnoser = StereoDiagnoser()
        faults = diagnoser.diagnose(frame)
        assert faults == []

    def test_detects_high_invalid_disparity(self):
        frame = self._make_frame(invalid_ratio=0.5)
        diagnoser = StereoDiagnoser(max_invalid_ratio=0.3)
        faults = diagnoser.diagnose(frame)
        assert any("invalid" in f.lower() for f in faults)

    def test_detects_depth_out_of_range(self):
        parser = StereoDataParser()
        disp = np.ones((5, 5)) * 5.0
        depth = np.ones((5, 5)) * 200.0  # >> max_depth
        frame = parser.parse_matrix(0.0, disp, depth)
        diagnoser = StereoDiagnoser(max_depth=100.0)
        faults = diagnoser.diagnose(frame)
        assert any("depth" in f.lower() for f in faults)
