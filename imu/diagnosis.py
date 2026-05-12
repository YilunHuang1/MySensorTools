"""
imu/diagnosis.py — Fault diagnosis for IMU sensors.

Checks performed:
  - Accelerometer saturation (|acc| > threshold)
  - Gyroscope saturation (|gyro| > threshold)
  - Static acceleration check: gravity vector magnitude should be ~9.81 m/s²
  - Timestamp monotonicity / gaps
  - Zero-output (stuck sensor)
"""

from typing import List, Sequence

import numpy as np

from common.base_parser import BaseDiagnoser
from imu.data_parser import IMURecord

# Default thresholds
DEFAULT_ACC_SATURATION = 160.0   # m/s²  (typical ±16 g range)
DEFAULT_GYRO_SATURATION = 2000.0  # deg/s (typical ±2000 dps range)
DEFAULT_GRAVITY = 9.81            # m/s²
DEFAULT_GRAVITY_TOL = 1.5         # m/s² tolerance
DEFAULT_TIMESTAMP_GAP = 0.5       # seconds — flag gaps larger than this


class IMUDiagnoser(BaseDiagnoser):
    """Analyse a list of :class:`~imu.data_parser.IMURecord` for common IMU faults."""

    def __init__(
        self,
        acc_saturation: float = DEFAULT_ACC_SATURATION,
        gyro_saturation: float = DEFAULT_GYRO_SATURATION,
        gravity: float = DEFAULT_GRAVITY,
        gravity_tol: float = DEFAULT_GRAVITY_TOL,
        max_timestamp_gap: float = DEFAULT_TIMESTAMP_GAP,
    ):
        self.acc_saturation = acc_saturation
        self.gyro_saturation = gyro_saturation
        self.gravity = gravity
        self.gravity_tol = gravity_tol
        self.max_timestamp_gap = max_timestamp_gap

    def diagnose(self, data: Sequence[IMURecord]) -> List[str]:
        """Return a list of fault strings found in *data*.

        Parameters
        ----------
        data : sequence of IMURecord
            Time-ordered IMU measurements.

        Returns
        -------
        list of str
            Human-readable fault descriptions.  Empty list → no faults.
        """
        faults: List[str] = []
        if not data:
            faults.append("No IMU data provided.")
            return faults

        faults.extend(self._check_acc_saturation(data))
        faults.extend(self._check_gyro_saturation(data))
        faults.extend(self._check_gravity_magnitude(data))
        faults.extend(self._check_timestamp_gaps(data))
        faults.extend(self._check_stuck_sensor(data))
        return faults

    def _check_acc_saturation(self, data: Sequence[IMURecord]) -> List[str]:
        faults = []
        for rec in data:
            for axis, val in (("X", rec.acc_x), ("Y", rec.acc_y), ("Z", rec.acc_z)):
                if abs(val) >= self.acc_saturation:
                    faults.append(
                        f"[t={rec.timestamp:.3f}] Accelerometer {axis}-axis saturation: "
                        f"{val:.2f} m/s² (threshold ±{self.acc_saturation} m/s²)"
                    )
        return faults

    def _check_gyro_saturation(self, data: Sequence[IMURecord]) -> List[str]:
        faults = []
        for rec in data:
            for axis, val in (("X", rec.gyro_x), ("Y", rec.gyro_y), ("Z", rec.gyro_z)):
                if abs(val) >= self.gyro_saturation:
                    faults.append(
                        f"[t={rec.timestamp:.3f}] Gyroscope {axis}-axis saturation: "
                        f"{val:.2f} deg/s (threshold ±{self.gyro_saturation} deg/s)"
                    )
        return faults

    def _check_gravity_magnitude(self, data: Sequence[IMURecord]) -> List[str]:
        faults = []
        for rec in data:
            mag = np.sqrt(rec.acc_x**2 + rec.acc_y**2 + rec.acc_z**2)
            if abs(mag - self.gravity) > self.gravity_tol:
                faults.append(
                    f"[t={rec.timestamp:.3f}] Unusual gravity magnitude: "
                    f"{mag:.3f} m/s² (expected {self.gravity} ± {self.gravity_tol})"
                )
        return faults

    def _check_timestamp_gaps(self, data: Sequence[IMURecord]) -> List[str]:
        faults = []
        timestamps = [r.timestamp for r in data]
        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i - 1]
            if gap < 0:
                faults.append(
                    f"Timestamp non-monotonic between sample {i - 1} "
                    f"(t={timestamps[i-1]:.3f}) and sample {i} (t={timestamps[i]:.3f})"
                )
            elif gap > self.max_timestamp_gap:
                faults.append(
                    f"Large timestamp gap of {gap:.3f}s between sample {i - 1} "
                    f"(t={timestamps[i-1]:.3f}) and sample {i} (t={timestamps[i]:.3f})"
                )
        return faults

    def _check_stuck_sensor(self, data: Sequence[IMURecord]) -> List[str]:
        """Detect if any axis outputs a constant value across all samples."""
        faults = []
        if len(data) < 3:
            return faults
        channels = {
            "acc_x": [r.acc_x for r in data],
            "acc_y": [r.acc_y for r in data],
            "acc_z": [r.acc_z for r in data],
            "gyro_x": [r.gyro_x for r in data],
            "gyro_y": [r.gyro_y for r in data],
            "gyro_z": [r.gyro_z for r in data],
        }
        for ch, vals in channels.items():
            if len(set(vals)) == 1:
                faults.append(
                    f"Stuck sensor detected on channel '{ch}': "
                    f"constant value {vals[0]} across all {len(vals)} samples"
                )
        return faults
