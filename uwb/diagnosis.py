"""
uwb/diagnosis.py — Fault diagnosis for UWB positioning sensors.

Checks:
  - Position jumps (sudden large displacement between consecutive samples)
  - Z-axis out of expected bounds (floor plan consistency)
  - Low signal quality
  - Timestamp gaps / non-monotonic timestamps
"""

from typing import List, Sequence

import numpy as np

from common.base_parser import BaseDiagnoser
from uwb.data_parser import UWBRecord

DEFAULT_MAX_JUMP = 2.0          # metres — flag larger instantaneous displacements
DEFAULT_MIN_QUALITY = 0.3       # normalised quality score threshold
DEFAULT_MAX_Z = 5.0             # metres above floor (reasonable building height)
DEFAULT_TIMESTAMP_GAP = 1.0     # seconds


class UWBDiagnoser(BaseDiagnoser):
    """Diagnose a sequence of :class:`~uwb.data_parser.UWBRecord` per tag."""

    def __init__(
        self,
        max_jump: float = DEFAULT_MAX_JUMP,
        min_quality: float = DEFAULT_MIN_QUALITY,
        max_z: float = DEFAULT_MAX_Z,
        max_timestamp_gap: float = DEFAULT_TIMESTAMP_GAP,
    ):
        self.max_jump = max_jump
        self.min_quality = min_quality
        self.max_z = max_z
        self.max_timestamp_gap = max_timestamp_gap

    def diagnose(self, data: Sequence[UWBRecord]) -> List[str]:
        """Diagnose a sequence of UWB records (single tag expected).

        Parameters
        ----------
        data : sequence of UWBRecord
            Time-ordered measurements for one tag.

        Returns
        -------
        list of str
        """
        faults: List[str] = []
        if not data:
            faults.append("No UWB data provided.")
            return faults
        faults.extend(self._check_position_jumps(data))
        faults.extend(self._check_z_bounds(data))
        faults.extend(self._check_quality(data))
        faults.extend(self._check_timestamp_gaps(data))
        return faults

    def _check_position_jumps(self, data: Sequence[UWBRecord]) -> List[str]:
        faults = []
        for i in range(1, len(data)):
            prev, curr = data[i - 1], data[i]
            dist = np.sqrt(
                (curr.x - prev.x) ** 2
                + (curr.y - prev.y) ** 2
                + (curr.z - prev.z) ** 2
            )
            if dist > self.max_jump:
                faults.append(
                    f"[t={curr.timestamp:.3f}] Position jump of {dist:.3f}m "
                    f"for tag '{curr.tag_id}' (threshold: {self.max_jump}m)"
                )
        return faults

    def _check_z_bounds(self, data: Sequence[UWBRecord]) -> List[str]:
        faults = []
        for rec in data:
            if rec.z < 0 or rec.z > self.max_z:
                faults.append(
                    f"[t={rec.timestamp:.3f}] Tag '{rec.tag_id}' Z-coordinate "
                    f"out of bounds: {rec.z:.3f}m (expected 0..{self.max_z}m)"
                )
        return faults

    def _check_quality(self, data: Sequence[UWBRecord]) -> List[str]:
        faults = []
        for rec in data:
            if rec.quality is not None and rec.quality < self.min_quality:
                faults.append(
                    f"[t={rec.timestamp:.3f}] Low UWB signal quality for tag "
                    f"'{rec.tag_id}': {rec.quality:.3f} (threshold: {self.min_quality})"
                )
        return faults

    def _check_timestamp_gaps(self, data: Sequence[UWBRecord]) -> List[str]:
        faults = []
        for i in range(1, len(data)):
            gap = data[i].timestamp - data[i - 1].timestamp
            if gap < 0:
                faults.append(
                    f"Non-monotonic timestamp at sample {i}: "
                    f"{data[i-1].timestamp:.3f} → {data[i].timestamp:.3f}"
                )
            elif gap > self.max_timestamp_gap:
                faults.append(
                    f"Large timestamp gap of {gap:.3f}s between sample {i-1} "
                    f"(t={data[i-1].timestamp:.3f}) and sample {i} "
                    f"(t={data[i].timestamp:.3f}) for tag '{data[i].tag_id}'"
                )
        return faults
