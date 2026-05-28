# Migration Notes

This repository is a cleaned tool-only extraction from `/Users/yilunhuang/vita-project`.

Included:
- Source code for sensor analysis, diagnosis, plotting, conversion, and smoke tests.
- Small configuration templates and calibration tables required by the tools.
- Human documentation and Codex sensor skill references.

Excluded intentionally:
- Raw MCAP/rosbag data, CSV captures, PCD output, generated charts, reports, notebooks, caches, and local virtual environments.
- Large model/runtime assets from `04_imu/omni_demo`.
- Historical Copilot chat exports and local debug records.
- Vendor binary packages and shared libraries.
- Duplicate or hardcoded experimental scripts that were replaced by consolidated tools.

Consolidations:
- UWB ad-hoc 2D/3D plotting scripts were replaced by `uwb/visualization/plot_uwb_csv.py`.
- Camera EEPROM parsing is kept as `camera/eeprom/parse_eeprom.py`; the misspelled duplicate `parse_epprom.py` was dropped.
- IMU MCAP analysis is kept in `imu/mcap_analysis/analyze_imu_mcap.py`; the duplicate copy under Codex skill docs is documentation context only.

Repository maintenance rule:
- Put new reusable code under the relevant sensor directory.
- Put large data in external storage or a release artifact, not in git.
- Prefer CLI arguments over editing hardcoded local paths.
