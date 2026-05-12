"""
common/log_parser.py — Generic sensor log file parser.

Supports plain-text log files with lines in the format:
    [TIMESTAMP] [LEVEL] [SENSOR] message
or simpler:
    TIMESTAMP LEVEL message

Example line:
    2024-01-15 10:23:45.123 ERROR  LiDAR  Ring 3 data missing
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LogEntry:
    """A single parsed log record."""

    timestamp: str
    level: str
    sensor: Optional[str]
    message: str
    raw: str = field(repr=False)


# Patterns tried in order; first match wins.
_PATTERNS = [
    # [2024-01-15 10:23:45.123] [ERROR] [LiDAR] Ring 3 data missing
    re.compile(
        r"\[(?P<ts>[^\]]+)\]\s*\[(?P<level>[^\]]+)\]\s*\[(?P<sensor>[^\]]+)\]\s*(?P<msg>.*)"
    ),
    # 2024-01-15 10:23:45.123  ERROR  LiDAR  Ring 3 data missing
    re.compile(
        r"(?P<ts>\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+"
        r"(?P<level>DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\s+"
        r"(?P<sensor>\S+)\s+(?P<msg>.*)"
    ),
    # 2024-01-15 10:23:45  ERROR  some message (no sensor field)
    re.compile(
        r"(?P<ts>\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+"
        r"(?P<level>DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\s+"
        r"(?P<msg>.*)"
    ),
]


def _parse_line(line: str) -> Optional[LogEntry]:
    """Try each pattern against *line* and return the first match."""
    for pattern in _PATTERNS:
        m = pattern.match(line.strip())
        if m:
            groups = m.groupdict()
            return LogEntry(
                timestamp=groups["ts"].strip(),
                level=groups["level"].strip().upper(),
                sensor=groups.get("sensor", "").strip() or None,
                message=groups["msg"].strip(),
                raw=line,
            )
    return None


class SensorLogParser:
    """Parse sensor log files and filter entries by level or sensor."""

    # Canonical level order (higher index = higher severity)
    _LEVEL_ORDER = ["DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL", "CRITICAL"]

    def parse_file(self, filepath: str) -> List[LogEntry]:
        """Read *filepath* and return a list of :class:`LogEntry` objects.

        Lines that cannot be parsed are silently skipped.
        """
        entries: List[LogEntry] = []
        with open(filepath, "r", encoding="utf-8") as fh:
            for line in fh:
                entry = _parse_line(line)
                if entry is not None:
                    entries.append(entry)
        return entries

    def parse_text(self, text: str) -> List[LogEntry]:
        """Parse a multi-line string directly (useful for testing)."""
        entries: List[LogEntry] = []
        for line in text.splitlines():
            entry = _parse_line(line)
            if entry is not None:
                entries.append(entry)
        return entries

    def filter_by_level(
        self, entries: List[LogEntry], level: str, min_severity: bool = True
    ) -> List[LogEntry]:
        """Return entries at or above *level* (when *min_severity* is True).

        If *min_severity* is False, return only entries whose level exactly
        matches *level*.
        """
        level = level.upper()
        if not min_severity:
            return [e for e in entries if e.level == level]

        level_idx = self._level_order_index(level)
        return [e for e in entries if self._level_order_index(e.level) >= level_idx]

    def filter_by_sensor(
        self, entries: List[LogEntry], sensor: str
    ) -> List[LogEntry]:
        """Return entries whose sensor field matches *sensor* (case-insensitive)."""
        sensor = sensor.upper()
        return [e for e in entries if e.sensor and e.sensor.upper() == sensor]

    def _level_order_index(self, level: str) -> int:
        level = level.upper()
        # Treat WARN and WARNING identically
        if level == "WARNING":
            level = "WARN"
        try:
            return self._LEVEL_ORDER.index(level)
        except ValueError:
            return -1
