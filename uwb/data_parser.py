"""
uwb/data_parser.py — Parser for UWB (Ultra-Wideband) positioning CSV logs.

Expected CSV columns:
    timestamp, tag_id, x, y, z [, quality]
"""

import csv
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from common.base_parser import BaseDataParser


@dataclass
class UWBRecord:
    """One UWB ranging / positioning measurement."""

    timestamp: float
    tag_id: str
    x: float
    y: float
    z: float
    quality: Optional[float] = field(default=None)   # RSSI or CIR quality metric


class UWBDataParser(BaseDataParser):
    """Parse UWB positioning logs from a CSV file."""

    def parse_csv(self, filepath: str) -> List[UWBRecord]:
        """Read *filepath* and return a list of :class:`UWBRecord`."""
        records: List[UWBRecord] = []
        with open(filepath, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                records.append(
                    UWBRecord(
                        timestamp=float(row["timestamp"]),
                        tag_id=row["tag_id"].strip(),
                        x=float(row["x"]),
                        y=float(row["y"]),
                        z=float(row["z"]),
                        quality=float(row["quality"]) if "quality" in row else None,
                    )
                )
        return records

    def group_by_tag(self, records: List[UWBRecord]) -> Dict[str, List[UWBRecord]]:
        """Return a dict mapping tag_id → list of :class:`UWBRecord`."""
        groups: Dict[str, List[UWBRecord]] = {}
        for rec in records:
            groups.setdefault(rec.tag_id, []).append(rec)
        return groups
