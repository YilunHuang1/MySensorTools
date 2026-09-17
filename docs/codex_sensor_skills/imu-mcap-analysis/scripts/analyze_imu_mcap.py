#!/usr/bin/env python3
"""Compatibility entrypoint for the repository's maintained IMU analyzer."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[4]
    runpy.run_path(str(root / "imu/mcap_analysis/analyze_imu_mcap.py"), run_name="__main__")
