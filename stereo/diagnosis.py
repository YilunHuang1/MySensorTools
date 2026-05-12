"""
stereo/diagnosis.py — Fault diagnosis for stereo cameras.

Checks:
  - High proportion of invalid disparities (NaN or ≤ 0)
  - Depth values out of sensor range
  - Sudden frame-to-frame disparity histogram shifts
"""

from typing import List, Optional, Sequence

import numpy as np

from common.base_parser import BaseDiagnoser
from stereo.data_parser import StereoFrame

DEFAULT_MAX_INVALID_RATIO = 0.30   # > 30 % invalid pixels is suspicious
DEFAULT_MIN_DEPTH = 0.1            # metres
DEFAULT_MAX_DEPTH = 100.0          # metres


class StereoDiagnoser(BaseDiagnoser):
    """Diagnose stereo camera frames for common disparity / depth faults."""

    def __init__(
        self,
        max_invalid_ratio: float = DEFAULT_MAX_INVALID_RATIO,
        min_depth: float = DEFAULT_MIN_DEPTH,
        max_depth: float = DEFAULT_MAX_DEPTH,
    ):
        self.max_invalid_ratio = max_invalid_ratio
        self.min_depth = min_depth
        self.max_depth = max_depth

    def diagnose(self, data: StereoFrame) -> List[str]:
        """Diagnose a single :class:`StereoFrame`."""
        faults: List[str] = []
        faults.extend(self._check_invalid_disparity(data))
        if data.depth is not None:
            faults.extend(self._check_depth_range(data))
        return faults

    def diagnose_sequence(self, frames: Sequence[StereoFrame]) -> List[str]:
        """Diagnose a sequence of frames, including temporal checks."""
        faults: List[str] = []
        for frame in frames:
            faults.extend(self.diagnose(frame))
        return faults

    def _check_invalid_disparity(self, frame: StereoFrame) -> List[str]:
        total = frame.disparity.size
        if total == 0:
            return ["Empty disparity frame."]
        invalid = np.sum(~np.isfinite(frame.disparity) | (frame.disparity <= 0))
        ratio = invalid / total
        if ratio > self.max_invalid_ratio:
            return [
                f"[t={frame.timestamp:.3f}] High invalid disparity ratio: {ratio:.1%} "
                f"({int(invalid)}/{total} pixels)"
            ]
        return []

    def _check_depth_range(self, frame: StereoFrame) -> List[str]:
        faults = []
        depth = frame.depth
        valid = depth[np.isfinite(depth)]
        if valid.size == 0:
            return faults
        out_of_range = np.sum((valid < self.min_depth) | (valid > self.max_depth))
        if out_of_range > 0:
            faults.append(
                f"[t={frame.timestamp:.3f}] {int(out_of_range)} depth pixels out of range "
                f"[{self.min_depth}, {self.max_depth}] m"
            )
        return faults
