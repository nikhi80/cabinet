"""Prescription image selection, OCR review, and confirmed local saving."""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Thread

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.checkbox import CheckBox
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.utils import platform

from cabinet.prescription_scanner import (
    extract_medicines,
    image_sha256,
    prescription_fingerprint,
    read_prescription_text,
)
from cabinet.screens import CabinetScreen

logger = logging.getLogger(__name__)

_NEW_INVENTORY = "Create new inventory record"
_FIELDS = (
    ("name", "Medicine name"),
    ("strength", "Strength"),
    ("dose", "Dose per intake"),
    ("frequency", "Frequency"),
    ("instructions", "Food / other instructions"),
    ("start_date", "Start date (YYYY-MM-DD)"),
    ("duration_days", "Treatment duration (days)"),
    ("prescribed_quantity", "Quantity prescribed"),
    ("reminder_times", "Reminder times (24-hour HH:MM, comma-separated)"),
)


class PrescriptionScreen(CabinetScreen):
    def __init__(self, app, **kwargs):
        self.image_path = ""
        self.ocr_text = ""
        self.status_message = ""
        self.status_color = None
        self._ocr_token = 0
        self.review_items: list[dict] = []
        self._cards: list[dict] = []
        super().__init__(app, name="prescription", **kwargs)

    def refresh(self) -> None:
        if self._cards:
            self.review_items = self._capture_review_items()
        super().refresh()

    def build_content(self):
        self.add_heading(
            "Scan prescription",
            "OCR suggestions are not medical advice. Check every detail against the original.",
        )
        self.body.add_widget(
            self.button("Back to Home", lambda: self.app.navigate("home"), height=38)
        )
        content = self.scroll()

        image_card = self.card()
        image_card.add_widget(
            self.label(
                "Prescription image preview",
                15,
                True,
                self.palette["text"],
                dp(26),
            )
        )
        if self.image_path and Path(self.image_path).is_file():
            preview = Image(
                source=self.image_path,
                size_hint_y=None,
                height=dp(220),
                fit_mode="contain",
            )
            image_card.add_widget(preview)
        else:
            image_card.add_widget(
                self.label(
                    "Choose or take a clear photo to begin.",
                    13,
                    False,
                    self.palette["muted"],
                    dp(48),
                )
            )
        image_actions = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        image_actions.add_widget(
            self.button("Upload / replace image", self.choose_image, height=40)
        )
        image_actions.add_widget(
            self.button("Take / retake photo", self.take_photo, height=40)
        )
        image_card.add_widget(image_actions)
        image_card.add_widget(
            self.button("Extract text with OCR", self.run_ocr, True, height=42)
        )
        self.status_label = self.label(
            self.status_message,
            12,
            False,
            self.status_color or self.palette["danger"],
            dp(32),
        )
        image_card.add_widget(self.status_label)
        content.add_widget(image_card)

        if self.ocr_text:
            text_card = self.card()
            text_card.add_widget(self.label("Text read from the image", 14, True))
            raw_text = TextInput(
                text=self.ocr_text,
                readonly=True,
                multiline=True,
                size_hint_y=None,
                height=dp(120),
                foreground_color=self.palette["text"],
                background_color=self.palette["background"],
            )
            text_card.add_widget(raw_text)
            content.add_widget(text_card)

        review = self.card(self.palette["blue_soft"])
        review.add_widget(self.label("Review every medicine", 16, True))
        review.add_widget(
            self.label(
                "Fields from OCR are only suggestions. Blank or unclear values need "
                "confirmation. Cabinet will not infer a dose or schedule.",
                12,
                False,
                self.palette["muted"],
            )
        )
        review.add_widget(
            self.button("＋ Add medicine", self.add_medicine_card, height=38)
        )
        self.cards_parent = review
        self._cards = []
        for index, item in enumerate(self.review_items):
            self._add_review_card(review, index, item)
        review.add_widget(
            self.button("Confirm prescription and save", self.save_prescription, True, 46)
        )
        content.add_widget(review)

    def _text_input(self, initial: str, hint: str) -> TextInput:
        return TextInput(
            text=str(initial or ""),
            hint_text=hint,
            multiline=False,
            size_hint_y=None,
            height=dp(40),
            padding=(dp(9), dp(9)),
            font_size=dp(13),
            foreground_color=self.palette["text"],
            background_color=self.palette["surface"],
            cursor_color=self.palette["mint"],
        )

    def _add_review_card(self, parent, index: int, item: dict) -> None:
        card = self.card(padding=11, spacing=3)
        card.add_widget(self.label(f"Medicine {index + 1}", 15, True))
        controls = {}
        for key, caption in _FIELDS:
            value = item.get(key, "")
            marker = "OCR suggestion · confirm" if value else "Needs confirmation"
            card.add_widget(
                self.label(f"{caption} · {marker}", 11, True, self.palette["muted"], dp(20))
            )
            controls[key] = self._text_input(value, caption)
            card.add_widget(controls[key])

        end_label = self.label(
            "Calculated end date: enter a start date and duration",
            11,
            False,
            self.palette["muted"],
            dp(22),
        )
        card.add_widget(end_label)

        inventory_matches = self.store.matching_medicines(
            str(item.get("name", "")), str(item.get("strength", ""))
        )
        inventory_options = {
            f"Update existing #{medicine['id']}: {medicine['name']}"
            + (f" · {medicine['strength']}" if medicine["strength"] else ""):
            medicine["id"]
            for medicine in inventory_matches
        }
        choices = list(inventory_options)
        if _NEW_INVENTORY not in choices:
            choices.append(_NEW_INVENTORY)
        selected_inventory_id = item.get("inventory_id")
        current = next(
            (
                choice
                for choice, medicine_id in inventory_options.items()
                if medicine_id == selected_inventory_id
            ),
            item.get("inventory_choice") or next(iter(inventory_options), _NEW_INVENTORY),
        )
        if current not in choices:
            current = next(iter(inventory_options), _NEW_INVENTORY)
        card.add_widget(
            self.label(
                "Inventory match · existing records are reused to avoid duplicates",
                11,
                True,
                self.palette["muted"],
                dp(32),
            )
        )
        inventory = Spinner(
            text=current,
            values=choices,
            size_hint_y=None,
            height=dp(40),
            background_color=self.palette["surface"],
            color=self.palette["text"],
        )
        card.add_widget(inventory)

        purchased_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(7))
        purchased = CheckBox(
            size_hint=(None, 1), width=dp(36), active=bool(item.get("purchased", False))
        )
        purchased_row.add_widget(purchased)
        purchased_row.add_widget(
            self.label("Purchased? (prescribed quantity is not current stock)", 11)
        )
        card.add_widget(purchased_row)
        card.add_widget(
            self.label("How many units were purchased?", 11, True, self.palette["muted"], dp(20))
        )
        purchased_quantity = self._text_input(
            item.get("purchased_quantity", ""), "Enter purchased amount"
        )
        purchased_quantity.disabled = not purchased.active
        purchased.bind(
            active=lambda _widget, active: setattr(purchased_quantity, "disabled", not active)
        )
        card.add_widget(purchased_quantity)

        reminder_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(7))
        create_reminders = CheckBox(
            size_hint=(None, 1),
            width=dp(36),
            active=bool(item.get("create_reminders", True)),
        )
        reminder_row.add_widget(create_reminders)
        reminder_row.add_widget(
            self.label("Create reminders (requires confirmed frequency, dates and exact times)", 11)
        )
        card.add_widget(reminder_row)
        confirm_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(7))
        confirmed = CheckBox(
            size_hint=(None, 1), width=dp(36), active=bool(item.get("confirmed", False))
        )
        confirm_row.add_widget(confirmed)
        confirm_row.add_widget(
            self.label("I checked this medicine's details against the prescription", 11, True)
        )
        card.add_widget(confirm_row)
        card.add_widget(
            self.button("Remove medicine", lambda: self.remove_medicine_card(index), height=34)
        )

        record = {
            "controls": controls,
            "end_label": end_label,
            "inventory": inventory,
            "inventory_options": inventory_options,
            "purchased": purchased,
            "purchased_quantity": purchased_quantity,
            "create_reminders": create_reminders,
            "confirmed": confirmed,
        }
        self._cards.append(record)
        controls["start_date"].bind(
            text=lambda *_args, fields=controls, label=end_label: self._update_end_date(
                fields, label
            )
        )
        controls["duration_days"].bind(
            text=lambda *_args, fields=controls, label=end_label: self._update_end_date(
                fields, label
            )
        )
        controls["name"].bind(
            text=lambda *_args, fields=controls, select=inventory, row=record:
            self._refresh_inventory_options(fields, select, row)
        )
        controls["strength"].bind(
            text=lambda *_args, fields=controls, select=inventory, row=record:
            self._refresh_inventory_options(fields, select, row)
        )
        self._update_end_date(controls, end_label)
        parent.add_widget(card)

    def _refresh_inventory_options(self, controls, spinner, record) -> None:
        matches = self.store.matching_medicines(
            controls["name"].text, controls["strength"].text
        )
        options = {
            f"Update existing #{medicine['id']}: {medicine['name']}"
            + (f" · {medicine['strength']}" if medicine["strength"] else ""):
            medicine["id"]
            for medicine in matches
        }
        record["inventory_options"] = options
        spinner.values = list(options) + [_NEW_INVENTORY]
        if spinner.text not in options:
            spinner.text = next(iter(options), _NEW_INVENTORY)

    @staticmethod
    def _update_end_date(controls, label) -> None:
        from datetime import date, timedelta

        try:
            start = date.fromisoformat(controls["start_date"].text.strip())
            duration = int(controls["duration_days"].text.strip())
            if duration < 1:
                raise ValueError
        except ValueError:
            label.text = "Calculated end date: enter a valid start date and duration"
            return
        label.text = f"Calculated end date: {(start + timedelta(days=duration - 1)).isoformat()}"

    def _capture_review_items(self) -> list[dict]:
        captured = []
        for record in self._cards:
            item = {
                key: widget.text.strip()
                for key, widget in record["controls"].items()
            }
            inventory_id = record["inventory_options"].get(record["inventory"].text)
            item.update(
                {
                    "inventory_id": inventory_id,
                    "inventory_choice": record["inventory"].text,
                    "purchased": record["purchased"].active,
                    "purchased_quantity": record["purchased_quantity"].text.strip(),
                    "create_reminders": record["create_reminders"].active,
                    "confirmed": record["confirmed"].active,
                }
            )
            captured.append(item)
        return captured

    def _rebuild_cards(self) -> None:
        if hasattr(self, "cards_parent"):
            self.cards_parent.clear_widgets()
            self.cards_parent.add_widget(self.label("Review every medicine", 16, True))
            self.cards_parent.add_widget(
                self.label(
                    "Fields from OCR are only suggestions. Blank or unclear values need "
                    "confirmation. Cabinet will not infer a dose or schedule.",
                    12,
                    False,
                    self.palette["muted"],
                )
            )
            self.cards_parent.add_widget(
                self.button("＋ Add medicine", self.add_medicine_card, height=38)
            )
            self._cards = []
            for index, item in enumerate(self.review_items):
                self._add_review_card(self.cards_parent, index, item)
            self.cards_parent.add_widget(
                self.button("Confirm prescription and save", self.save_prescription, True, 46)
            )

    def add_medicine_card(self) -> None:
        if self._cards:
            self.review_items = self._capture_review_items()
        self.review_items.append({})
        self._rebuild_cards()

    def remove_medicine_card(self, index: int) -> None:
        self.review_items = self._capture_review_items()
        self.review_items.pop(index)
        self._rebuild_cards()

    def choose_image(self) -> None:
        if platform == "android":
            try:
                from plyer import filechooser
            except ImportError as error:
                self._show_error(
                    "Image picker unavailable. Install Plyer in the Android build."
                )
                logger.error("Plyer file chooser is unavailable: %s", error)
                return
            try:
                filechooser.open_file(
                    on_selection=self._mobile_file_selected,
                    filters=["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp"],
                )
            except Exception:
                logger.exception("Android image picker failed")
                self._show_error(
                    "Cabinet couldn't open the image picker. Try another image or "
                    "restart the app."
                )
            return

        chooser = FileChooserListView(
            path=str(Path.home()),
            filters=["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp"],
            dirselect=False,
        )
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        content.add_widget(chooser)
        popup = Popup(title="Choose a prescription image", content=content, size_hint=(0.94, 0.9))
        buttons = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        buttons.add_widget(self.button("Cancel", popup.dismiss))

        def use_selected():
            if not chooser.selection:
                self._show_error("Select an image file first.")
                return
            self._set_image(chooser.selection[0])
            popup.dismiss()

        buttons.add_widget(self.button("Use image", use_selected, True))
        content.add_widget(buttons)
        popup.open()

    def _mobile_file_selected(self, selection) -> None:
        if selection:
            Clock.schedule_once(lambda _dt: self._set_image(selection[0]), 0)

    def take_photo(self) -> None:
        if platform != "android":
            self._show_error(
                "Camera capture is available through Plyer on supported Android devices. "
                "On this desktop build, use Upload / replace image."
            )
            return
        destination = Path(self.app.user_data_dir) / "prescriptions" / "capture.jpg"
        destination.parent.mkdir(parents=True, exist_ok=True)

        def completed(path):
            if path:
                Clock.schedule_once(
                    lambda _dt: self._set_captured_image(path),
                    0,
                )

        def open_camera():
            try:
                from plyer import camera

                camera.take_picture(
                    filename=str(destination),
                    on_complete=completed,
                )
            except Exception:
                logger.exception("Android camera launch failed")
                self._show_error(
                    "Cabinet couldn't open the camera. Check camera permission "
                    "and try again."
                )

        try:
            from android.permissions import check_permission, request_permissions

            if check_permission("android.permission.CAMERA"):
                open_camera()
            else:
                request_permissions(
                    ["android.permission.CAMERA"],
                    lambda _permissions, grants: (
                        open_camera()
                        if grants and all(grants)
                        else self._show_error(
                            "Camera permission is required to take a prescription photo."
                        )
                    ),
                )
        except Exception:
            logger.exception("Android camera permission check failed")
            self._show_error(
                "Cabinet couldn't request camera access. Use Upload / replace image instead."
            )

    def _set_captured_image(self, path: str) -> None:
        try:
            self._set_image(path)
        except (OSError, ValueError) as error:
            logger.exception("Couldn't open the captured prescription image")
            self._show_error(f"Cabinet couldn't open the captured image: {error}")

    def _set_image(self, path: str) -> None:
        selected = Path(path)
        if not selected.is_file():
            self._show_error("The selected image could not be opened.")
            return
        self.image_path = str(selected)
        self._ocr_token += 1
        self.ocr_text = ""
        self.review_items = []
        self._cards = []
        self.status_message = ""
        self.status_color = self.palette["danger"]
        self.refresh()

    def run_ocr(self) -> None:
        if not self.image_path:
            self._show_error("Choose or take a prescription image first.")
            return
        self._ocr_token += 1
        request_id = self._ocr_token
        image_path = self.image_path
        self.status_color = self.palette["muted"]
        self.status_message = "Reading the image locally…"
        self.status_label.color = self.status_color
        self.status_label.text = self.status_message

        def worker():
            try:
                text = read_prescription_text(image_path)
            except Exception as error:
                logger.exception("Prescription OCR failed")
                Clock.schedule_once(
                    lambda _dt, message=str(error), token=request_id:
                    self._ocr_failed(message, token),
                    0,
                )
            else:
                Clock.schedule_once(
                    lambda _dt, result=text, token=request_id:
                    self._ocr_succeeded(result, token),
                    0,
                )

        Thread(target=worker, name="cabinet-prescription-ocr", daemon=True).start()

    def _ocr_failed(self, message: str, request_id: int) -> None:
        if request_id != self._ocr_token:
            return
        self.status_color = self.palette["danger"]
        self.status_message = message
        self.status_label.color = self.status_color
        self.status_label.text = self.status_message

    def _ocr_succeeded(self, text: str, request_id: int) -> None:
        if request_id != self._ocr_token:
            return
        self.ocr_text = text
        self.review_items = extract_medicines(text)
        if not self.review_items:
            self.review_items = [{}]
            self.status_color = self.palette["warning"]
            self.status_message = (
                "No medicine details were confidently recognized. Add a medicine and "
                "enter the information from the prescription."
            )
        else:
            self.status_color = self.palette["muted"]
            self.status_message = (
                "Review the suggestions below. OCR has not confirmed any field."
            )
        self._cards = []
        self.refresh()

    def _show_error(self, message: str) -> None:
        self.status_color = self.palette["danger"]
        self.status_message = message
        self.status_label.color = self.status_color
        self.status_label.text = self.status_message

    def save_prescription(self) -> None:
        items = self._capture_review_items()
        try:
            fingerprint = prescription_fingerprint(items)
            digest = image_sha256(self.image_path) if self.image_path else ""
            result = self.store.confirm_prescription(
                items,
                fingerprint,
                self.ocr_text,
                digest,
            )
        except (ValueError, OSError) as error:
            self._show_error(str(error))
            return
        if result["duplicate"]:
            if result["reminders_added"]:
                message = (
                    "This prescription was already saved, so Cabinet did not add "
                    "stock again. A previously missing reminder schedule was added "
                    "from your newly confirmed times."
                )
            else:
                message = (
                    "Cabinet recognized the same confirmed prescription and did not "
                    "add stock or duplicate reminders. If you bought more medicine, "
                    "update its stock from the Medicines screen."
                )
            self.show_message(
                "Prescription already saved",
                message,
            )
            if result["reminders_added"]:
                self.app.sync_dose_notifications()
            return
        if any(item["create_reminders"] for item in items):
            self.app.sync_dose_notifications()
        for screen_name in ("home", "medicines", "calendar"):
            screen = self.app.screens.get(screen_name)
            if screen is not None:
                screen.refresh()
        if any(item["create_reminders"] for item in items):
            schedule_message = (
                "Confirmed dose schedules are visible in Home and Calendar while "
                "Cabinet is open."
            )
        else:
            schedule_message = (
                "No reminder schedule was requested; the prescription and inventory "
                "details were still saved."
            )
        self.show_message(
            "Prescription saved",
            "Confirmed details were saved to Medicine inventory. Cabinet added only "
            "amounts marked purchased; existing stock was left unchanged otherwise "
            "(new entries start at zero). "
            + schedule_message,
        )
        self.app.navigate("home")
