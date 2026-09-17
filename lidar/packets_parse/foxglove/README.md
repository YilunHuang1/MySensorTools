# Foxglove LiDAR preview

Both paths decode reassembled WLR-722Z packets into `foxglove.PointCloud` at
`/sensor_tools/lidar_points_preview`. The bundled angular table is a reference;
use device calibration for quantitative geometry. This output must not replace
or be confused with the production `/lidar_points` channel.

## User Script

Paste `vanjee_722z_converter.ts` into a Foxglove User Script. Its default input is
`aorta/default/pub/lidar_packets`; edit `inputs` to the exact channel in your bag.
Foxglove must already decode the input schema. The script consumes `message.data`,
not CDR bytes. It retains packet fragments between messages and emits a preview
chunk for each input message, rather than promising exactly one full rotation.
Select `/sensor_tools/lidar_points_preview` in a 3D panel. Receive-time stamping is
for display, not sensor timing analysis. Reload the script when switching bags.

## Offline MCAP

Copy this entire `foxglove` folder (including `sensor_tools` and the calibration CSV), then:

```bash
python3 -m pip install -r requirements.txt
python3 mcap_add_lidar_points.py input.mcap output.mcap -n 100
```

Use `--topic` for an exact source channel and `--output-topic` to choose a unique
preview channel. Original schemas, messages, attachments and metadata are retained;
the frame limit applies only to added previews. Existing output files and output
channel collisions are refused. The output uses JSON `foxglove.PointCloud`, with
XYZ/intensity fields and frame `lidar`. It is not ROS PointCloud2.

For per-point timestamps and scan-boundary analysis use
`extract_lidar_pcd_with_ts.py`, not these display converters.
