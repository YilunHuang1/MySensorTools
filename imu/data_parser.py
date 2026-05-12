"""
imu/data_parser.py — Parser for IMU (Inertial Measurement Unit) CSV logs.

Expected CSV columns (header required):
    timestamp, acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z[, roll, pitch, yaw]

All angular values are in degrees; accelerations in m/s²; gyro in deg/s.
"""

import csv
from dataclasses import dataclass, field
from typing import List, Optional

from common.base_parser import BaseDataParser


@dataclass
class IMURecord:
    """One IMU measurement sample."""

    timestamp: float
    acc_x: float
    acc_y: float
    acc_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float
    roll: Optional[float] = field(default=None)
    pitch: Optional[float] = field(default=None)
    yaw: Optional[float] = field(default=None)


def _to_float(value: str) -> float:
    return float(value.strip())


class IMUDataParser(BaseDataParser):
    """Parse IMU data from a CSV file into a list of :class:`IMURecord`."""

    def parse_csv(self, filepath: str) -> List[IMURecord]:
        """Read *filepath* and return a list of :class:`IMURecord` objects."""
        records: List[IMURecord] = []
        with open(filepath, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                record = IMURecord(
                    timestamp=_to_float(row["timestamp"]),
                    acc_x=_to_float(row["acc_x"]),
                    acc_y=_to_float(row["acc_y"]),
                    acc_z=_to_float(row["acc_z"]),
                    gyro_x=_to_float(row["gyro_x"]),
                    gyro_y=_to_float(row["gyro_y"]),
                    gyro_z=_to_float(row["gyro_z"]),
                    roll=_to_float(row["roll"]) if "roll" in row else None,
                    pitch=_to_float(row["pitch"]) if "pitch" in row else None,
                    yaw=_to_float(row["yaw"]) if "yaw" in row else None,
                )
                records.append(record)
        return records

    def parse_records(self, records: List[dict]) -> List[IMURecord]:
        """Parse a list of dicts (e.g. from unit tests) into IMURecord objects."""
        result = []
        for row in records:
            result.append(
                IMURecord(
                    timestamp=float(row["timestamp"]),
                    acc_x=float(row["acc_x"]),
                    acc_y=float(row["acc_y"]),
                    acc_z=float(row["acc_z"]),
                    gyro_x=float(row["gyro_x"]),
                    gyro_y=float(row["gyro_y"]),
                    gyro_z=float(row["gyro_z"]),
                    roll=float(row["roll"]) if "roll" in row else None,
                    pitch=float(row["pitch"]) if "pitch" in row else None,
                    yaw=float(row["yaw"]) if "yaw" in row else None,
                )
            )
        return result
