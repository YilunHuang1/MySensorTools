#!/usr/bin/env python3
"""Compatibility entry point for explicit timestamp-range extraction.

Example:
  python extract_with_timestamp_range_example.py input.mcap \
    --start 1789000000 --end 1789000001 --save-pcd --output-dir output/window

Start/end are hardware-source Unix seconds, not MCAP recorder time.
"""
if __name__ == '__main__':
    from extract_lidar_pcd_with_ts import cli
    cli()
