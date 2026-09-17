#!/usr/bin/env python3
"""Exercise the real serial statistics and CSV logger without opening a device."""
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from SerialHandlerStandalone import CSVLogger, RangingStats, SerialHandler


class LoggingTest(unittest.TestCase):
    def test_stats_and_csv(self):
        stats = RangingStats()
        with patch('SerialHandlerStandalone.time.monotonic', side_effect=[1., 1.05, 1.1]):
            for _ in range(3):
                stats.update(1.25, 10, 20, [-80, -81])
        self.assertAlmostEqual(stats.fps(), 20)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'sample.csv'
            logger = CSVLogger(str(path))
            logger.log(1.25, 10, 20, stats.fps(), [-80, -81])
            logger.close()
            with path.open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertEqual(float(rows[0]['distance_m']), 1.25)
            self.assertEqual(rows[0]['rssi'], '-80,-81')

    def test_passive_handler_cannot_send(self):
        handler = SerialHandler(enable_csv=False)
        with self.assertRaises(PermissionError):
            handler.sendCmd(b'configuration')
        handler.stop()
        handler.stop()


if __name__ == '__main__':
    unittest.main()
