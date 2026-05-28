#!/usr/bin/env python3
"""Create a standardized Vita robot debug case from dropped data files."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEBUG_CASES_ROOT = REPO_ROOT / "debug_cases"
PRIMARY_CODEBASE = os.environ.get("VITA_ROBOT_ROOT", str(REPO_ROOT / "vita-robot"))
TOOLS_ROOT = REPO_ROOT

DATA_EXTS = {
    ".mcap",
    ".db3",
    ".bag",
    ".log",
    ".txt",
    ".tar",
    ".gz",
    ".tgz",
    ".zip",
}
SCREENSHOT_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create debug_cases/<case_id> with issue.yaml from MCAP/log/screenshot inputs."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Files or directories to include. Directories are scanned one level recursively.",
    )
    parser.add_argument("--case-id", help="Case id. Defaults to timestamp plus inferred sensor.")
    parser.add_argument("--title", help="Human-readable title.")
    parser.add_argument("--time", dest="problem_time", help='Problem time in CST, e.g. "2026-05-13 14:24:54.240".')
    parser.add_argument("--symptom", help="Short problem description.")
    parser.add_argument("--fault-log", action="append", default=[], help="Fault log line. Can be repeated.")
    parser.add_argument("--robot-behavior", help="What the robot was doing at the problem time.")
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy input files instead of creating symlinks. Default is symlink.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow writing into an existing case directory.",
    )
    return parser.parse_args()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "sensor_issue"


def collect_inputs(inputs: list[str]) -> tuple[list[Path], list[Path]]:
    data_files: list[Path] = []
    screenshots: list[Path] = []
    for raw in inputs:
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"input does not exist: {path}")
        candidates = [path]
        if path.is_dir():
            candidates = [p for p in path.rglob("*") if p.is_file()]
        for candidate in candidates:
            suffix = "".join(candidate.suffixes[-2:]).lower()
            single_suffix = candidate.suffix.lower()
            if single_suffix in SCREENSHOT_EXTS:
                screenshots.append(candidate)
            elif single_suffix in DATA_EXTS or suffix in {".tar.gz"}:
                data_files.append(candidate)
    return sorted(set(data_files)), sorted(set(screenshots))


def scan_text(files: list[Path], limit_bytes: int = 512_000) -> str:
    chunks: list[str] = []
    for path in files:
        if path.suffix.lower() not in {".log", ".txt"}:
            continue
        try:
            with path.open("rb") as handle:
                raw = handle.read(limit_bytes)
        except OSError:
            continue
        chunks.append(raw.decode("utf-8", errors="ignore"))
    return "\n".join(chunks)


def infer_sensor(text: str, files: list[Path]) -> tuple[str, str, list[str]]:
    names = " ".join(str(p.name).lower() for p in files)
    haystack = f"{text.lower()}\n{names}"
    rules = [
        ("imu-mcap-analysis", "imu", ["imu", "acc_norm", "gyroscope", "/imu_raw", "asm330"]),
        ("lidar-debug", "lidar", ["lidar", "pointcloud", "/lidar_points", "vanjee", "rtc"]),
        ("uwb-debug", "uwb", ["uwb", "anchor", "tag", "head_touch", "ble"]),
        ("stereo-debug", "stereo", ["stereo", "image_left", "image_right", "h265_quarter", "nv12"]),
        ("infrared-debug", "infrared", ["infrared", "ir", "sc202cs", "qr", "video_h265"]),
    ]
    for skill, sensor, keywords in rules:
        if any(keyword in haystack for keyword in keywords):
            return skill, sensor, keywords
    return "vita-sensor-debug", "sensor", []


def extract_fault_lines(text: str, explicit_lines: list[str]) -> list[str]:
    lines = [line.strip() for line in explicit_lines if line.strip()]
    for line in text.splitlines():
        lower = line.lower()
        if any(token in lower for token in ["fault", "error", "warn", "异常", "报错"]):
            lines.append(line.strip())
        if len(lines) >= 20:
            break
    return lines


def rel_link_target(source: Path, link_path: Path) -> str:
    return os.path.relpath(source, start=link_path.parent)


def place_file(source: Path, dest: Path, copy: bool) -> None:
    if dest.exists() or dest.is_symlink():
        return
    if copy:
        shutil.copy2(source, dest)
    else:
        dest.symlink_to(rel_link_target(source, dest))


def yaml_scalar(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def yaml_block_list(items: list[str], indent: int = 2) -> str:
    prefix = " " * indent
    if not items:
        return f"{prefix}[]\n"
    lines: list[str] = []
    for item in items:
        lines.append(f"{prefix}- |")
        for row in item.splitlines() or [""]:
            lines.append(f"{prefix}  {row}")
    return "\n".join(lines) + "\n"


def write_issue_yaml(
    path: Path,
    case_id: str,
    title: str,
    problem_time: str,
    symptom: str,
    robot_behavior: str,
    primary_skill: str,
    data_files: list[Path],
    screenshot_files: list[Path],
    fault_lines: list[str],
) -> None:
    created = dt.datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"case_id: {case_id}",
        f"title: {yaml_scalar(title)}",
        "status: new",
        f"created_at_cst: {yaml_scalar(created)}",
        "",
        "repository:",
        f"  primary_codebase: {PRIMARY_CODEBASE}",
        f"  tools_root: {TOOLS_ROOT}",
        "",
        "problem:",
        f"  problem_time_cst: {yaml_scalar(problem_time or 'TODO')}",
        "  subsystem: TODO",
        "  fault_name: TODO",
        "  fault_id: TODO",
        f"  symptom: {yaml_scalar(symptom or 'TODO')}",
        f"  robot_behavior: {yaml_scalar(robot_behavior or 'TODO')}",
        "  user_observation: TODO",
        "",
        "fault_logs:",
    ]
    content = "\n".join(lines) + "\n"
    content += yaml_block_list(fault_lines)
    content += "\n"
    content += "data:\n"
    if data_files:
        content += "  files:\n"
        for file_path in data_files:
            content += f"    - path: data/{file_path.name}\n"
    else:
        content += "  files: []\n"
    if screenshot_files:
        content += "  screenshots:\n"
        for file_path in screenshot_files:
            content += f"    - screenshots/{file_path.name}\n"
    else:
        content += "  screenshots: []\n"
    content += "  logs:\n"
    content += "    embedded_in_mcap:\n"
    content += "      - /x5/vlog\n"
    content += "      - /s100/vlog\n"
    content += "\n"
    content += "analysis_request:\n"
    content += "  entry_skill: vita-sensor-debug\n"
    content += f"  primary_skill: {primary_skill}\n"
    content += "  supporting_skill: robot-rosbag-log-triage\n"
    content += "  questions:\n"
    content += "    - TODO\n"
    content += "\n"
    content += "known_findings:\n"
    content += "  conclusion_short: TODO\n"
    content += "\n"
    content += "expected_outputs:\n"
    content += "  - reports/triage.md\n"
    path.write_text(content, encoding="utf-8")


def write_triage_stub(path: Path, case_id: str, title: str, primary_skill: str) -> None:
    content = f"""# {title}

## Case

- Case ID: `{case_id}`
- Entry skill: `vita-sensor-debug`
- Routed skill: `{primary_skill}`

## Triage Notes

Run:

```text
用 vita-sensor-debug 分析 debug_cases/{case_id}
```

Then update this report with the timeline, topic evidence, code path, and conclusion.
"""
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    data_files, screenshot_files = collect_inputs(args.inputs)
    text = scan_text(data_files)
    primary_skill, sensor, _ = infer_sensor(" ".join([args.symptom or "", text]), data_files + screenshot_files)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    case_id = args.case_id or f"{timestamp}_{sensor}_issue"
    case_id = slugify(case_id)
    title = args.title or f"{case_id.replace('_', ' ')}"

    case_dir = DEBUG_CASES_ROOT / case_id
    if case_dir.exists() and not args.force:
        print(f"case already exists: {case_dir}", file=sys.stderr)
        return 2

    data_dir = case_dir / "data"
    screenshots_dir = case_dir / "screenshots"
    reports_dir = case_dir / "reports"
    data_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    for source in data_files:
        place_file(source, data_dir / source.name, copy=args.copy)
    for source in screenshot_files:
        place_file(source, screenshots_dir / source.name, copy=args.copy)

    fault_lines = extract_fault_lines(text, args.fault_log)
    write_issue_yaml(
        case_dir / "issue.yaml",
        case_id=case_id,
        title=title,
        problem_time=args.problem_time or "",
        symptom=args.symptom or "",
        robot_behavior=args.robot_behavior or "",
        primary_skill=primary_skill,
        data_files=data_files,
        screenshot_files=screenshot_files,
        fault_lines=fault_lines,
    )
    write_triage_stub(reports_dir / "triage.md", case_id, title, primary_skill)

    print(case_dir)
    print(f"data_files={len(data_files)} screenshots={len(screenshot_files)} primary_skill={primary_skill}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
