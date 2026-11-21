import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ims


class ReportExportTests(unittest.TestCase):
    def test_concurrent_exports_preserve_each_report(self):
        service = ims.ReportService()
        inputs = [[], [{"item": "Fish"}], [{"item": "Sausage"}]]
        with tempfile.TemporaryDirectory() as directory, patch.object(
            ims, "REPORT_DIR", Path(directory)
        ), patch.object(ims, "datetime") as clock:
            clock.now.return_value = datetime(2026, 11, 21, 12, 30)
            with ThreadPoolExecutor(max_workers=3) as workers:
                paths = list(workers.map(service.write_csv, inputs, ["inventory"] * 3))
            self.assertEqual(len(set(paths)), 3)
            self.assertIn("inventory_20261121_123000.csv", [p.name for p in paths])
            self.assertEqual(paths[0].read_text(), "No records\n")
            for path, rows in zip(paths[1:], inputs[1:]):
                with path.open(newline="", encoding="utf-8") as report:
                    self.assertEqual(list(csv.DictReader(report)), rows)

    def test_failed_export_removes_its_partial_file(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            ims, "REPORT_DIR", Path(directory)
        ):
            with self.assertRaises(ValueError):
                ims.ReportService().write_csv([{"item": "Fish"}, {"other": "test"}], "inventory")
            self.assertEqual(list(Path(directory).iterdir()), [])
