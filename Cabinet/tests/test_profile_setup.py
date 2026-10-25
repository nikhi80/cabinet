import tempfile
import unittest
from pathlib import Path

from cabinet.database import CabinetStore, account_database_path
from cabinet.preferences import save_setup_preferences


class SetupPreferenceTests(unittest.TestCase):
    def test_accounts_keep_separate_database_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            first = account_database_path(directory, "first")
            second = account_database_path(directory, "second")
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent.name, "first")

    def test_profile_name_requires_confirmation_and_settings_are_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CabinetStore(Path(directory) / "cabinet.sqlite3")
            store.set_setting("date_of_birth", "2000-01-01")
            store.set_setting("gender", "Female")
            store.set_setting("feature_cycle", "true")
            store.set_setting("reminders_enabled", "true")

            save_setup_preferences(
                store,
                {
                    "display_name": "Rae",
                    "feature_medicines": "true",
                    "feature_vaccines": "false",
                    "household_name": "Home",
                },
            )
            self.assertEqual(store.get_setting("setup_complete"), "true")
            self.assertEqual(store.get_setting("display_name"), "Rae")
            self.assertEqual(store.get_setting("feature_vaccines"), "false")

            with self.assertRaisesRegex(ValueError, "Confirm profile changes"):
                save_setup_preferences(store, {"display_name": "Sam"})
            self.assertEqual(store.get_setting("display_name"), "Rae")

            save_setup_preferences(
                store, {"display_name": "Sam"}, confirm_profile_overwrite=True
            )
            self.assertEqual(store.get_setting("display_name"), "Sam")
            self.assertEqual(store.get_setting("date_of_birth"), "2000-01-01")
            self.assertEqual(store.get_setting("gender"), "Female")
            self.assertEqual(store.get_setting("feature_cycle"), "true")
            self.assertEqual(store.get_setting("reminders_enabled"), "true")


if __name__ == "__main__":
    unittest.main()
