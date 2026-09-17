# Historical ROS package metadata

The original repository did not include `msg/UWB.msg`; reconstructing a wire schema
from guesses would break compatibility. This directory is therefore excluded from
colcon builds. Current BLE tools use `SerialHandlerStandalone` and CSV output;
robot data is read through Aorta or file-embedded MCAP schemas. No custom ROS
message package is required. These two metadata files are retained for history.
