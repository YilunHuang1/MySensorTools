#!/usr/bin/env python3
"""Analyze ROS2 sensor_msgs/Imu topics in an MCAP file.

This script intentionally avoids ros2 CLI and mcap_ros2 dependencies. It reads
MCAP records with the Python mcap package and decodes sensor_msgs/msg/Imu CDR
payloads directly.
"""

from __future__ import annotations

import argparse
import math
import struct
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable

from mcap.reader import make_reader


CST = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class ImuSample:
    topic: str
    log_time_ns: int
    header_time_ns: int
    frame_id: str
    acceleration: tuple[float, float, float]
    angular_velocity: tuple[float, float, float]

    @property
    def acc_norm(self) -> float:
        return math.sqrt(sum(axis * axis for axis in self.acceleration))


@dataclass(frozen=True)
class LogRecord:
    topic: str
    log_time_ns: int
    stamp_ns: int
    level: int
    name: str
    message: str
    file: str
    function: str
    line: int


def _align_from_payload(offset: int, alignment: int, base: int = 4) -> int:
    """Align CDR fields relative to the 4-byte encapsulation header."""
    return base + (((offset - base) + alignment - 1) & ~(alignment - 1))


def _read_cdr_string(data: bytes, offset: int, base: int = 4) -> tuple[str, int]:
    offset = _align_from_payload(offset, 4, base)
    (length,) = struct.unpack_from("<I", data, offset)
    offset += 4
    value = data[offset : offset + length].rstrip(b"\x00").decode("utf-8", "replace")
    return value, offset + length


def parse_imu_cdr(data: bytes) -> tuple[int, str, tuple[float, float, float], tuple[float, float, float]]:
    """Decode fields needed from sensor_msgs/msg/Imu CDR bytes.

    Returns header timestamp ns, frame_id, angular_velocity, linear_acceleration.
    """
    base = 4
    offset = base

    sec, nanosec = struct.unpack_from("<iI", data, offset)
    offset += 8

    offset = _align_from_payload(offset, 4, base)
    (frame_len,) = struct.unpack_from("<I", data, offset)
    offset += 4
    frame_id = data[offset : offset + frame_len].rstrip(b"\x00").decode("utf-8", "replace")
    offset += frame_len

    offset = _align_from_payload(offset, 8, base)
    offset += 32  # orientation

    offset = _align_from_payload(offset, 8, base)
    offset += 72  # orientation_covariance

    offset = _align_from_payload(offset, 8, base)
    angular_velocity = struct.unpack_from("<3d", data, offset)
    offset += 24

    offset = _align_from_payload(offset, 8, base)
    offset += 72  # angular_velocity_covariance

    offset = _align_from_payload(offset, 8, base)
    linear_acceleration = struct.unpack_from("<3d", data, offset)

    header_time_ns = sec * 1_000_000_000 + nanosec
    return header_time_ns, frame_id, angular_velocity, linear_acceleration


def log_level_name(level: int) -> str:
    return {
        10: "DEBUG",
        20: "INFO",
        30: "WARN",
        40: "ERROR",
        50: "FATAL",
    }.get(level, str(level))


def parse_log_cdr(data: bytes) -> tuple[int, int, str, str, str, str, int] | None:
    """Decode rcl_interfaces/msg/Log CDR bytes."""
    try:
        base = 4
        offset = base
        sec, nanosec = struct.unpack_from("<iI", data, offset)
        offset += 8
        (level,) = struct.unpack_from("<B", data, offset)
        offset += 1
        name, offset = _read_cdr_string(data, offset, base)
        message, offset = _read_cdr_string(data, offset, base)
        file, offset = _read_cdr_string(data, offset, base)
        function, offset = _read_cdr_string(data, offset, base)
        offset = _align_from_payload(offset, 4, base)
        (line,) = struct.unpack_from("<I", data, offset)
    except (struct.error, UnicodeDecodeError):
        return None

    stamp_ns = sec * 1_000_000_000 + nanosec
    return stamp_ns, level, name, message, file, function, line


def parse_cst_time(value: str) -> int:
    normalized = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y%m%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y%m%d %H:%M:%S"):
        try:
            return int(datetime.strptime(normalized, fmt).replace(tzinfo=CST).timestamp() * 1e9)
        except ValueError:
            pass
    raise ValueError(f"unsupported time format: {value!r}")


def format_cst(ns: int) -> str:
    return datetime.fromtimestamp(ns / 1e9, tz=CST).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, round((len(sorted_values) - 1) * pct / 100))
    return sorted_values[index]


def iter_imu_samples(
    mcap_path: Path,
    topics: Iterable[str] | None = None,
    start_time_ns: int | None = None,
    end_time_ns: int | None = None,
) -> Iterable[ImuSample]:
    with mcap_path.open("rb") as stream:
        reader = make_reader(stream)
        for _schema, channel, message in reader.iter_messages(
            topics=topics,
            start_time=start_time_ns,
            end_time=end_time_ns,
        ):
            header_ns, frame_id, angular_velocity, acceleration = parse_imu_cdr(message.data)
            yield ImuSample(
                topic=channel.topic,
                log_time_ns=message.log_time,
                header_time_ns=header_ns,
                frame_id=frame_id,
                acceleration=acceleration,
                angular_velocity=angular_velocity,
            )


def iter_log_records(
    mcap_path: Path,
    topics: Iterable[str] | None = None,
    start_time_ns: int | None = None,
    end_time_ns: int | None = None,
) -> Iterable[LogRecord]:
    with mcap_path.open("rb") as stream:
        reader = make_reader(stream)
        for _schema, channel, message in reader.iter_messages(
            topics=topics,
            start_time=start_time_ns,
            end_time=end_time_ns,
        ):
            parsed = parse_log_cdr(message.data)
            if parsed is None:
                continue
            stamp_ns, level, name, log_message, file, function, line = parsed
            yield LogRecord(
                topic=channel.topic,
                log_time_ns=message.log_time,
                stamp_ns=stamp_ns,
                level=level,
                name=name,
                message=log_message,
                file=file,
                function=function,
                line=line,
            )


def list_topics(mcap_path: Path) -> int:
    with mcap_path.open("rb") as stream:
        reader = make_reader(stream)
        summary = reader.get_summary()
        if not summary:
            print("No MCAP summary found.")
            return 1

        print("Channels:")
        for channel_id, channel in sorted(summary.channels.items()):
            schema = summary.schemas.get(channel.schema_id) if summary.schemas else None
            schema_name = schema.name if schema else str(channel.schema_id)
            count = summary.statistics.channel_message_counts.get(channel_id, 0) if summary.statistics else 0
            print(f"{channel_id:3d} {channel.topic:36s} {schema_name:28s} {count}")

        if summary.statistics:
            start = summary.statistics.message_start_time
            end = summary.statistics.message_end_time
            print(f"\nRange CST: {format_cst(start)} -> {format_cst(end)}")
            print(f"Messages: {summary.statistics.message_count}")
    return 0


def analyze(args: argparse.Namespace) -> int:
    mcap_path = Path(args.mcap)
    topics = args.topics.split(",")
    start_ns = parse_cst_time(args.start) if args.start else None
    end_ns = parse_cst_time(args.end) if args.end else None

    if args.center:
        center_ns = parse_cst_time(args.center)
        window_ns = int(args.window_seconds * 1e9)
        start_ns = center_ns - window_ns
        end_ns = center_ns + window_ns

    for topic in topics:
        samples = list(iter_imu_samples(mcap_path, [topic], start_ns, end_ns))
        if not samples:
            print(f"\n{topic}: no samples")
            continue

        norms = [sample.acc_norm for sample in samples]
        bad = [sample for sample in samples if sample.acc_norm < args.min_norm or sample.acc_norm > args.max_norm]
        print(f"\n{topic}")
        print(f"  samples: {len(samples)}")
        print(
            "  norm: "
            f"min={min(norms):.6f} p1={percentile(norms, 1):.6f} "
            f"p5={percentile(norms, 5):.6f} p50={percentile(norms, 50):.6f} "
            f"p95={percentile(norms, 95):.6f} p99={percentile(norms, 99):.6f} "
            f"max={max(norms):.6f}"
        )
        print(f"  bad_count: {len(bad)} using [{args.min_norm}, {args.max_norm}]")

        for label, sample in (("min", min(samples, key=lambda item: item.acc_norm)), ("max", max(samples, key=lambda item: item.acc_norm))):
            print_sample(f"  {label}", sample)

        if args.center:
            center_ns = parse_cst_time(args.center)
            nearest = sorted(samples, key=lambda item: abs(item.log_time_ns - center_ns))[: args.nearest]
            print(f"  nearest_to_center:")
            for sample in nearest:
                print_sample("   ", sample)

        if bad:
            print(f"  first_bad:")
            for sample in bad[: args.bad_limit]:
                print_sample("   ", sample)

    if args.include_logs:
        print_logs(args, mcap_path, start_ns, end_ns)

    return 0


def logs(args: argparse.Namespace) -> int:
    mcap_path = Path(args.mcap)
    start_ns = parse_cst_time(args.start) if args.start else None
    end_ns = parse_cst_time(args.end) if args.end else None

    if args.center:
        center_ns = parse_cst_time(args.center)
        window_ns = int(args.window_seconds * 1e9)
        start_ns = center_ns - window_ns
        end_ns = center_ns + window_ns

    print_logs(args, mcap_path, start_ns, end_ns)
    return 0


def print_logs(
    args: argparse.Namespace,
    mcap_path: Path,
    start_ns: int | None,
    end_ns: int | None,
) -> None:
    log_topics = args.log_topics.split(",")
    keywords = [item for item in (args.log_keywords or "").split(",") if item]
    records = list(iter_log_records(mcap_path, log_topics, start_ns, end_ns))

    if keywords:
        lowered = [item.lower() for item in keywords]
        records = [
            record
            for record in records
            if any(keyword in record.message.lower() or keyword in record.name.lower() for keyword in lowered)
        ]

    records.sort(key=lambda record: (record.stamp_ns, record.topic, record.log_time_ns))
    if args.log_limit > 0:
        records = records[: args.log_limit]

    print("\nlogs")
    print(f"  topics: {','.join(log_topics)}")
    print(f"  records: {len(records)}")
    if keywords:
        print(f"  keywords: {','.join(keywords)}")

    for record in records:
        print_log_record("   ", record)


def print_sample(prefix: str, sample: ImuSample) -> None:
    ax, ay, az = sample.acceleration
    gx, gy, gz = sample.angular_velocity
    print(
        f"{prefix} log={format_cst(sample.log_time_ns)} "
        f"header={format_cst(sample.header_time_ns)} frame={sample.frame_id} "
        f"acc=({ax:.6f},{ay:.6f},{az:.6f}) norm={sample.acc_norm:.6f} "
        f"gyr=({gx:.6f},{gy:.6f},{gz:.6f})"
    )


def print_log_record(prefix: str, record: LogRecord) -> None:
    location = ""
    if record.file:
        location = f" {record.file}:{record.line}"
    print(
        f"{prefix}{record.topic} stamp={format_cst(record.stamp_ns)} "
        f"log={format_cst(record.log_time_ns)} [{log_level_name(record.level)}] "
        f"[{record.name}]{location} {record.message}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    topics_parser = subparsers.add_parser("topics", help="List MCAP channels and message counts")
    topics_parser.add_argument("mcap")
    topics_parser.set_defaults(func=lambda args: list_topics(Path(args.mcap)))

    analyze_parser = subparsers.add_parser("analyze", help="Analyze sensor_msgs/Imu topics")
    analyze_parser.add_argument("mcap")
    analyze_parser.add_argument("--topics", default="/imu_raw,/imu_raw_x5,/lidar_imu")
    analyze_parser.add_argument("--start", help="CST start time, e.g. '2026-05-13 14:24:52.240'")
    analyze_parser.add_argument("--end", help="CST end time, e.g. '2026-05-13 14:24:56.240'")
    analyze_parser.add_argument("--center", help="CST center time; overrides --start/--end with --window-seconds")
    analyze_parser.add_argument("--window-seconds", type=float, default=2.0)
    analyze_parser.add_argument("--min-norm", type=float, default=0.1)
    analyze_parser.add_argument("--max-norm", type=float, default=50.0)
    analyze_parser.add_argument("--nearest", type=int, default=12)
    analyze_parser.add_argument("--bad-limit", type=int, default=20)
    analyze_parser.add_argument("--include-logs", action=argparse.BooleanOptionalAction, default=True)
    analyze_parser.add_argument("--log-topics", default="/x5/vlog,/s100/vlog")
    analyze_parser.add_argument("--log-keywords", default="")
    analyze_parser.add_argument("--log-limit", type=int, default=80)
    analyze_parser.set_defaults(func=analyze)

    logs_parser = subparsers.add_parser("logs", help="Decode rcl_interfaces/msg/Log topics")
    logs_parser.add_argument("mcap")
    logs_parser.add_argument("--start", help="CST start time")
    logs_parser.add_argument("--end", help="CST end time")
    logs_parser.add_argument("--center", help="CST center time; overrides --start/--end with --window-seconds")
    logs_parser.add_argument("--window-seconds", type=float, default=2.0)
    logs_parser.add_argument("--log-topics", default="/x5/vlog,/s100/vlog")
    logs_parser.add_argument("--log-keywords", default="")
    logs_parser.add_argument("--log-limit", type=int, default=120)
    logs_parser.set_defaults(func=logs)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
