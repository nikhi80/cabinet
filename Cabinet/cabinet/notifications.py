"""Android local notifications for confirmed medicine dose schedules."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def build_dose_notification_payloads(
    doses: list[dict[str, Any]], now: datetime | None = None
) -> list[dict[str, Any]]:
    """Convert upcoming database reminders to local-time Android alarm payloads."""
    now = now or datetime.now()
    payloads = []
    for dose in doses:
        due_at = datetime.fromisoformat(dose["snoozed_until"] or dose["due_at"])
        if due_at <= now:
            continue
        medicine = dose["name"]
        if dose["strength"]:
            medicine += f" ({dose['strength']})"
        payloads.append(
            {
                "id": int(dose["id"]),
                "at": int(due_at.timestamp() * 1000),
                "title": f"Medicine reminder: {medicine}",
                "message": f"Time for {dose['dose']} · {dose['frequency']}",
            }
        )
    return payloads


def sync_android_dose_notifications(store, enabled: bool) -> bool | None:
    """Replace the Android alarm queue with the active profile's pending doses."""
    from kivy.utils import platform

    if platform != "android":
        return None

    from jnius import autoclass

    payloads = []
    if enabled:
        doses = store.list_upcoming_doses(limit=100000)
        payloads = build_dose_notification_payloads(doses)

    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    scheduler = autoclass(
        "org.cabinetapp.cabinet.notifications.NotificationScheduler"
    )
    scheduler.replaceAll(activity, json.dumps(payloads, ensure_ascii=False))
    return bool(scheduler.hasNotificationPermission(activity))
