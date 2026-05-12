"""
tests/test_lidar.py — Tests for lidar.data_parser and lidar.diagnosis.
"""

import numpy as np
import pytest

from lidar.data_parser import LidarDataParser, LidarFrame
from lidar.diagnosis import LidarDiagnoser

PCD_TEXT = """\
# .PCD v0.7
VERSION 0.7
FIELDS x y z intensity ring
SIZE 4 4 4 4 4
TYPE F F F F U
COUNT 1 1 1 1 1
WIDTH 5
HEIGHT 1
VIEWPOINT 0 0 0 1 0 0 0
POINTS 5
DATA ascii
1.0 2.0 0.5 100 0
3.0 4.0 1.0 200 1
5.0 6.0 1.5 150 2
7.0 8.0 2.0 50 3
9.0 10.0 2.5 80 4
"""


class TestLidarDataParser:
    def test_parse_pcd_text(self):
        parser = LidarDataParser()
        frames = parser._parse_pcd_text(PCD_TEXT)
        assert len(frames) == 1
        frame = frames[0]
        assert frame.num_points == 5
        assert frame.points.shape == (5, 3)
        assert frame.intensity is not None
        assert frame.ring is not None

    def test_parse_pcd_coordinates(self):
        parser = LidarDataParser()
        frame = parser._parse_pcd_text(PCD_TEXT)[0]
        np.testing.assert_allclose(frame.points[0], [1.0, 2.0, 0.5])
        np.testing.assert_allclose(frame.points[-1], [9.0, 10.0, 2.5])

    def test_parse_pcd_rings(self):
        parser = LidarDataParser()
        frame = parser._parse_pcd_text(PCD_TEXT)[0]
        assert list(frame.ring) == [0, 1, 2, 3, 4]


class TestLidarDiagnoser:
    def _make_frame(self, n=200, rings=None):
        pts = np.random.rand(n, 3) * 10
        intensity = np.random.rand(n) * 255
        ring = np.array(rings) if rings is not None else None
        return LidarFrame(points=pts, intensity=intensity, ring=ring)

    def test_no_faults_on_clean_frame(self):
        frame = self._make_frame(n=500)
        diagnoser = LidarDiagnoser(min_points=100)
        faults = diagnoser.diagnose(frame)
        assert faults == []

    def test_detects_too_few_points(self):
        frame = self._make_frame(n=10)
        diagnoser = LidarDiagnoser(min_points=100)
        faults = diagnoser.diagnose(frame)
        assert any("too few" in f.lower() for f in faults)

    def test_detects_excessive_zero_points(self):
        pts = np.zeros((200, 3))
        frame = LidarFrame(points=pts)
        diagnoser = LidarDiagnoser(min_points=100, max_zero_ratio=0.05)
        faults = diagnoser.diagnose(frame)
        assert any("zero" in f.lower() for f in faults)

    def test_detects_intensity_out_of_range(self):
        pts = np.random.rand(200, 3) * 5
        intensity = np.full(200, 300.0)  # > 255
        frame = LidarFrame(points=pts, intensity=intensity)
        diagnoser = LidarDiagnoser(min_points=100, intensity_max=255.0)
        faults = diagnoser.diagnose(frame)
        assert any("intensity" in f.lower() for f in faults)

    def test_detects_missing_rings(self):
        pts = np.random.rand(200, 3) * 5
        ring = np.zeros(200, dtype=int)  # only ring 0 present; expect 4
        frame = LidarFrame(points=pts, ring=ring)
        diagnoser = LidarDiagnoser(min_points=100, expected_rings=4)
        faults = diagnoser.diagnose(frame)
        assert any("ring" in f.lower() for f in faults)

    def test_nan_detection(self):
        pts = np.random.rand(200, 3)
        pts[0] = [np.nan, np.nan, np.nan]
        pts[1] = [np.inf, 0, 0]
        frame = LidarFrame(points=pts)
        diagnoser = LidarDiagnoser(min_points=100, nan_ratio_threshold=0.001)
        faults = diagnoser.diagnose(frame)
        assert any("nan" in f.lower() or "inf" in f.lower() for f in faults)
