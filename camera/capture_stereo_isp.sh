#!/usr/bin/env bash
# Capture a reproducible stereo ISP test bundle without changing camera or robot state.
# Start it before the dog walks; stop with Ctrl-C after the test route finishes.

set -Eeuo pipefail
umask 022

readonly DEFAULT_OUTPUT_ROOT="/tmp/stereo_capture"
readonly ENV_SCRIPT="/app/script/env.sh"
readonly STEREO_CONFIG_DIR="/app/stereo/config"

output_root="$DEFAULT_OUTPUT_ROOT"
label="manual"
duration_sec=0

usage() {
  cat <<'EOF'
Usage: capture_stereo_isp.sh [options]

Records the stereo evidence needed for ISP tuning:
  - left/right H.265 and NV12 streams when available
  - left/right ISP 2A status
  - ROS graph/topic metadata, runtime config, ISP JSON checksum, and logs

Options:
  -o, --output-root DIR   Parent directory for the capture bundle (default: /tmp/stereo_capture)
  -l, --label NAME        Short scene label used in the bundle name (default: manual)
  -d, --duration SEC      Stop automatically after SEC seconds; 0 means Ctrl-C stops recording
  -h, --help              Show this help

Example:
  /root/stereo_capture_1107.sh -l p0-03_mixed_light
  /root/stereo_capture_1107.sh -l p0-06_follow_run -d 30
EOF
}

while (($# > 0)); do
  case "$1" in
    -o|--output-root)
      output_root="$2"
      shift 2
      ;;
    -l|--label)
      label="$2"
      shift 2
      ;;
    -d|--duration)
      duration_sec="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! [[ "$duration_sec" =~ ^[0-9]+$ ]]; then
  echo "--duration must be a non-negative integer" >&2
  exit 2
fi

if [[ ! -r "$ENV_SCRIPT" ]]; then
  echo "Missing ROS environment: $ENV_SCRIPT" >&2
  exit 1
fi

# The deployed ROS environment carries the correct DDS settings for the X5.
source "$ENV_SCRIPT"

if ! command -v ros2 >/dev/null; then
  echo "ros2 is unavailable after sourcing $ENV_SCRIPT" >&2
  exit 1
fi

timestamp="$(date +%Y%m%d_%H%M%S)"
safe_label="$(printf '%s' "$label" | tr -cs '[:alnum:]_.-' '_')"
capture_dir="${output_root%/}/${timestamp}_${safe_label}"
metadata_dir="$capture_dir/metadata"
bag_dir="$capture_dir/stereo.mcap"
mkdir -p "$metadata_dir"

readonly -a CANDIDATE_TOPICS=(
  /image_left_raw/h265
  /image_right_raw/h265
  /image_left_raw/h265_half
  /image_right_raw/h265_half
  /image_left_raw/h265_quarter
  /image_right_raw/h265_quarter
  /image_left_raw/nv12_half
  /image_left_raw/nv12_quarter
  /image_right_raw/nv12_quarter
  /stereo/left/isp_status
  /stereo/right/isp_status
  /stereo_left/camera_info
  /stereo_right/camera_info
)

bag_pid=""

capture_runtime_metadata() {
  local phase="$1"
  local status_topic

  {
    echo "capture_phase=$phase"
    date -Is
    hostname
    uname -a
    echo "--- stereo process ---"
    ps -ef | grep -E '[s]tereo_exec|[c]amera_encode' || true
    echo "--- sensor driver parameters ---"
    for parameter in /sys/module/hobot_sensor/parameters/sensor_num \
                     /sys/module/hobot_sensor/parameters/sensor_update_flag; do
      [[ -r "$parameter" ]] && printf '%s=' "$parameter" && cat "$parameter"
    done
  } >"$metadata_dir/runtime_${phase}.txt" 2>&1

  {
    echo "--- ROS topics ---"
    ros2 topic list || true
    echo "--- ROS nodes ---"
    ros2 node list || true
  } >"$metadata_dir/ros_graph_${phase}.txt" 2>&1

  for status_topic in /stereo/left/isp_status /stereo/right/isp_status; do
    local side="${status_topic#/stereo/}"
    side="${side%/isp_status}"
    timeout 8 ros2 topic echo --once "$status_topic" \
      >"$metadata_dir/isp_status_${side}_${phase}.yaml" 2>&1 || true
  done
}

copy_static_evidence() {
  {
    echo "--- ISP JSON ---"
    ls -l "$STEREO_CONFIG_DIR/sc230ai_tuning_sensing.json" || true
    md5sum "$STEREO_CONFIG_DIR/sc230ai_tuning_sensing.json" || true
    sha256sum "$STEREO_CONFIG_DIR/sc230ai_tuning_sensing.json" || true
    echo "--- deployed stereo executable ---"
    ls -l /app/stereo/stereo_exec || true
    md5sum /app/stereo/stereo_exec || true
    sha256sum /app/stereo/stereo_exec || true
    echo "--- deployed stereo configs ---"
    find "$STEREO_CONFIG_DIR" -maxdepth 2 -type f -printf '%p\n' | sort || true
  } >"$metadata_dir/config_manifest.txt" 2>&1

  for config in \
    "$STEREO_CONFIG_DIR/sc230ai_tuning_sensing.json" \
    "$STEREO_CONFIG_DIR/node_config.json" \
    "$STEREO_CONFIG_DIR/nodes/stereo_camera.json"; do
    [[ -r "$config" ]] && cp --preserve=mode,timestamps "$config" "$metadata_dir/"
  done

  # Keep the complete tuning JSON above, and also extract the high-value knobs
  # needed to compare captures without manually opening the full parameter file.
  if command -v python3 >/dev/null; then
    python3 - "$STEREO_CONFIG_DIR/sc230ai_tuning_sensing.json" \
      >"$metadata_dir/isp_summary.json" 2>&1 <<'PY' || true
import json
import sys

with open(sys.argv[1], encoding="utf-8") as file:
    tuning = json.load(file)

header = tuning.get("header", {})
sensor_awb = tuning.get("sensor", {}).get("AWB", {})
awb_global = (sensor_awb.get("globals") or [{}])[0]
illumination = sensor_awb.get("illumination") or []
modules = tuning.get("tuning", {})

summary = {
    "header": {
        key: header.get(key)
        for key in ("creation_date", "creator", "sensor_name", "sample_name", "generator_version", "resolution")
    },
    "awb_global": {
        key: awb_global.get(key)
        for key in ("fRgProjIndoorMin", "fRgProjMax", "fRgProjMaxSky", "fRgProjOutdoorMin", "IIR")
    },
    "awb_illumination": [
        {
            "name": item.get("name"),
            "doorType": item.get("doorType"),
            "manualWB": item.get("manualWB"),
            "manualccMatrix": item.get("manualccMatrix"),
        }
        for item in illumination
    ],
    "module_presence": {
        "WDR_5_2_1": "WDR_5_2_1" in modules,
        "HDR_3_2DOL": "HDR_3_2DOL" in modules,
    },
    "hdr_isEnable_values": [
        item.get("isEnable")
        for item in modules.get("HDR_3_2DOL", {}).get("config", [])
        if isinstance(item, dict) and "isEnable" in item
    ],
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY
  else
    grep -n -E '"(creation_date|sensor_name|sample_name|WDR_5_2_1|HDR_3_2DOL)"' \
      "$STEREO_CONFIG_DIR/sc230ai_tuning_sensing.json" \
      >"$metadata_dir/isp_summary.txt" 2>&1 || true
  fi

  find /tmp/logs /app/logs -maxdepth 2 -type f -iname '*stereo*' -print \
    >"$metadata_dir/stereo_log_files.txt" 2>/dev/null || true
  while IFS= read -r log_file; do
    [[ -r "$log_file" ]] || continue
    cp --preserve=mode,timestamps "$log_file" "$metadata_dir/$(basename "$log_file")" 2>/dev/null || true
  done <"$metadata_dir/stereo_log_files.txt"
}

write_topic_metadata() {
  local topic
  for topic in "${CANDIDATE_TOPICS[@]}"; do
    local topic_file
    topic_file="$(printf '%s' "$topic" | tr '/' '_')"
    ros2 topic info -v "$topic" >"$metadata_dir/topic${topic_file}.txt" 2>&1 || true
  done
}

stop_capture() {
  local exit_code=$?
  trap - EXIT INT TERM

  if [[ -n "$bag_pid" ]] && kill -0 "$bag_pid" 2>/dev/null; then
    echo "Stopping rosbag recorder (PID $bag_pid)..."
    kill -INT "$bag_pid" 2>/dev/null || true
    wait "$bag_pid" || true
  fi

  capture_runtime_metadata "end"
  copy_static_evidence
  if [[ -d "$bag_dir" ]]; then
    ros2 bag info "$bag_dir" >"$metadata_dir/rosbag_info.txt" 2>&1 || true
  fi
  (cd "$capture_dir" && find . -type f -print0 | sort -z | xargs -0 sha256sum) \
    >"$metadata_dir/SHA256SUMS.txt" 2>&1 || true

  echo "Capture bundle: $capture_dir"
  exit "$exit_code"
}

trap stop_capture EXIT INT TERM

capture_runtime_metadata "start"
copy_static_evidence
write_topic_metadata

echo "Starting stereo capture. Operate the dog, then press Ctrl-C to stop."
echo "Output: $capture_dir"

if ((duration_sec > 0)); then
  timeout --signal=INT "${duration_sec}s" \
    ros2 bag record --storage mcap --output "$bag_dir" "${CANDIDATE_TOPICS[@]}" \
    >"$metadata_dir/rosbag_record.log" 2>&1 &
else
  ros2 bag record --storage mcap --output "$bag_dir" "${CANDIDATE_TOPICS[@]}" \
    >"$metadata_dir/rosbag_record.log" 2>&1 &
fi
bag_pid=$!
wait "$bag_pid"
