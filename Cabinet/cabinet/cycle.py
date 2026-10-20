"""Private, local-only menstrual history storage and non-diagnostic estimates."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Generator

from cabinet.secure_storage import PrivateDataCipher


class MenstrualStore:
    """Encrypted cycle records use a database separate from ordinary exports."""

    def __init__(
        self, database_path: str | Path, cipher: PrivateDataCipher
    ) -> None:
        self.database_path = Path(database_path)
        self.cipher = cipher
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS period_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    encrypted_payload TEXT NOT NULL
                )
                """
            )

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def add_period(
        self,
        first_day: str,
        last_day: str = "",
        symptoms: str = "",
        notes: str = "",
    ) -> int:
        first_day = self._validate_date(first_day, "First day")
        last_day = self._validate_date(last_day, "Last day", optional=True)
        if last_day and last_day < first_day:
            raise ValueError("Last day cannot be before the first day.")
        payload = json.dumps(
            {
                "first_day": first_day,
                "last_day": last_day,
                "symptoms": symptoms.strip(),
                "notes": notes.strip(),
            }
        )
        encrypted_payload = self.cipher.encrypt(payload)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO period_records (encrypted_payload) VALUES (?)",
                (encrypted_payload,),
            )
            return int(cursor.lastrowid)

    def update_period(self, record_id: int, **values: str) -> None:
        existing = next(
            (record for record in self.list_periods() if record["id"] == record_id),
            None,
        )
        if existing is None:
            raise ValueError("Period record was not found.")
        allowed = {"first_day", "last_day", "symptoms", "notes"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError("Unsupported period record field.")
        existing.update(values)
        first_day = self._validate_date(existing["first_day"], "First day")
        last_day = self._validate_date(
            existing.get("last_day", ""), "Last day", optional=True
        )
        if last_day and last_day < first_day:
            raise ValueError("Last day cannot be before the first day.")
        payload = json.dumps(
            {
                "first_day": first_day,
                "last_day": last_day,
                "symptoms": existing.get("symptoms", "").strip(),
                "notes": existing.get("notes", "").strip(),
            }
        )
        encrypted_payload = self.cipher.encrypt(payload)
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE period_records SET encrypted_payload = ? WHERE id = ?",
                (encrypted_payload, record_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("Period record was not found.")

    def delete_period(self, record_id: int) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM period_records WHERE id = ?", (record_id,)
            )
            if cursor.rowcount == 0:
                raise ValueError("Period record was not found.")

    def delete_all(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM period_records")

    def erase_all(self) -> None:
        """Remove encrypted rows, compact the database, then remove its files/key."""
        self.delete_all()
        with self._connect() as connection:
            connection.execute("VACUUM")
        self.cipher.destroy_key()
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.database_path) + suffix)
            if path.exists():
                path.unlink()

    def list_periods(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, encrypted_payload FROM period_records"
            ).fetchall()
        results = []
        for row in rows:
            payload = json.loads(self.cipher.decrypt(row["encrypted_payload"]))
            results.append({"id": row["id"], **payload})
        return sorted(results, key=lambda item: item["first_day"], reverse=True)

    @staticmethod
    def _validate_date(value: str, label: str, optional: bool = False) -> str:
        cleaned = value.strip()
        if not cleaned and optional:
            return ""
        try:
            date.fromisoformat(cleaned)
        except ValueError as error:
            raise ValueError(f"{label} must use YYYY-MM-DD.") from error
        return cleaned


def estimate_next_period_window(
    first_days: list[str],
) -> tuple[date, date] | None:
    """Estimate a window from at least four user-entered period start dates."""
    parsed = sorted({date.fromisoformat(value) for value in first_days})
    if len(parsed) < 4:
        return None
    intervals = [
        (later - earlier).days for earlier, later in zip(parsed, parsed[1:])
    ]
    if len(intervals) < 3 or any(interval < 1 or interval > 90 for interval in intervals):
        return None
    next_earliest = parsed[-1] + timedelta(days=min(intervals))
    next_latest = parsed[-1] + timedelta(days=max(intervals))
    return next_earliest, next_latest


def safe_account_id(uid: str) -> str:
    safe_uid = uid.strip()
    if not safe_uid:
        raise ValueError("Account id is required.")
    if any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in safe_uid):
        raise ValueError("Account id contains an invalid character.")
    return safe_uid


def account_database_path(user_data_dir: str | Path, uid: str) -> Path:
    return (
        Path(user_data_dir)
        / "accounts"
        / safe_account_id(uid)
        / "cabinet.sqlite3"
    )


def private_store_path(user_data_dir: str | Path, uid: str) -> Path:
    return (
        Path(user_data_dir)
        / "private-health"
        / safe_account_id(uid)
        / "menstrual.sqlite3"
    )
