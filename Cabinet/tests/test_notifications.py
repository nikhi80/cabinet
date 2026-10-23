import unittest
from datetime import datetime

from cabinet.notifications import build_dose_notification_payloads


class DoseNotificationTests(unittest.TestCase):
    def test_builds_notification_from_due_time_and_medicine_details(self):
        now = datetime(2030, 1, 2, 8, 0)
        due_at = datetime(2030, 1, 2, 9, 30)
        payloads = build_dose_notification_payloads(
            [
                {
                    "id": 7,
                    "due_at": due_at.isoformat(),
                    "snoozed_until": "",
                    "name": "Medicine",
                    "strength": "10 mg",
                    "dose": "1 tablet",
                    "frequency": "Once daily",
                }
            ],
            now,
        )

        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["id"], 7)
        self.assertEqual(payloads[0]["at"], int(due_at.timestamp() * 1000))
        self.assertEqual(payloads[0]["title"], "Medicine reminder: Medicine (10 mg)")
        self.assertEqual(payloads[0]["message"], "Time for 1 tablet · Once daily")

    def test_uses_snooze_time_and_omits_already_due_reminders(self):
        now = datetime(2030, 1, 2, 8, 0)
        payloads = build_dose_notification_payloads(
            [
                {
                    "id": 1,
                    "due_at": datetime(2030, 1, 2, 7, 0).isoformat(),
                    "snoozed_until": datetime(2030, 1, 2, 8, 10).isoformat(),
                    "name": "Medicine",
                    "strength": "",
                    "dose": "1",
                    "frequency": "Once daily",
                },
                {
                    "id": 2,
                    "due_at": datetime(2030, 1, 2, 7, 0).isoformat(),
                    "snoozed_until": "",
                    "name": "Old dose",
                    "strength": "",
                    "dose": "1",
                    "frequency": "Once daily",
                },
            ],
            now,
        )

        self.assertEqual([item["id"] for item in payloads], [1])
        self.assertEqual(
            payloads[0]["at"],
            int(datetime(2030, 1, 2, 8, 10).timestamp() * 1000),
        )

    def test_preserves_negative_medicine_alarm_ids(self):
        due_at = datetime(2030, 1, 2, 9, 30)
        payloads = build_dose_notification_payloads(
            [
                {
                    "id": -2,
                    "due_at": due_at.isoformat(),
                    "snoozed_until": "",
                    "name": "Daily medicine",
                    "strength": "",
                    "dose": "Scheduled alarm",
                    "frequency": "Daily",
                }
            ],
            now=datetime(2030, 1, 2, 8, 0),
        )

        self.assertEqual(payloads[0]["id"], -2)


if __name__ == "__main__":
    unittest.main()
