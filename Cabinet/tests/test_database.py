import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
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

    def test_medicine_has_in_app_dose_schedule_through_end_date(self):
        start = date.today() + timedelta(days=2)
        end = start + timedelta(days=1)
        medicine_id = self.store.add_medicine(
            "Daily medicine",
            10,
            schedule_start_date=start.isoformat(),
            schedule_end_date=end.isoformat(),
            schedule_times=["08:00", "20:00"],
        )

        reminders = self.store.list_dose_reminders_between(start, end)
        self.assertEqual(len(reminders), 4)
        self.assertTrue(all(item["id"] < 0 for item in reminders))
        self.assertTrue(all(item["medicine_id"] == medicine_id for item in reminders))
        self.assertEqual(
            [item["due_at"][11:16] for item in reminders],
            ["08:00", "20:00", "08:00", "20:00"],
        )
        upcoming = self.store.list_upcoming_doses(
            now=datetime.combine(start, datetime.min.time())
        )
        self.assertTrue(all(item["id"] < 0 for item in upcoming))
        self.assertEqual(len(upcoming), 4)

    def test_existing_in_app_dose_can_be_snoozed_and_marked_taken(self):
        start = date.today() + timedelta(days=2)
        medicine_id = self.store.add_medicine(
            "Dose medicine",
            1,
            schedule_start_date=start.isoformat(),
            schedule_end_date=start.isoformat(),
            schedule_times=["08:00"],
        )
        reminder = self.store.list_dose_reminders_between(start, start)[0]
        now = datetime.fromisoformat(reminder["due_at"]) - timedelta(minutes=5)

        self.store.update_dose_reminder(reminder["id"], "snoozed", now)
        snoozed = self.store.list_dose_reminders_between(start, start)[0]
        self.assertEqual(
            snoozed["snoozed_until"],
            (now + timedelta(minutes=15)).isoformat(),
        )
        self.store.update_dose_reminder(snoozed["id"], "taken", now)

        history = self.store.dose_history()
        self.assertEqual(history[0]["status"], "taken")
        self.assertEqual(history[0]["name"], "Dose medicine")
        self.assertEqual(self.store.list_medicines()[0]["id"], medicine_id)

    def test_invalid_in_app_dose_schedule_does_not_create_medicine(self):
        today = date.today()
        invalid_schedules = (
            (today, today, [], "at least one dose time"),
            (today, today, ["25:00"], "24-hour HH:MM"),
            (today, today - timedelta(days=1), ["08:00"], "cannot be before"),
        )
        for start, end, times, error in invalid_schedules:
            with self.subTest(start=start, end=end, times=times):
                with self.assertRaisesRegex(ValueError, error):
                    self.store.add_medicine(
                        "Invalid schedule",
                        1,
                        schedule_start_date=start.isoformat(),
                        schedule_end_date=end.isoformat(),
                        schedule_times=times,
                    )
        self.assertEqual(self.store.list_medicines(), [])

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
