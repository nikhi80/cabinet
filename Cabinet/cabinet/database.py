"""Local SQLite storage for Cabinet.

All records are kept on the device. This module intentionally does not make
network requests or calculate medical/vaccination recommendations.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Generator


def account_database_path(user_data_dir: str | Path, uid: str) -> Path:
    safe_uid = uid.strip()
    if not safe_uid:
        raise ValueError("Account id is required.")
    if any(
        character
        not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for character in safe_uid
    ):
        raise ValueError("Account id contains an invalid character.")
    return Path(user_data_dir) / "accounts" / safe_uid / "cabinet.sqlite3"


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
                CREATE TABLE IF NOT EXISTS medicine_alarm_schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    medicine_id INTEGER NOT NULL REFERENCES medicines(id)
                        ON DELETE CASCADE,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    reminder_times TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS medicine_alarm_reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    schedule_id INTEGER NOT NULL
                        REFERENCES medicine_alarm_schedules(id) ON DELETE CASCADE,
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
        schedule_start_date: str = "",
        schedule_end_date: str = "",
        schedule_times: list[str] | None = None,
    ) -> int:
        name = self._required_text(name, "Medicine name")
        quantity_value = self._nonnegative_int(quantity, "Quantity")
        threshold = self._nonnegative_int(low_stock_threshold, "Low-stock alert")
        expiry = self._validate_optional_date(expiry_date, "Expiry date")
        schedule = None
        if schedule_times is not None:
            start_date = self._validate_optional_date(
                schedule_start_date, "Schedule start date"
            )
            end_date = self._validate_optional_date(
                schedule_end_date, "Schedule end date"
            )
            if not start_date or not end_date:
                raise ValueError("Enter both a start date and an end date for the schedule.")
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
            if start < date.today():
                raise ValueError("Schedule start date cannot be in the past.")
            if end < start:
                raise ValueError("Schedule end date cannot be before its start date.")
            if (end - start).days >= 3650:
                raise ValueError("Dose schedules can be created for up to 10 years.")
            times = self._validated_schedule_times(schedule_times)
            schedule = (start_date, end_date, times)
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
            if schedule is not None:
                self._create_in_app_dose_schedule(
                    connection, medicine_id, *schedule, now=now
                )
            return medicine_id

    @staticmethod
    def _create_in_app_dose_schedule(
        connection: sqlite3.Connection,
        medicine_id: int,
        start_date: str,
        end_date: str,
        schedule_times: list[str],
        *,
        now: str,
    ) -> None:
        cursor = connection.execute(
            """INSERT INTO medicine_alarm_schedules
               (medicine_id, start_date, end_date, reminder_times)
               VALUES (?, ?, ?, ?)""",
            (medicine_id, start_date, end_date, json.dumps(schedule_times)),
        )
        schedule_id = int(cursor.lastrowid)
        current_date = date.fromisoformat(start_date)
        final_date = date.fromisoformat(end_date)
        reminder_count = 0
        while current_date <= final_date:
            for schedule_time in schedule_times:
                due_at = f"{current_date.isoformat()}T{schedule_time}:00"
                if due_at >= now:
                    connection.execute(
                        """INSERT INTO medicine_alarm_reminders
                           (schedule_id, due_at, updated_at)
                           VALUES (?, ?, ?)""",
                        (schedule_id, due_at, now),
                    )
                    reminder_count += 1
            current_date += timedelta(days=1)
        if reminder_count == 0:
            raise ValueError("Choose a dose time that is still in the future.")

    @staticmethod
    def _validated_schedule_times(values: list[str]) -> list[str]:
        times = sorted(value.strip() for value in values if value.strip())
        if not times:
            raise ValueError("Enter at least one dose time.")
        if len(times) > 8:
            raise ValueError("Add no more than 8 dose times per day.")
        for value in times:
            try:
                parsed = datetime.strptime(value, "%H:%M")
            except ValueError as error:
                raise ValueError(
                    "Dose times must use 24-hour HH:MM format."
                ) from error
            if parsed.strftime("%H:%M") != value:
                raise ValueError("Dose times must use 24-hour HH:MM format.")
        if len(set(times)) != len(times):
            raise ValueError("Dose times must be different.")
        return times

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
            connection.execute(
                """UPDATE medicine_alarm_reminders
                   SET status = 'missed', updated_at = ?
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
            alarm_rows = connection.execute(
                """SELECT r.id, r.due_at, r.status, r.snoozed_until,
                          m.id AS medicine_id, m.name, m.strength,
                          'Scheduled alarm' AS dose, 'Daily' AS frequency,
                          '' AS instructions
                   FROM medicine_alarm_reminders r
                   JOIN medicine_alarm_schedules s ON s.id = r.schedule_id
                   JOIN medicines m ON m.id = s.medicine_id
                   WHERE r.status = 'pending'
                     AND CASE WHEN r.snoozed_until != ''
                              THEN r.snoozed_until ELSE r.due_at END >= ?
                   ORDER BY CASE WHEN r.snoozed_until != ''
                                 THEN r.snoozed_until ELSE r.due_at END
                   LIMIT ?""",
                (now_text, limit),
            ).fetchall()
            doses = [dict(row) for row in rows]
            doses.extend(
                self._as_medicine_alarm_dose(row) for row in alarm_rows
            )
            doses.sort(
                key=lambda dose: dose["snoozed_until"] or dose["due_at"]
            )
            return doses[:limit]

    def list_dose_reminders_between(
        self, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """List pending dose reminders in a date range without changing their status."""
        if end_date < start_date:
            raise ValueError("End date cannot be before start date.")
        start_date = max(start_date, date.today())
        if end_date < start_date:
            return []
        now_text = datetime.now().isoformat(timespec="seconds")
        with self._connect() as connection:
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
                     AND substr(
                         CASE WHEN d.snoozed_until != ''
                              THEN d.snoozed_until ELSE d.due_at END,
                         1, 10
                     ) BETWEEN ? AND ?
                   ORDER BY CASE WHEN d.snoozed_until != ''
                                 THEN d.snoozed_until ELSE d.due_at END""",
                (now_text, start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
            alarm_rows = connection.execute(
                """SELECT r.id, r.due_at, r.status, r.snoozed_until,
                          m.id AS medicine_id, m.name, m.strength,
                          'Scheduled alarm' AS dose, 'Daily' AS frequency,
                          '' AS instructions
                   FROM medicine_alarm_reminders r
                   JOIN medicine_alarm_schedules s ON s.id = r.schedule_id
                   JOIN medicines m ON m.id = s.medicine_id
                   WHERE r.status = 'pending'
                     AND CASE WHEN r.snoozed_until != ''
                              THEN r.snoozed_until ELSE r.due_at END >= ?
                     AND substr(
                         CASE WHEN r.snoozed_until != ''
                              THEN r.snoozed_until ELSE r.due_at END,
                         1, 10
                     ) BETWEEN ? AND ?
                   ORDER BY CASE WHEN r.snoozed_until != ''
                                 THEN r.snoozed_until ELSE r.due_at END""",
                (now_text, start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
            doses = [dict(row) for row in rows]
            doses.extend(
                self._as_medicine_alarm_dose(row) for row in alarm_rows
            )
            doses.sort(
                key=lambda dose: dose["snoozed_until"] or dose["due_at"]
            )
            return doses

    @staticmethod
    def _as_medicine_alarm_dose(row: sqlite3.Row) -> dict[str, Any]:
        dose = dict(row)
        dose["id"] = -int(dose["id"]) - 1
        return dose

    def update_dose_reminder(
        self, reminder_id: int, action: str, now: datetime | None = None
    ) -> None:
        now = now or datetime.now()
        if action not in {"taken", "skipped", "snoozed"}:
            raise ValueError("Choose Taken, Skip, or Snooze.")
        is_medicine_alarm = reminder_id < 0
        database_id = -reminder_id - 1 if is_medicine_alarm else reminder_id
        if database_id < 1:
            raise ValueError("Dose reminder was not found.")
        reminder_table = (
            "medicine_alarm_reminders" if is_medicine_alarm else "dose_reminders"
        )
        with self._connect() as connection:
            row = connection.execute(
                f"""SELECT status, due_at, snoozed_until
                    FROM {reminder_table} WHERE id = ?""",
                (database_id,),
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
                    f"""UPDATE {reminder_table}
                        SET snoozed_until = ?, updated_at = ? WHERE id = ?""",
                    (snoozed_until, now.isoformat(timespec="seconds"), database_id),
                )
            else:
                connection.execute(
                    f"""UPDATE {reminder_table}
                        SET status = ?, snoozed_until = '', updated_at = ?
                        WHERE id = ?""",
                    (action, now.isoformat(timespec="seconds"), database_id),
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
            alarm_rows = connection.execute(
                """SELECT r.id, r.due_at, r.status, r.snoozed_until,
                          m.name, m.strength, 'Scheduled alarm' AS dose,
                          '' AS instructions
                   FROM medicine_alarm_reminders r
                   JOIN medicine_alarm_schedules s ON s.id = r.schedule_id
                   JOIN medicines m ON m.id = s.medicine_id
                   WHERE r.status != 'pending'
                   ORDER BY r.due_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            history = [dict(row) for row in rows]
            for row in alarm_rows:
                history_item = dict(row)
                history_item["id"] = -int(history_item["id"]) - 1
                history.append(history_item)
            history.sort(key=lambda item: item["due_at"], reverse=True)
            return history[:limit]

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
