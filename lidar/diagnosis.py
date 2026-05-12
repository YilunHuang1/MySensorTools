"""
lidar/diagnosis.py — Fault diagnosis for LiDAR sensors.

Checks:
  - Too few points (possible occlusion or data loss)
  - Too many NaN / infinite values
  - Points at exactly (0, 0, 0) — common ghost return artefact
  - Intensity out of expected range
  - Missing ring IDs (if ring data is available)
"""

from typing import List, Optional, Sequence

import numpy as np

from common.base_parser import BaseDiagnoser
from lidar.data_parser import LidarFrame

DEFAULT_MIN_POINTS = 100
DEFAULT_MAX_ZERO_RATIO = 0.05      # up to 5 % zero points is acceptable
DEFAULT_INTENSITY_MAX = 255.0
DEFAULT_NAN_RATIO_THRESHOLD = 0.01  # > 1 % NaNs is suspicious


class LidarDiagnoser(BaseDiagnoser):
    """Diagnose a single :class:`~lidar.data_parser.LidarFrame` for common faults."""

    def __init__(
        self,
        min_points: int = DEFAULT_MIN_POINTS,
        max_zero_ratio: float = DEFAULT_MAX_ZERO_RATIO,
        intensity_max: float = DEFAULT_INTENSITY_MAX,
        nan_ratio_threshold: float = DEFAULT_NAN_RATIO_THRESHOLD,
        expected_rings: Optional[int] = None,
    ):
        self.min_points = min_points
        self.max_zero_ratio = max_zero_ratio
        self.intensity_max = intensity_max
        self.nan_ratio_threshold = nan_ratio_threshold
        self.expected_rings = expected_rings

    def diagnose(self, data: LidarFrame) -> List[str]:
        """Return a list of fault descriptions for *data*.

        Parameters
        ----------
        data : LidarFrame

        Returns
        -------
        list of str
            Empty list means no faults detected.
        """
        faults: List[str] = []
        faults.extend(self._check_point_count(data))
        faults.extend(self._check_nan_inf(data))
        faults.extend(self._check_zero_points(data))
        faults.extend(self._check_intensity(data))
        faults.extend(self._check_rings(data))
        return faults

    def _check_point_count(self, frame: LidarFrame) -> List[str]:
        if frame.num_points < self.min_points:
            return [
                f"Too few points: {frame.num_points} "
                f"(minimum expected: {self.min_points})"
            ]
        return []

    def _check_nan_inf(self, frame: LidarFrame) -> List[str]:
        faults = []
        total = frame.num_points
        if total == 0:
            return faults
        bad = np.sum(~np.isfinite(frame.points))
        ratio = bad / (total * 3)
        if ratio > self.nan_ratio_threshold:
            faults.append(
                f"High NaN/Inf ratio in point cloud: {ratio:.1%} of coordinates "
                f"are not finite ({int(bad)} values)"
            )
        return faults

    def _check_zero_points(self, frame: LidarFrame) -> List[str]:
        if frame.num_points == 0:
            return []
        zero_mask = np.all(frame.points == 0.0, axis=1)
        ratio = zero_mask.sum() / frame.num_points
        if ratio > self.max_zero_ratio:
            return [
                f"Excessive zero-origin returns: {ratio:.1%} of points are at (0,0,0) "
                f"(threshold: {self.max_zero_ratio:.1%})"
            ]
        return []

    def _check_intensity(self, frame: LidarFrame) -> List[str]:
        if frame.intensity is None or len(frame.intensity) == 0:
            return []
        out_of_range = np.sum(
            (frame.intensity < 0) | (frame.intensity > self.intensity_max)
        )
        if out_of_range > 0:
            return [
                f"{out_of_range} intensity values out of expected range "
                f"[0, {self.intensity_max}]"
            ]
        return []

    def _check_rings(self, frame: LidarFrame) -> List[str]:
        faults = []
        if frame.ring is None:
            return faults
        present = set(np.unique(frame.ring).tolist())
        if self.expected_rings is not None:
            expected = set(range(self.expected_rings))
            missing = expected - present
            if missing:
                faults.append(
                    f"Missing LiDAR ring IDs: {sorted(missing)} "
                    f"(expected {self.expected_rings} rings 0..{self.expected_rings-1})"
                )
        return faults
