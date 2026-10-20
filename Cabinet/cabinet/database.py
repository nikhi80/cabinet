"""Local SQLite storage for Cabinet.

All records are kept on the device. This module intentionally does not make
network requests or calculate medical/vaccination recommendations.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Generator


class CabinetStore:
    """Small SQLite repository used by the app and its tests."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS medicines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    strength TEXT NOT NULL DEFAULT '',
                    form TEXT NOT NULL DEFAULT '',
                    quantity INTEGER NOT NULL CHECK (quantity >= 0),
                    low_stock_threshold INTEGER NOT NULL DEFAULT 0
                        CHECK (low_stock_threshold >= 0),
                    expiry_date TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS stock_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    medicine_id INTEGER NOT NULL REFERENCES medicines(id)
                        ON DELETE CASCADE,
                    change_amount INTEGER NOT NULL,
                    quantity_after INTEGER NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    changed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS vaccines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person TEXT NOT NULL,
                    vaccine_name TEXT NOT NULL,
                    dose_label TEXT NOT NULL DEFAULT '',
                    administered_on TEXT NOT NULL DEFAULT '',
                    next_due_on TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS appointments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    person TEXT NOT NULL DEFAULT '',
                    appointment_date TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'Vaccination',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS prescriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL UNIQUE,
                    image_hash TEXT NOT NULL DEFAULT '',
                    ocr_text TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS prescription_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prescription_id INTEGER NOT NULL REFERENCES prescriptions(id)
                        ON DELETE CASCADE,
                    medicine_id INTEGER REFERENCES medicines(id) ON DELETE SET NULL,
                    name TEXT NOT NULL,
                    strength TEXT NOT NULL DEFAULT '',
                    dose TEXT NOT NULL,
                    frequency TEXT NOT NULL,
                    instructions TEXT NOT NULL DEFAULT '',
                    start_date TEXT NOT NULL,
                    duration_days INTEGER NOT NULL,
                    end_date TEXT NOT NULL,
                    prescribed_quantity INTEGER,
                    reminder_times TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS medicine_schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prescription_item_id INTEGER NOT NULL UNIQUE
                        REFERENCES prescription_items(id) ON DELETE CASCADE,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    reminder_times TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS dose_reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    schedule_id INTEGER NOT NULL REFERENCES medicine_schedules(id)
                        ON DELETE CASCADE,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'taken', 'skipped', 'missed')),
                    snoozed_until TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    UNIQUE (schedule_id, due_at)
                );
                CREATE TABLE IF NOT EXISTS settings (
                    setting_key TEXT PRIMARY KEY,
                    setting_value TEXT NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO settings VALUES ('theme', 'light')"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _validate_optional_date(value: str, field_name: str) -> str:
        clean_value = value.strip()
        if clean_value:
            try:
                parsed_date = date.fromisoformat(clean_value)
            except ValueError as error:
                raise ValueError(
                    f"{field_name} must be a valid date in YYYY-MM-DD format."
                ) from error
            if parsed_date.isoformat() != clean_value:
                raise ValueError(
                    f"{field_name} must be a valid date in YYYY-MM-DD format."
                )
        return clean_value

    @staticmethod
    def _required_text(value: str, field_name: str) -> str:
        clean_value = value.strip()
        if not clean_value:
            raise ValueError(f"{field_name} is required.")
        return clean_value

    @staticmethod
    def _nonnegative_int(value: int | str, field_name: str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{field_name} must be a whole number.") from error
        if parsed < 0:
            raise ValueError(f"{field_name} cannot be negative.")
        return parsed

    def add_medicine(
        self,
        name: str,
        quantity: int | str,
        low_stock_threshold: int | str = 0,
        strength: str = "",
        form: str = "",
        expiry_date: str = "",
        notes: str = "",
    ) -> int:
        name = self._required_text(name, "Medicine name")
        quantity_value = self._nonnegative_int(quantity, "Quantity")
        threshold = self._nonnegative_int(low_stock_threshold, "Low-stock alert")
        expiry = self._validate_optional_date(expiry_date, "Expiry date")
        now = self._now()
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO medicines
                   (name, strength, form, quantity, low_stock_threshold,
                    expiry_date, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    name,
                    strength.strip(),
                    form.strip(),
                    quantity_value,
                    threshold,
                    expiry,
                    notes.strip(),
                    now,
                    now,
                ),
            )
            medicine_id = int(cursor.lastrowid)
            connection.execute(
                """INSERT INTO stock_history
                   (medicine_id, change_amount, quantity_after, note, changed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (medicine_id, quantity_value, quantity_value, "Initial stock", now),
            )
            return medicine_id

    def update_medicine(self, medicine_id: int, **values: Any) -> None:
        allowed = {
            "name",
            "strength",
            "form",
            "quantity",
            "low_stock_threshold",
            "expiry_date",
            "notes",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Unsupported medicine fields: {', '.join(sorted(unknown))}")
        if not values:
            return
        if "name" in values:
            values["name"] = self._required_text(values["name"], "Medicine name")
        if "quantity" in values:
            values["quantity"] = self._nonnegative_int(values["quantity"], "Quantity")
        if "low_stock_threshold" in values:
            values["low_stock_threshold"] = self._nonnegative_int(
                values["low_stock_threshold"], "Low-stock alert"
            )
        if "expiry_date" in values:
            values["expiry_date"] = self._validate_optional_date(
                values["expiry_date"], "Expiry date"
            )
        for field in ("strength", "form", "notes"):
            if field in values:
                values[field] = str(values[field]).strip()

        now = self._now()
        assignments = ", ".join(f"{field} = ?" for field in values)
        with self._connect() as connection:
            previous = connection.execute(
                "SELECT quantity FROM medicines WHERE id = ?", (medicine_id,)
            ).fetchone()
            if previous is None:
                raise ValueError("Medicine was not found.")
            connection.execute(
                f"UPDATE medicines SET {assignments}, updated_at = ? WHERE id = ?",
                (*values.values(), now, medicine_id),
            )
            if "quantity" in values and values["quantity"] != previous["quantity"]:
                connection.execute(
                    """INSERT INTO stock_history
                       (medicine_id, change_amount, quantity_after, note, changed_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        medicine_id,
                        values["quantity"] - previous["quantity"],
                        values["quantity"],
                        "Quantity updated",
                        now,
                    ),
                )

    def change_stock(self, medicine_id: int, change: int | str, note: str = "") -> int:
        try:
            amount = int(change)
        except (TypeError, ValueError) as error:
            raise ValueError("Stock change must be a whole number.") from error
        if amount == 0:
            raise ValueError("Enter a non-zero stock change.")
        now = self._now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT quantity FROM medicines WHERE id = ?", (medicine_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Medicine was not found.")
            new_quantity = int(row["quantity"]) + amount
            if new_quantity < 0:
                raise ValueError("Stock cannot go below zero.")
            connection.execute(
                "UPDATE medicines SET quantity = ?, updated_at = ? WHERE id = ?",
                (new_quantity, now, medicine_id),
            )
            connection.execute(
                """INSERT INTO stock_history
                   (medicine_id, change_amount, quantity_after, note, changed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (medicine_id, amount, new_quantity, note.strip(), now),
            )
            return new_quantity

    def delete_medicine(self, medicine_id: int) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM medicines WHERE id = ?", (medicine_id,))
            if cursor.rowcount == 0:
                raise ValueError("Medicine was not found.")

    def list_medicines(self, search: str = "") -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM medicines
                   WHERE name LIKE ? OR strength LIKE ? OR form LIKE ?
                   ORDER BY name COLLATE NOCASE""",
                tuple(f"%{search.strip()}%" for _ in range(3)),
            ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def _normalize_medicine_part(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.casefold())

    @classmethod
    def _prescription_item_key(cls, item: dict[str, Any]) -> tuple[str, ...]:
        return (
            cls._normalize_medicine_part(str(item.get("name", ""))),
            cls._normalize_medicine_part(str(item.get("strength", ""))),
            " ".join(str(item.get("dose", "")).casefold().split()),
            " ".join(str(item.get("frequency", "")).casefold().split()),
            " ".join(str(item.get("instructions", "")).casefold().split()),
            str(item.get("start_date", "")),
            str(item.get("duration_days", "")),
            str(item.get("prescribed_quantity") or ""),
        )

    def matching_medicines(self, name: str, strength: str = "") -> list[dict[str, Any]]:
        normalized_name = self._normalize_medicine_part(name)
        normalized_strength = self._normalize_medicine_part(strength)
        return [
            medicine
            for medicine in self.list_medicines()
            if self._normalize_medicine_part(medicine["name"]) == normalized_name
            and self._normalize_medicine_part(medicine["strength"])
            == normalized_strength
        ]

    @staticmethod
    def _validated_reminder_times(values: list[str], frequency: str) -> list[str]:
        frequency_text = re.sub(
            r"\b(?:a day|per day)\b", "daily", frequency.casefold()
        )
        counts = {
            "once daily": 1,
            "twice daily": 2,
            "three times daily": 3,
            "four times daily": 4,
        }
        expected_count = counts.get(frequency_text)
        if expected_count is None:
            numeric_daily = re.fullmatch(
                r"(\d+)\s+times?\s+daily", frequency_text
            )
            if numeric_daily:
                expected_count = int(numeric_daily.group(1))
        if expected_count is None:
            every_hours = re.fullmatch(r"every\s+(\d+)\s+hours?", frequency_text)
            if every_hours:
                interval = int(every_hours.group(1))
                if interval > 0 and 24 % interval == 0:
                    expected_count = 24 // interval
        if expected_count is None:
            raise ValueError(
                "Use a clear frequency (once, twice, three times, or four times daily; "
                "or every N hours when it divides evenly into 24)."
            )
        times = [value.strip() for value in values if value.strip()]
        if len(times) != expected_count:
            raise ValueError(
                f"Enter exactly {expected_count} local reminder time(s) for this frequency."
            )
        for value in times:
            try:
                parsed = datetime.strptime(value, "%H:%M")
            except ValueError as error:
                raise ValueError("Reminder times must use 24-hour HH:MM format.") from error
            if parsed.strftime("%H:%M") != value:
                raise ValueError("Reminder times must use 24-hour HH:MM format.")
        if len(set(times)) != len(times):
            raise ValueError("Reminder times must be different.")
        every_hours = re.fullmatch(r"every\s+(\d+)\s+hours?", frequency_text)
        if every_hours:
            interval_minutes = int(every_hours.group(1)) * 60
            minute_of_day = [
                int(value[:2]) * 60 + int(value[3:]) for value in times
            ]
            intervals = [
                (minute_of_day[(index + 1) % len(minute_of_day)] - minute) % 1440
                for index, minute in enumerate(minute_of_day)
            ]
            intervals = [interval or 1440 for interval in intervals]
            if any(interval != interval_minutes for interval in intervals):
                raise ValueError(
                    f"Reminder times must be {every_hours.group(1)} hours apart "
                    "for this confirmed frequency."
                )
        return sorted(times)

    def confirm_prescription(
        self,
        items: list[dict[str, Any]],
        fingerprint: str,
        ocr_text: str = "",
        image_hash: str = "",
    ) -> dict[str, Any]:
        if not items:
            raise ValueError("Add or confirm at least one medicine.")
        if not fingerprint.strip():
            raise ValueError("Prescription fingerprint is required.")

        prepared: list[dict[str, Any]] = []
        for item in items:
            if not item.get("confirmed"):
                raise ValueError("Confirm each medicine's details before saving.")
            name = self._required_text(item.get("name", ""), "Medicine name")
            dose = self._required_text(item.get("dose", ""), "Dose per intake")
            frequency = self._required_text(item.get("frequency", ""), "Frequency")
            start_date = self._validate_optional_date(
                item.get("start_date", ""), "Start date"
            )
            if item.get("create_reminders"):
                if not start_date:
                    raise ValueError(
                        f"Enter a confirmed start date for {name} before creating reminders."
                    )
                try:
                    duration_days = int(item.get("duration_days", ""))
                except (TypeError, ValueError) as error:
                    raise ValueError(
                        f"Enter the prescribed duration in days for {name}."
                    ) from error
                if not 1 <= duration_days <= 3650:
                    raise ValueError(
                        f"Duration for {name} must be between 1 and 3650 days."
                    )
                times = self._validated_reminder_times(
                    item.get("reminder_times", []), frequency
                )
            else:
                duration_days = int(item.get("duration_days") or 0)
                times = []
            if start_date and duration_days:
                end_date = (
                    date.fromisoformat(start_date)
                    + timedelta(days=duration_days - 1)
                ).isoformat()
            else:
                end_date = ""
            prescribed_quantity = item.get("prescribed_quantity")
            if prescribed_quantity not in (None, ""):
                prescribed_quantity = self._nonnegative_int(
                    prescribed_quantity, "Prescribed quantity"
                )
            else:
                prescribed_quantity = None
            purchased_quantity = item.get("purchased_quantity")
            if purchased_quantity not in (None, ""):
                purchased_quantity = self._nonnegative_int(
                    purchased_quantity, "Purchased quantity"
                )
            else:
                purchased_quantity = 0
            if item.get("purchased") and purchased_quantity <= 0:
                raise ValueError(
                    f"Enter how many {name} units were purchased; prescribed quantity "
                    "is not assumed to be in stock."
                )
            if not item.get("purchased") and purchased_quantity:
                raise ValueError(
                    f"Mark {name} as purchased before adding purchased quantity to stock."
                )

            inventory_id = item.get("inventory_id")
            if inventory_id:
                try:
                    inventory_id = int(inventory_id)
                except (TypeError, ValueError) as error:
                    raise ValueError("Selected inventory record is invalid.") from error
                with self._connect() as connection:
                    existing = connection.execute(
                        "SELECT name, strength FROM medicines WHERE id = ?",
                        (inventory_id,),
                    ).fetchone()
                if existing is None:
                    raise ValueError("Selected medicine inventory record no longer exists.")
                if (
                    self._normalize_medicine_part(existing["name"])
                    != self._normalize_medicine_part(name)
                    or self._normalize_medicine_part(existing["strength"])
                    != self._normalize_medicine_part(item.get("strength", ""))
                ):
                    raise ValueError(
                        "Selected inventory record does not match the confirmed name and strength."
                    )
            prepared.append(
                {
                    **item,
                    "name": name,
                    "strength": str(item.get("strength", "")).strip(),
                    "dose": dose,
                    "frequency": frequency,
                    "instructions": str(item.get("instructions", "")).strip(),
                    "start_date": start_date,
                    "duration_days": duration_days,
                    "end_date": end_date,
                    "prescribed_quantity": prescribed_quantity,
                    "purchased_quantity": purchased_quantity,
                    "inventory_id": inventory_id,
                    "reminder_times": times,
                }
            )

        now_datetime = datetime.now().replace(microsecond=0)
        now = now_datetime.isoformat(timespec="seconds")

        def create_schedule(
            connection: sqlite3.Connection,
            item_id: int,
            item: dict[str, Any],
        ) -> None:
            schedule_cursor = connection.execute(
                """INSERT INTO medicine_schedules
                   (prescription_item_id, start_date, end_date, reminder_times)
                   VALUES (?, ?, ?, ?)""",
                (
                    item_id,
                    item["start_date"],
                    item["end_date"],
                    json.dumps(item["reminder_times"]),
                ),
            )
            schedule_id = int(schedule_cursor.lastrowid)
            schedule_date = max(
                date.fromisoformat(item["start_date"]),
                now_datetime.date(),
            )
            final_date = date.fromisoformat(item["end_date"])
            while schedule_date <= final_date:
                for reminder_time in item["reminder_times"]:
                    due_at = f"{schedule_date.isoformat()}T{reminder_time}:00"
                    if due_at < now:
                        continue
                    connection.execute(
                        """INSERT INTO dose_reminders
                           (schedule_id, due_at, updated_at)
                           VALUES (?, ?, ?)""",
                        (schedule_id, due_at, now),
                    )
                schedule_date += timedelta(days=1)

        with self._connect() as connection:
            duplicate = connection.execute(
                "SELECT id FROM prescriptions WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if duplicate is not None:
                prescription_id = int(duplicate["id"])
                existing_items = list(
                    connection.execute(
                        "SELECT * FROM prescription_items WHERE prescription_id = ?",
                        (prescription_id,),
                    ).fetchall()
                )
                reminders_added = False
                for item in prepared:
                    if not item["create_reminders"]:
                        continue
                    key = self._prescription_item_key(item)
                    existing_item = next(
                        (
                            row
                            for row in existing_items
                            if self._prescription_item_key(dict(row)) == key
                        ),
                        None,
                    )
                    if existing_item is None:
                        raise ValueError(
                            "Cabinet found the prescription but couldn't match its "
                            "confirmed medicine details."
                        )
                    existing_items.remove(existing_item)
                    schedule = connection.execute(
                        """SELECT id FROM medicine_schedules
                           WHERE prescription_item_id = ?""",
                        (existing_item["id"],),
                    ).fetchone()
                    if schedule is not None:
                        continue
                    connection.execute(
                        "UPDATE prescription_items SET reminder_times = ? WHERE id = ?",
                        (json.dumps(item["reminder_times"]), existing_item["id"]),
                    )
                    create_schedule(connection, int(existing_item["id"]), item)
                    reminders_added = True
                return {
                    "duplicate": True,
                    "prescription_id": prescription_id,
                    "reminders_added": reminders_added,
                }

            cursor = connection.execute(
                """INSERT INTO prescriptions
                   (fingerprint, image_hash, ocr_text, created_at)
                   VALUES (?, ?, ?, ?)""",
                (fingerprint, image_hash, ocr_text, now),
            )
            prescription_id = int(cursor.lastrowid)
            item_ids: list[int] = []
            for item in prepared:
                medicine_id = item["inventory_id"]
                if medicine_id is None:
                    inventory_cursor = connection.execute(
                        """INSERT INTO medicines
                           (name, strength, quantity, created_at, updated_at)
                           VALUES (?, ?, 0, ?, ?)""",
                        (item["name"], item["strength"], now, now),
                    )
                    medicine_id = int(inventory_cursor.lastrowid)
                    connection.execute(
                        """INSERT INTO stock_history
                           (medicine_id, change_amount, quantity_after, note, changed_at)
                           VALUES (?, 0, 0, 'Added from confirmed prescription; stock not purchased',
                                   ?)""",
                        (medicine_id, now),
                    )
                if item["purchased_quantity"]:
                    current = connection.execute(
                        "SELECT quantity FROM medicines WHERE id = ?", (medicine_id,)
                    ).fetchone()
                    new_quantity = int(current["quantity"]) + item["purchased_quantity"]
                    connection.execute(
                        "UPDATE medicines SET quantity = ?, updated_at = ? WHERE id = ?",
                        (new_quantity, now, medicine_id),
                    )
                    connection.execute(
                        """INSERT INTO stock_history
                           (medicine_id, change_amount, quantity_after, note, changed_at)
                           VALUES (?, ?, ?, 'Purchased from confirmed prescription', ?)""",
                        (medicine_id, item["purchased_quantity"], new_quantity, now),
                    )
                item_cursor = connection.execute(
                    """INSERT INTO prescription_items
                       (prescription_id, medicine_id, name, strength, dose, frequency,
                        instructions, start_date, duration_days, end_date,
                        prescribed_quantity, reminder_times)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        prescription_id,
                        medicine_id,
                        item["name"],
                        item["strength"],
                        item["dose"],
                        item["frequency"],
                        item["instructions"],
                        item["start_date"],
                        item["duration_days"],
                        item["end_date"],
                        item["prescribed_quantity"],
                        json.dumps(item["reminder_times"]),
                    ),
                )
                item_id = int(item_cursor.lastrowid)
                item_ids.append(item_id)
                if item["create_reminders"]:
                    create_schedule(connection, item_id, item)
            return {
                "duplicate": False,
                "prescription_id": prescription_id,
                "item_ids": item_ids,
            }

    def list_prescription_items(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT i.*, m.name AS inventory_name
                   FROM prescription_items i
                   LEFT JOIN medicines m ON m.id = i.medicine_id
                   ORDER BY i.id DESC"""
            ).fetchall()
            results = [dict(row) for row in rows]
            for row in results:
                row["reminder_times"] = json.loads(row["reminder_times"])
            return results

    def list_upcoming_doses(
        self, now: datetime | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        now = now or datetime.now()
        now_text = now.isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                """UPDATE dose_reminders SET status = 'missed', updated_at = ?
                   WHERE status = 'pending'
                     AND CASE WHEN snoozed_until != ''
                              THEN snoozed_until ELSE due_at END < ?""",
                (now_text, now_text),
            )
            rows = connection.execute(
                """SELECT d.id, d.due_at, d.status, d.snoozed_until,
                          i.medicine_id, i.name, i.strength, i.dose,
                          i.frequency, i.instructions
                   FROM dose_reminders d
                   JOIN medicine_schedules s ON s.id = d.schedule_id
                   JOIN prescription_items i ON i.id = s.prescription_item_id
                   WHERE d.status = 'pending'
                     AND CASE WHEN d.snoozed_until != ''
                              THEN d.snoozed_until ELSE d.due_at END >= ?
                   ORDER BY CASE WHEN d.snoozed_until != ''
                                 THEN d.snoozed_until ELSE d.due_at END
                   LIMIT ?""",
                (now_text, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def update_dose_reminder(
        self, reminder_id: int, action: str, now: datetime | None = None
    ) -> None:
        now = now or datetime.now()
        if action not in {"taken", "skipped", "snoozed"}:
            raise ValueError("Choose Taken, Skip, or Snooze.")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT status, due_at, snoozed_until
                   FROM dose_reminders WHERE id = ?""",
                (reminder_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Dose reminder was not found.")
            if row["status"] != "pending":
                raise ValueError("Only pending doses can be updated.")
            if action == "snoozed":
                scheduled = datetime.fromisoformat(
                    row["snoozed_until"] or row["due_at"]
                )
                snoozed_until = (
                    max(now, scheduled) + timedelta(minutes=10)
                ).isoformat(timespec="seconds")
                connection.execute(
                    """UPDATE dose_reminders SET snoozed_until = ?, updated_at = ?
                       WHERE id = ?""",
                    (snoozed_until, now.isoformat(timespec="seconds"), reminder_id),
                )
            else:
                connection.execute(
                    """UPDATE dose_reminders SET status = ?, snoozed_until = '',
                       updated_at = ? WHERE id = ?""",
                    (action, now.isoformat(timespec="seconds"), reminder_id),
                )

    def dose_history(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT d.id, d.due_at, d.status, d.snoozed_until,
                          i.name, i.strength, i.dose, i.instructions
                   FROM dose_reminders d
                   JOIN medicine_schedules s ON s.id = d.schedule_id
                   JOIN prescription_items i ON i.id = s.prescription_item_id
                   WHERE d.status != 'pending'
                   ORDER BY d.due_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def stock_history(self, medicine_id: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM stock_history WHERE medicine_id = ?
                   ORDER BY changed_at DESC, id DESC""",
                (medicine_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_vaccine(
        self,
        person: str,
        vaccine_name: str,
        dose_label: str = "",
        administered_on: str = "",
        next_due_on: str = "",
        notes: str = "",
    ) -> int:
        person = self._required_text(person, "Family member")
        vaccine_name = self._required_text(vaccine_name, "Vaccine name")
        administered = self._validate_optional_date(administered_on, "Date given")
        next_due = self._validate_optional_date(next_due_on, "Next due date")
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO vaccines
                   (person, vaccine_name, dose_label, administered_on, next_due_on,
                    notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    person,
                    vaccine_name,
                    dose_label.strip(),
                    administered,
                    next_due,
                    notes.strip(),
                    self._now(),
                ),
            )
            return int(cursor.lastrowid)

    def list_vaccines(self, search: str = "") -> list[dict[str, Any]]:
        pattern = f"%{search.strip()}%"
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM vaccines
                   WHERE person LIKE ? OR vaccine_name LIKE ? OR dose_label LIKE ?
                   ORDER BY CASE WHEN next_due_on = '' THEN '9999-12-31'
                                 ELSE next_due_on END,
                            person COLLATE NOCASE""",
                (pattern, pattern, pattern),
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_vaccine(self, vaccine_id: int) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM vaccines WHERE id = ?", (vaccine_id,))
            if cursor.rowcount == 0:
                raise ValueError("Vaccine record was not found.")

    def add_appointment(
        self,
        title: str,
        appointment_date: str,
        person: str = "",
        kind: str = "Vaccination",
        notes: str = "",
    ) -> int:
        title = self._required_text(title, "Appointment title")
        appointment_date = self._validate_optional_date(
            appointment_date, "Appointment date"
        )
        if not appointment_date:
            raise ValueError("Appointment date is required.")
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO appointments
                   (title, person, appointment_date, kind, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    title,
                    person.strip(),
                    appointment_date,
                    kind.strip() or "Vaccination",
                    notes.strip(),
                    self._now(),
                ),
            )
            return int(cursor.lastrowid)

    def list_appointments(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM appointments
                   ORDER BY appointment_date, title COLLATE NOCASE"""
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_appointment(self, appointment_id: int) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM appointments WHERE id = ?", (appointment_id,)
            )
            if cursor.rowcount == 0:
                raise ValueError("Appointment was not found.")

    def dashboard(self, today: date | None = None) -> dict[str, Any]:
        today = today or date.today()
        expiry_limit = (today + timedelta(days=30)).isoformat()
        today_text = today.isoformat()
        medicines = self.list_medicines()
        vaccines = self.list_vaccines()
        appointments = self.list_appointments()
        low_stock = [
            item
            for item in medicines
            if item["quantity"] <= item["low_stock_threshold"]
        ]
        expiring = [
            item
            for item in medicines
            if item["expiry_date"] and item["expiry_date"] <= expiry_limit
        ]
        upcoming = [
            appointment
            for appointment in appointments
            if appointment["appointment_date"] >= today_text
        ]
        upcoming += [
            {
                "title": f"{record['vaccine_name']} due",
                "person": record["person"],
                "appointment_date": record["next_due_on"],
                "kind": "Vaccine due date",
            }
            for record in vaccines
            if record["next_due_on"] and record["next_due_on"] >= today_text
        ]
        upcoming.sort(key=lambda item: item["appointment_date"])
        return {
            "medicine_count": len(medicines),
            "low_stock": low_stock,
            "expiring": expiring,
            "upcoming": upcoming[:5],
            "today": today_text,
        }

    def get_setting(self, key: str, default: str = "") -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT setting_value FROM settings WHERE setting_key = ?", (key,)
            ).fetchone()
            return str(row["setting_value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO settings (setting_key, setting_value) VALUES (?, ?)
                   ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value""",
                (key, value),
            )

    def export_json(self, destination: str | Path) -> Path:
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "exported_at": self._now(),
            "medicines": self.list_medicines(),
            "stock_history": self._all_rows("stock_history"),
            "vaccines": self.list_vaccines(),
            "appointments": self.list_appointments(),
            "prescriptions": self._all_rows("prescriptions"),
            "prescription_items": self.list_prescription_items(),
            "medicine_schedules": self._all_rows("medicine_schedules"),
            "dose_reminders": self._all_rows("dose_reminders"),
            "upcoming_doses": self.list_upcoming_doses(),
            "dose_history": self.dose_history(),
        }
        destination_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return destination_path

    def export_medicines_csv(self, destination: str | Path) -> Path:
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.list_medicines()
        columns = [
            "id",
            "name",
            "strength",
            "form",
            "quantity",
            "low_stock_threshold",
            "expiry_date",
            "notes",
        ]
        with destination_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            writer.writerows({key: row[key] for key in columns} for row in rows)
        return destination_path

    def create_backup(self, destination: str | Path) -> Path:
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as source:
            backup = sqlite3.connect(destination_path)
            try:
                source.backup(backup)
                backup.commit()
            finally:
                backup.close()
        return destination_path

    def _all_rows(self, table: str) -> list[dict[str, Any]]:
        if table not in {
            "stock_history",
            "prescriptions",
            "prescription_items",
            "dose_reminders",
            "medicine_schedules",
        }:
            raise ValueError("Unsupported export table.")
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
