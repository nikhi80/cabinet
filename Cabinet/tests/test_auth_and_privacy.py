import base64
import json
import os
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import patch

from cabinet.auth import (
    AuthenticationError,
    FirebaseEmailAuth,
    validate_email,
    validate_password,
)
from cabinet.cycle import (
    MenstrualStore,
    account_database_path,
    estimate_next_period_window,
    private_store_path,
)
from cabinet.database import CabinetStore
from cabinet.preferences import save_setup_preferences
from cabinet.secure_storage import supports_private_storage


class FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return self.body


class ReversibleTestCipher:
    def __init__(self):
        self.destroyed = False

    def encrypt(self, value):
        return base64.urlsafe_b64encode(value.encode()).decode()

    def decrypt(self, value):
        return base64.urlsafe_b64decode(value.encode()).decode()

    def destroy_key(self):
        self.destroyed = True


class FirebaseAuthTests(unittest.TestCase):
    def test_email_and_password_validation(self):
        self.assertEqual(validate_email(" Person@Example.com "), "person@example.com")
        with self.assertRaisesRegex(ValueError, "valid email"):
            validate_email("not-an-email")
        with self.assertRaisesRegex(ValueError, "8 characters"):
            validate_password("short")

    def test_signup_uses_firebase_and_returns_uid_session(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout, json.loads(request.data)))
            return FakeResponse(
                {
                    "localId": "uid-1",
                    "email": "person@example.com",
                    "idToken": "short-lived-id-token",
                    "refreshToken": "refresh-token",
                }
            )

        auth = FirebaseEmailAuth("public-api-key", opener=opener)
        session = auth.sign_up("person@example.com", "correct horse battery")
        self.assertEqual(session.uid, "uid-1")
        self.assertTrue(session.is_new_user)
        self.assertEqual(calls[0][2]["password"], "correct horse battery")
        self.assertIn("accounts:signUp", calls[0][0].full_url)
        self.assertEqual(calls[0][1], 15)

    def test_signin_error_is_generic_and_reset_never_reports_account_existence(self):
        def failed_opener(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                {},
                __import__("io").BytesIO(
                    b'{"error":{"message":"EMAIL_NOT_FOUND"}}'
                ),
            )

        auth = FirebaseEmailAuth("public-api-key", opener=failed_opener)
        with self.assertRaises(AuthenticationError) as error:
            auth.sign_in("person@example.com", "bad-password")
        self.assertEqual(
            str(error.exception),
            "We couldn't sign you in. Check your email and password.",
        )

    def test_missing_configuration_fails_without_simulated_login(self):
        auth = FirebaseEmailAuth(api_key="", opener=lambda *_args, **_kwargs: None)
        with self.assertRaisesRegex(AuthenticationError, "Firebase setup"):
            auth.sign_in("person@example.com", "some-password")

    def test_workspace_loader_finds_config_beside_project_when_runtime_dir_differs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_dir = root / "runtime"
            project_root = root / "project"
            package_dir = project_root / "cabinet"
            package_dir.mkdir(parents=True)
            (project_root / "firebase_config.json").write_text(
                json.dumps({"apiKey": "project-api-key"}),
                encoding="utf-8",
            )

            with (
                patch("cabinet.auth.__file__", str(package_dir / "auth.py")),
                patch.dict(os.environ, {"CABINET_FIREBASE_API_KEY": ""}),
            ):
                auth = FirebaseEmailAuth.from_workspace(runtime_dir)

        self.assertEqual(auth.api_key, "project-api-key")


class PrivateCycleStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "private-health" / "uid-1" / "periods.db"
        self.cipher = ReversibleTestCipher()
        self.store = MenstrualStore(self.path, self.cipher)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_records_are_encoded_separately_and_can_be_updated_and_deleted(self):
        record_id = self.store.add_period(
            "2030-01-01", "2030-01-04", "cramps", "note"
        )
        raw_database = self.path.read_bytes()
        self.assertNotIn(b"cramps", raw_database)
        self.assertEqual(self.store.list_periods()[0]["symptoms"], "cramps")
        self.store.update_period(record_id, notes="updated")
        self.assertEqual(self.store.list_periods()[0]["notes"], "updated")
        self.store.delete_period(record_id)
        self.assertEqual(self.store.list_periods(), [])

    def test_validates_period_dates_and_estimates_only_with_four_starts(self):
        with self.assertRaisesRegex(ValueError, "Last day cannot"):
            self.store.add_period("2030-01-10", "2030-01-09")
        self.assertIsNone(
            estimate_next_period_window(["2030-01-01", "2030-01-29", "2030-02-26"])
        )
        self.assertEqual(
            estimate_next_period_window(
                ["2030-01-01", "2030-01-29", "2030-02-26", "2030-03-26"]
            ),
            (date(2030, 4, 23), date(2030, 4, 23)),
        )

    def test_erasing_private_data_destroys_key_and_database(self):
        self.store.add_period("2030-01-01")
        self.store.erase_all()
        self.assertTrue(self.cipher.destroyed)
        self.assertFalse(self.path.exists())

    def test_private_paths_do_not_accept_path_traversal(self):
        with self.assertRaisesRegex(ValueError, "invalid character"):
            private_store_path(self.temp_dir.name, "..\\other")

    def test_accounts_get_separate_database_paths(self):
        one = account_database_path(self.temp_dir.name, "account-1")
        two = account_database_path(self.temp_dir.name, "account-2")
        self.assertNotEqual(one, two)
        self.assertEqual(one.parent.name, "account-1")


class OnboardingPreferenceTests(unittest.TestCase):
    def test_setup_completion_and_preferences_are_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CabinetStore(Path(directory) / "cabinet.sqlite3")
            save_setup_preferences(
                store,
                {
                    "display_name": "Rae",
                    "personalization": "Skip",
                    "feature_cycle": "false",
                    "reminders_enabled": "false",
                },
            )
            self.assertEqual(store.get_setting("setup_complete"), "true")
            self.assertEqual(store.get_setting("display_name"), "Rae")
            self.assertEqual(store.get_setting("feature_cycle"), "false")


class PrivateStoragePlatformTests(unittest.TestCase):
    def test_private_tracker_storage_is_only_enabled_on_supported_platforms(self):
        self.assertTrue(supports_private_storage("android"))
        self.assertTrue(supports_private_storage("win"))
        self.assertFalse(supports_private_storage("ios"))
        self.assertFalse(supports_private_storage("linux"))


if __name__ == "__main__":
    unittest.main()
