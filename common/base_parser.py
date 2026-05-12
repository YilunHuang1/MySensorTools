"""
common/base_parser.py — Abstract base class for sensor data parsers.
"""

from abc import ABC, abstractmethod
from typing import Any, List


class BaseDataParser(ABC):
    """All sensor data parsers inherit from this class.

    Sub-classes must implement :meth:`parse_csv`.  They may additionally
    override :meth:`parse_file` for format-specific binary/text formats.
    """

    @abstractmethod
    def parse_csv(self, filepath: str) -> List[Any]:
        """Parse a CSV file and return a list of sensor records."""

    def parse_file(self, filepath: str) -> List[Any]:
        """Parse an arbitrary file.  Default implementation delegates to
        :meth:`parse_csv`; sub-classes may override for other formats."""
        return self.parse_csv(filepath)


class BaseDiagnoser(ABC):
    """All sensor diagnosers inherit from this class."""

    @abstractmethod
    def diagnose(self, data: Any) -> List[str]:
        """Analyse *data* and return a list of fault description strings.

        An empty list means no faults were detected.
        """
