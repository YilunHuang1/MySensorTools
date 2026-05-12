"""
infrared/diagnosis.py — Fault diagnosis for infrared / thermal cameras.

Checks:
  - Temperature out of sensor measurement range
  - Dead / stuck pixels (constant temperature across frames)
  - High number of NaN pixels
  - Thermal runaway: scene max temperature exceeds a safety threshold
"""

from typing import List, Sequence

import numpy as np

from common.base_parser import BaseDiagnoser
from infrared.data_parser import InfraredFrame

DEFAULT_MIN_TEMP = -40.0    # °C — typical sensor lower bound
DEFAULT_MAX_TEMP = 550.0    # °C — typical sensor upper bound
DEFAULT_THERMAL_RUNAWAY = 200.0  # °C — flag if max scene temp exceeds this
DEFAULT_NAN_RATIO = 0.05    # > 5 % NaN pixels is suspicious


class InfraredDiagnoser(BaseDiagnoser):
    """Diagnose infrared camera frames for common thermal-imaging faults."""

    def __init__(
        self,
        min_temp: float = DEFAULT_MIN_TEMP,
        max_temp: float = DEFAULT_MAX_TEMP,
        thermal_runaway_threshold: float = DEFAULT_THERMAL_RUNAWAY,
        nan_ratio: float = DEFAULT_NAN_RATIO,
    ):
        self.min_temp = min_temp
        self.max_temp = max_temp
        self.thermal_runaway_threshold = thermal_runaway_threshold
        self.nan_ratio = nan_ratio

    def diagnose(self, data: InfraredFrame) -> List[str]:
        """Diagnose a single :class:`InfraredFrame`."""
        faults: List[str] = []
        faults.extend(self._check_nan_pixels(data))
        faults.extend(self._check_temperature_range(data))
        faults.extend(self._check_thermal_runaway(data))
        return faults

    def diagnose_sequence(self, frames: Sequence[InfraredFrame]) -> List[str]:
        """Diagnose a sequence of frames including stuck-pixel checks."""
        faults: List[str] = []
        for frame in frames:
            faults.extend(self.diagnose(frame))
        if len(frames) >= 3:
            faults.extend(self._check_stuck_pixels(frames))
        return faults

    def _check_nan_pixels(self, frame: InfraredFrame) -> List[str]:
        total = frame.temperature.size
        nan_count = int(np.sum(np.isnan(frame.temperature)))
        ratio = nan_count / total if total > 0 else 0.0
        if ratio > self.nan_ratio:
            return [
                f"[t={frame.timestamp:.3f}] High NaN pixel ratio: {ratio:.1%} "
                f"({nan_count}/{total} pixels)"
            ]
        return []

    def _check_temperature_range(self, frame: InfraredFrame) -> List[str]:
        faults = []
        valid = frame.temperature[np.isfinite(frame.temperature)]
        out_of_range = np.sum((valid < self.min_temp) | (valid > self.max_temp))
        if out_of_range > 0:
            faults.append(
                f"[t={frame.timestamp:.3f}] {int(out_of_range)} pixels out of sensor range "
                f"[{self.min_temp}, {self.max_temp}] °C"
            )
        return faults

    def _check_thermal_runaway(self, frame: InfraredFrame) -> List[str]:
        max_t = frame.max_temp
        if max_t > self.thermal_runaway_threshold:
            return [
                f"[t={frame.timestamp:.3f}] Thermal runaway warning: "
                f"max temperature {max_t:.1f} °C exceeds threshold "
                f"{self.thermal_runaway_threshold} °C"
            ]
        return []

    def _check_stuck_pixels(self, frames: Sequence[InfraredFrame]) -> List[str]:
        """Flag pixels whose temperature never changes across all frames."""
        mats = [f.temperature for f in frames]
        stacked = np.stack(mats, axis=0)  # (T, H, W)
        variance = np.nanvar(stacked, axis=0)
        stuck_count = int(np.sum(variance == 0.0))
        total = variance.size
        if stuck_count > 0:
            return [
                f"Stuck pixels detected: {stuck_count}/{total} pixels "
                f"show zero variance across {len(frames)} frames"
            ]
        return []
