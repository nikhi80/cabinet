import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from cabinet.auth import (
    AuthenticationError,
    FirebaseEmailAuth,
    validate_email,
    validate_password,
)
class FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return self.body


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


if __name__ == "__main__":
    unittest.main()
