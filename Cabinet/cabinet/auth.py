"""Firebase Authentication REST client for email/password accounts.

Firebase's mobile Web API key identifies the project; it is not a service
account credential. No password or token is written to the Cabinet database.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AuthenticationError(Exception):
    """Safe-to-display authentication/configuration error."""


@dataclass(frozen=True)
class AuthSession:
    uid: str
    email: str
    id_token: str
    refresh_token: str
    is_new_user: bool = False


def validate_email(email: str) -> str:
    normalized = email.strip().lower()
    if len(normalized) > 254 or not re.fullmatch(
        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
        r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+",
        normalized,
    ):
        raise ValueError("Enter a valid email address.")
    return normalized


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Use a password with at least 8 characters.")
    if len(password) > 4096:
        raise ValueError("That password is too long.")


class FirebaseEmailAuth:
    """Email/password and password-reset operations backed by Firebase Auth."""

    _IDENTITY_URL = "https://identitytoolkit.googleapis.com/v1/accounts"
    _GENERIC_SIGN_IN = "We couldn't sign you in. Check your email and password."

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 15,
        opener=urllib.request.urlopen,
    ) -> None:
        self.api_key = api_key or os.environ.get("CABINET_FIREBASE_API_KEY", "")
        self.timeout = timeout
        self.opener = opener

    @classmethod
    def from_workspace(cls, workspace: Path) -> FirebaseEmailAuth:
        """Load the public Firebase web API key from env or a local JSON file."""
        config_path = workspace / "firebase_config.json"
        api_key = os.environ.get("CABINET_FIREBASE_API_KEY", "")
        if not api_key and config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                if not isinstance(config, dict):
                    raise ValueError("Firebase configuration must be a JSON object.")
                api_key = str(config.get("apiKey", ""))
            except (OSError, ValueError, json.JSONDecodeError) as error:
                raise AuthenticationError(
                    "Firebase configuration could not be read. Check firebase_config.json."
                ) from error
        return cls(api_key=api_key)

    def sign_up(self, email: str, password: str) -> AuthSession:
        email = validate_email(email)
        validate_password(password)
        result = self._request(
            "signUp",
            {"email": email, "password": password, "returnSecureToken": True},
        )
        return self._session(result, is_new_user=True)

    def sign_in(self, email: str, password: str) -> AuthSession:
        email = validate_email(email)
        if not password:
            raise ValueError("Enter your password.")
        result = self._request(
            "signInWithPassword",
            {"email": email, "password": password, "returnSecureToken": True},
        )
        return self._session(result)

    def send_password_reset(self, email: str) -> None:
        email = validate_email(email)
        self._request(
            "sendOobCode",
            {"requestType": "PASSWORD_RESET", "email": email},
        )

    def delete_account(self, id_token: str) -> None:
        if not id_token:
            raise AuthenticationError("Sign in again before deleting this account.")
        self._request("delete", {"idToken": id_token})

    def _request(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise AuthenticationError(
                "Email sign-in needs Firebase setup. Add your Firebase Web API key "
                "to firebase_config.json; see README.md."
            )
        url = f"{self._IDENTITY_URL}:{operation}?{urllib.parse.urlencode({'key': self.api_key})}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                body = json.loads(error.read().decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                raise AuthenticationError("The authentication service could not complete that request.") from error
            code = body.get("error", {}).get("message", "")
            raise AuthenticationError(self._friendly_error(operation, code)) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise AuthenticationError(
                "Cabinet couldn't reach the authentication service. Check your connection and try again."
            ) from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AuthenticationError(
                "The authentication service returned an unreadable response."
            ) from error
        if not isinstance(result, dict):
            raise AuthenticationError("The authentication service returned an invalid response.")
        return result

    def _session(self, result: dict[str, Any], is_new_user: bool = False) -> AuthSession:
        uid = result.get("localId")
        email = result.get("email")
        id_token = result.get("idToken")
        refresh_token = result.get("refreshToken")
        if not all(
            isinstance(value, str) and value
            for value in (uid, email, id_token, refresh_token)
        ):
            raise AuthenticationError("The authentication service returned an incomplete session.")
        return AuthSession(uid, email, id_token, refresh_token, is_new_user)

    @classmethod
    def _friendly_error(cls, operation: str, code: str) -> str:
        if operation == "signInWithPassword":
            return cls._GENERIC_SIGN_IN
        messages = {
            "EMAIL_EXISTS": "An account with that email already exists. Try logging in.",
            "INVALID_EMAIL": "Enter a valid email address.",
            "WEAK_PASSWORD : Password should be at least 6 characters":
                "Choose a longer password. Use at least 8 characters.",
            "OPERATION_NOT_ALLOWED":
                "Email/password sign-in is disabled in Firebase Authentication settings.",
            "TOO_MANY_ATTEMPTS_TRY_LATER":
                "Too many attempts. Wait a little while, then try again.",
            "USER_DISABLED": "This account is disabled. Contact the account administrator.",
            "INVALID_ID_TOKEN": "Your session expired. Sign in again.",
        }
        if code in messages:
            return messages[code]
        if operation == "sendOobCode":
            return "Cabinet couldn't send the reset email. Check the address and try again."
        if operation == "delete":
            return "Cabinet couldn't delete this account. Sign in again and retry."
        return "Cabinet couldn't create the account. Check your details and try again."
