import tempfile
import unittest
from datetime import date
from pathlib import Path

from cabinet.cycle import account_database_path
from cabinet.database import CabinetStore
from cabinet.preferences import (
    calculate_age,
    is_menstruation_eligible,
    menstruation_tab_enabled,
    save_setup_preferences,
    validate_date_of_birth,
)


class ProfileSetupTests(unittest.TestCase):
    def test_age_is_calculated_relative_to_the_birthday(self):
        today = date(2030, 5, 10)
        self.assertEqual(calculate_age("2018-05-10", today), 12)
        self.assertEqual(calculate_age("2018-05-11", today), 11)
        self.assertEqual(calculate_age("2000-01-01", today), 30)

    def test_date_of_birth_rejects_future_noncanonical_and_unreasonable_dates(self):
        for value in ("2030-05-11", "20180510", "1900-01-01"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_date_of_birth(value, date(2030, 5, 10))

    def test_tab_eligibility_requires_female_and_age_twelve(self):
        today = date(2030, 5, 10)
        self.assertTrue(is_menstruation_eligible("Female", "2018-05-10", today))
        self.assertFalse(is_menstruation_eligible("Female", "2018-05-11", today))
        self.assertFalse(is_menstruation_eligible("Male", "1990-01-01", today))
        self.assertFalse(
            is_menstruation_eligible(
                "Prefer not to say", "1990-01-01", today
            )
        )

    def test_tab_also_requires_explicit_tracker_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CabinetStore(Path(directory) / "cabinet.sqlite3")
            store.set_setting("gender", "Female")
            store.set_setting("date_of_birth", "2000-01-01")
            self.assertFalse(menstruation_tab_enabled(store, date(2030, 5, 10)))

            store.set_setting("feature_cycle", "true")
            self.assertTrue(menstruation_tab_enabled(store, date(2030, 5, 10)))

            store.set_setting("gender", "Male")
            self.assertFalse(menstruation_tab_enabled(store, date(2030, 5, 10)))

    def test_profile_is_saved_once_and_existing_profile_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CabinetStore(Path(directory) / "cabinet.sqlite3")
            original = {
                "display_name": "Rae",
                "date_of_birth": "2000-01-01",
                "gender": "Female",
            }
            save_setup_preferences(store, original)
            self.assertEqual(store.get_setting("setup_complete"), "true")
            self.assertEqual(store.get_setting("gender"), "Female")

            changed = {**original, "gender": "Prefer not to say"}
            with self.assertRaisesRegex(ValueError, "Confirm profile changes"):
                save_setup_preferences(store, changed)
            self.assertEqual(store.get_setting("gender"), "Female")

            save_setup_preferences(
                store, changed, confirm_profile_overwrite=True
            )
            self.assertEqual(store.get_setting("gender"), "Prefer not to say")

    def test_profiles_are_isolated_by_authenticated_account_id(self):
        with tempfile.TemporaryDirectory() as directory:
            first = CabinetStore(account_database_path(directory, "first"))
            second = CabinetStore(account_database_path(directory, "second"))
            first.set_setting("display_name", "Rae")
            second.set_setting("display_name", "Sam")
            first.set_setting("gender", "Female")
            second.set_setting("gender", "Male")

            self.assertEqual(first.get_setting("display_name"), "Rae")
            self.assertEqual(second.get_setting("display_name"), "Sam")
            self.assertEqual(first.get_setting("gender"), "Female")
            self.assertEqual(second.get_setting("gender"), "Male")


if __name__ == "__main__":
    unittest.main()
