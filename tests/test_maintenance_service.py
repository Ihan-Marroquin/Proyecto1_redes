from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.maintenance_server import MaintenanceService, ToolInputError


class MaintenanceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "maintenance.json"
        self.service = MaintenanceService(self.path)

    def test_lists_and_filters_machines(self) -> None:
        result = self.service.list_machines({"status": "warning"})
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["machines"][0]["machine_id"], "SELL-01")

    def test_checks_spare_part_and_reorder_flag(self) -> None:
        result = self.service.check_spare_part({"query": "COMP-01"})
        self.assertEqual(result["count"], 1)
        self.assertTrue(result["parts"][0]["reorder_recommended"])

    def test_creates_and_closes_work_order(self) -> None:
        created = self.service.create_work_order(
            {
                "machine_id": "SELL-01",
                "issue": "Inspect the sealing resistance.",
                "priority": "high",
            }
        )
        order_id = created["work_order"]["work_order_id"]
        self.assertEqual(created["work_order"]["status"], "open")

        closed = self.service.close_work_order(
            {
                "work_order_id": order_id,
                "resolution": "Resistance inspected and terminals tightened.",
            }
        )
        self.assertEqual(closed["work_order"]["status"], "closed")

    def test_rejects_unknown_machine(self) -> None:
        with self.assertRaises(ToolInputError):
            self.service.get_machine_status({"machine_id": "UNKNOWN"})


if __name__ == "__main__":
    unittest.main()

