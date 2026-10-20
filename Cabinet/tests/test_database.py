import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from cabinet.database import CabinetStore


class CabinetStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = CabinetStore(Path(self.temp_dir.name) / "cabinet.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_medicine_stock_history_and_search(self):
        medicine_id = self.store.add_medicine(
            "Allergy relief", 8, 3, strength="10 mg", expiry_date="2030-08-01"
        )
        self.assertEqual(self.store.change_stock(medicine_id, -5, "Used"), 3)
        self.assertEqual(len(self.store.stock_history(medicine_id)), 2)
        self.assertEqual(self.store.list_medicines("allergy")[0]["quantity"], 3)

    def test_rejects_negative_stock_and_invalid_date(self):
        medicine_id = self.store.add_medicine("Bandages", 1)
        with self.assertRaisesRegex(ValueError, "zero"):
            self.store.change_stock(medicine_id, -2)
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            self.store.add_medicine("Syrup", 2, expiry_date="tomorrow")

    def test_medicine_expiry_is_optional_persisted_and_editable(self):
        medicine_id = self.store.add_medicine("Tablets", 10)
        medicine = self.store.list_medicines()[0]
        self.assertEqual(medicine["expiry_date"], "")

        self.store.update_medicine(medicine_id, expiry_date="2031-04-15")
        self.assertEqual(self.store.list_medicines()[0]["expiry_date"], "2031-04-15")

        self.store.update_medicine(medicine_id, expiry_date="")
        self.assertEqual(self.store.list_medicines()[0]["expiry_date"], "")

    def test_rejects_noncanonical_or_impossible_expiry_dates(self):
        for expiry_date in ("20310203", "2031-02-30"):
            with self.subTest(expiry_date=expiry_date):
                with self.assertRaisesRegex(ValueError, "valid date.*YYYY-MM-DD"):
                    self.store.add_medicine("Tablets", 10, expiry_date=expiry_date)

    def test_dashboard_low_stock_expiry_and_due_dates(self):
        today = date(2030, 1, 1)
        self.store.add_medicine(
            "Cough syrup",
            2,
            low_stock_threshold=3,
            expiry_date=(today + timedelta(days=10)).isoformat(),
        )
        self.store.add_vaccine(
            "Sam",
            "Recorded vaccine",
            administered_on="2029-01-01",
            next_due_on=(today + timedelta(days=20)).isoformat(),
        )
        self.store.add_appointment(
            "Clinic visit", (today + timedelta(days=3)).isoformat(), "Sam"
        )
        dashboard = self.store.dashboard(today)
        self.assertEqual(dashboard["medicine_count"], 1)
        self.assertEqual(len(dashboard["low_stock"]), 1)
        self.assertEqual(len(dashboard["expiring"]), 1)
        self.assertEqual(dashboard["upcoming"][0]["title"], "Clinic visit")

    def test_dashboard_includes_past_expiry_as_an_alert(self):
        today = date(2030, 1, 1)
        self.store.add_medicine(
            "Past date item",
            1,
            expiry_date=(today - timedelta(days=2)).isoformat(),
        )
        dashboard = self.store.dashboard(today)
        self.assertEqual([item["name"] for item in dashboard["expiring"]], ["Past date item"])

    def test_empty_stock_is_a_low_stock_alert_even_at_zero_threshold(self):
        self.store.add_medicine("Out of stock", 0)
        dashboard = self.store.dashboard(date(2030, 1, 1))
        self.assertEqual([item["name"] for item in dashboard["low_stock"]], ["Out of stock"])

    def test_records_settings_exports_and_backup(self):
        self.store.add_medicine("Vitamin bottle", 12)
        self.store.add_vaccine("Rae", "Recorded entry")
        self.store.add_appointment("Reminder", "2030-05-10", kind="Medicine")
        self.store.set_setting("theme", "dark")
        self.assertEqual(self.store.get_setting("theme"), "dark")

        export_path = Path(self.temp_dir.name) / "export.json"
        self.store.export_json(export_path)
        self.assertEqual(len(json.loads(export_path.read_text())["medicines"]), 1)

        backup_path = Path(self.temp_dir.name) / "backup.sqlite3"
        self.store.create_backup(backup_path)
        self.assertTrue(backup_path.exists())
        restored = CabinetStore(backup_path)
        self.assertEqual(len(restored.list_vaccines()), 1)


if __name__ == "__main__":
    unittest.main()
