#!/usr/bin/env python3
"""Compatibility filename; supports both ROS CDR and Aorta FlatBuffers."""
from sensor_tools.uwb import detect_version_from_path, normalize_angle_for_version, mcap_to_dataframe, main

if __name__ == '__main__':
    raise SystemExit(main())
