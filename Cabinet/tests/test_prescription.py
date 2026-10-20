import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from cabinet.database import CabinetStore
from cabinet.prescription_scanner import (
    extract_medicines,
    prescription_fingerprint,
)


class PrescriptionExtractionTests(unittest.TestCase):
    def test_extracts_explicit_text_as_unconfirmed_suggestions(self):
        medicines = extract_medicines(
            "Amoxicillin 500 mg take 1 capsule twice daily for 7 days "
            "after food Qty 14"
        )
        self.assertEqual(len(medicines), 1)
        medicine = medicines[0]
        self.assertEqual(medicine["name"], "Amoxicillin")
        self.assertEqual(medicine["strength"], "500 mg")
        self.assertEqual(medicine["dose"], "1 capsule")
        self.assertEqual(medicine["frequency"], "twice daily")
        self.assertEqual(medicine["duration_days"], "7")
        self.assertEqual(medicine["instructions"], "after food")
        self.assertEqual(medicine["prescribed_quantity"], "14")
        self.assertFalse(medicine["confirmed"])
        self.assertEqual(medicine["reminder_times"], "")

    def test_fingerprint_ignores_user_selected_reminder_times(self):
        item = {
            "name": "Medicine",
            "dose": "1 tablet",
            "frequency": "twice daily",
            "reminder_times": "08:00, 20:00",
        }
        edited_times = {**item, "reminder_times": "09:00, 21:00"}
        self.assertEqual(
            prescription_fingerprint([item]),
            prescription_fingerprint([edited_times]),
        )

    def test_does_not_infer_unclear_frequency(self):
        medicines = extract_medicines(
            "Medicine Example 250 mg\nTake 1 tablet with food"
        )
        self.assertEqual(len(medicines), 1)
        self.assertEqual(medicines[0]["name"], "Medicine Example")
        self.assertEqual(medicines[0]["frequency"], "")

    def test_extracts_explicit_clock_times_without_inventing_other_times(self):
        medicine = extract_medicines(
            "Medicine Example 250 mg take 1 tablet twice daily at 8 AM and 8:00 PM"
        )[0]
        self.assertEqual(medicine["reminder_times"], "08:00, 20:00")

    def test_keeps_adjacent_medicine_lines_in_separate_review_cards(self):
        medicines = extract_medicines(
            "Metformin 500 mg\n"
            "Take 1 tablet twice daily for 7 days\n"
            "Atorvastatin 20 mg\n"
            "Take 1 tablet at night"
        )
        self.assertEqual(len(medicines), 2)
        self.assertEqual(medicines[0]["name"], "Metformin")
        self.assertEqual(medicines[0]["frequency"], "twice daily")
        self.assertEqual(medicines[1]["name"], "Atorvastatin")
        self.assertEqual(medicines[1]["frequency"], "")


class PrescriptionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = CabinetStore(Path(self.temp_dir.name) / "cabinet.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _item(self, **changes):
        item = {
            "name": "Amoxicillin",
            "strength": "500 mg",
            "dose": "1 capsule",
            "frequency": "twice daily",
            "instructions": "after food",
            "start_date": "2030-01-01",
            "duration_days": "7",
            "prescribed_quantity": "14",
            "reminder_times": ["08:00", "20:00"],
            "create_reminders": True,
            "confirmed": True,
            "purchased": False,
            "purchased_quantity": "",
        }
        item.update(changes)
        return item

    def test_new_inventory_starts_at_zero_and_prescription_stock_is_not_assumed(self):
        result = self.store.confirm_prescription(
            [self._item()], "fingerprint-one", "raw OCR text", "image-hash"
        )
        medicine = self.store.list_medicines()[0]
        self.assertFalse(result["duplicate"])
        self.assertEqual(medicine["quantity"], 0)
        self.assertEqual(self.store.stock_history(medicine["id"])[0]["quantity_after"], 0)
        self.assertEqual(len(self.store.list_prescription_items()), 1)
        self.assertEqual(len(self.store.list_upcoming_doses(datetime(2030, 1, 1))), 14)

    def test_existing_stock_changes_only_for_confirmed_purchase_amount(self):
        medicine_id = self.store.add_medicine(
            "amoxicillin", 3, strength="500MG"
        )
        item = self._item(inventory_id=medicine_id, purchased=True, purchased_quantity="4")
        self.store.confirm_prescription([item], "fingerprint-purchased")
        medicine = self.store.list_medicines()[0]
        self.assertEqual(medicine["quantity"], 7)
        self.assertEqual(self.store.stock_history(medicine_id)[0]["note"],
                         "Purchased from confirmed prescription")

    def test_unconfirmed_or_ambiguous_schedule_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Confirm each medicine"):
            self.store.confirm_prescription(
                [self._item(confirmed=False)], "unconfirmed"
            )
        with self.assertRaisesRegex(ValueError, "exactly 2 local reminder time"):
            self.store.confirm_prescription(
                [self._item(reminder_times=["08:00"])], "missing-time"
            )
        self.assertEqual(self.store.list_medicines(), [])

    def test_unpurchased_quantity_cannot_be_added_to_stock(self):
        with self.assertRaisesRegex(ValueError, "Mark .* as purchased"):
            self.store.confirm_prescription(
                [self._item(purchased=False, purchased_quantity="2")],
                "not-purchased",
            )
        self.assertEqual(self.store.list_medicines(), [])

    def test_every_hours_frequency_requires_matching_clock_intervals(self):
        with self.assertRaisesRegex(ValueError, "must be 8 hours apart"):
            self.store.confirm_prescription(
                [self._item(frequency="every 8 hours",
                            reminder_times=["08:00", "12:00", "20:00"])],
                "invalid-intervals",
            )
        saved = self.store.confirm_prescription(
            [self._item(frequency="every 8 hours",
                        reminder_times=["00:00", "08:00", "16:00"])],
            "valid-intervals",
        )
        self.assertFalse(saved["duplicate"])

    def test_duplicate_prescription_does_not_repeat_stock_or_reminders(self):
        item = self._item(purchased=True, purchased_quantity="5")
        fingerprint = prescription_fingerprint([item])
        first = self.store.confirm_prescription([item], fingerprint)
        second = self.store.confirm_prescription(
            [self._item(purchased=True, purchased_quantity="9")], fingerprint
        )
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(self.store.list_medicines()[0]["quantity"], 5)
        self.assertEqual(len(self.store.list_upcoming_doses(datetime(2030, 1, 1))), 14)

    def test_duplicate_can_add_missing_reminders_without_repeating_stock(self):
        without_reminders = self._item(
            create_reminders=False,
            purchased=True,
            purchased_quantity="5",
        )
        fingerprint = prescription_fingerprint([without_reminders])
        self.store.confirm_prescription([without_reminders], fingerprint)

        with_reminders = self._item(
            reminder_times=["09:00", "21:00"],
            purchased=True,
            purchased_quantity="8",
        )
        result = self.store.confirm_prescription(
            [with_reminders],
            prescription_fingerprint([with_reminders]),
        )
        self.assertTrue(result["duplicate"])
        self.assertTrue(result["reminders_added"])
        self.assertEqual(self.store.list_medicines()[0]["quantity"], 5)
        self.assertEqual(len(self.store.list_upcoming_doses(datetime(2030, 1, 1))), 14)

    def test_normalized_inventory_match_and_dose_actions(self):
        medicine_id = self.store.add_medicine("Amoxicillin", 2, strength="500 mg")
        self.assertEqual(
            self.store.matching_medicines(" amoxicillin ", "500MG")[0]["id"],
            medicine_id,
        )
        self.store.confirm_prescription(
            [self._item(inventory_id=medicine_id)], "dose-actions"
        )
        now = datetime(2030, 1, 1, 7, 55)
        upcoming = self.store.list_upcoming_doses(now)
        self.assertEqual(upcoming[0]["due_at"], "2030-01-01T08:00:00")
        self.store.update_dose_reminder(upcoming[0]["id"], "snoozed", now)
        snoozed = self.store.list_upcoming_doses(now)[0]
        self.assertEqual(
            snoozed["snoozed_until"],
            (now + timedelta(minutes=15)).isoformat(),
        )
        self.store.update_dose_reminder(snoozed["id"], "taken", now)
        self.assertEqual(self.store.dose_history()[0]["status"], "taken")

    def test_old_pending_doses_are_recorded_as_missed(self):
        self.store.confirm_prescription([self._item()], "missed-history")
        self.store.list_upcoming_doses(datetime(2030, 1, 1, 9, 0))
        history = self.store.dose_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "missed")

    def test_confirmation_does_not_mark_preexisting_doses_as_missed(self):
        past_start = (date.today() - timedelta(days=2)).isoformat()
        self.store.confirm_prescription(
            [self._item(start_date=past_start, duration_days="1")],
            "confirmed-after-course",
        )
        self.assertEqual(self.store.list_upcoming_doses(), [])
        self.assertEqual(self.store.dose_history(), [])

    def test_missing_duration_or_start_date_blocks_reminder_creation(self):
        with self.assertRaisesRegex(ValueError, "start date"):
            self.store.confirm_prescription(
                [self._item(start_date="")], "missing-start"
            )
        with self.assertRaisesRegex(ValueError, "prescribed duration"):
            self.store.confirm_prescription(
                [self._item(duration_days="")], "missing-duration"
            )
        self.assertEqual(self.store.list_medicines(), [])


if __name__ == "__main__":
    unittest.main()
