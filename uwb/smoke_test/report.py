"""
报告生成：终端输出 + JSON 文件。
"""

import json
import os
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from enum import Enum


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    detail: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class SmokeTestReport:
    mode: str = ""
    timestamp: str = ""
    anchor_version: str = "unknown"
    tag_version: str = "unknown"
    results: List[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult):
        self.results.append(result)

    @property
    def summary(self) -> dict:
        counts = {s: 0 for s in CheckStatus}
        for r in self.results:
            counts[r.status] += 1
        return counts

    def print_report(self):
        ts = self.timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        w = 56

        print()
        print("=" * w)
        print("  UWB 固件冒烟测试报告")
        print(f"  日期: {ts}")
        print(f"  模式: {self.mode}")
        print(f"  Anchor FW: {self.anchor_version}  |  Tag FW: {self.tag_version}")
        print("=" * w)
        print()
        print(f" {'#':>2}  {'检查项':<22} {'状态':<10} {'详情'}")
        print("-" * w)

        status_icons = {
            CheckStatus.PASS: "✅ PASS",
            CheckStatus.FAIL: "❌ FAIL",
            CheckStatus.WARN: "⚠️  WARN",
            CheckStatus.SKIP: "⏭️  SKIP",
        }

        for i, r in enumerate(self.results, 1):
            icon = status_icons.get(r.status, r.status.value)
            print(f" {i:>2}  {r.name:<22} {icon:<10} {r.detail}")

        print()
        print("=" * w)
        s = self.summary
        parts = []
        if s[CheckStatus.PASS]:
            parts.append(f"{s[CheckStatus.PASS]} PASS")
        if s[CheckStatus.WARN]:
            parts.append(f"{s[CheckStatus.WARN]} WARN")
        if s[CheckStatus.FAIL]:
            parts.append(f"{s[CheckStatus.FAIL]} FAIL")
        if s[CheckStatus.SKIP]:
            parts.append(f"{s[CheckStatus.SKIP]} SKIP")
        print(f"  总结: {', '.join(parts)}")
        overall = "PASS" if s[CheckStatus.FAIL] == 0 else "FAIL"
        print(f"  整体结果: {overall}")
        print("=" * w)
        print()

    def save_json(self, output_dir: str = ".") -> str:
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"smoke_test_report_{ts}.json"
        filepath = os.path.join(output_dir, filename)

        report_dict = {
            "mode": self.mode,
            "timestamp": self.timestamp,
            "anchor_version": self.anchor_version,
            "tag_version": self.tag_version,
            "results": [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "detail": r.detail,
                    "data": r.data,
                }
                for r in self.results
            ],
            "summary": {k.value: v for k, v in self.summary.items()},
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, ensure_ascii=False, indent=2)

        return filepath
