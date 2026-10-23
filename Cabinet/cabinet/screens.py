"""Screen layouts and forms for Cabinet."""

from __future__ import annotations

import calendar as month_calendar
from datetime import date, datetime
from pathlib import Path

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.utils import platform

from cabinet.preferences import menstruation_tab_enabled
from cabinet.secure_storage import SecureStorageUnavailable


class CabinetScreen(Screen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.store = app.store
        self.palette = app.palette
        self.body = BoxLayout(orientation="vertical", spacing=dp(12), padding=dp(18))
        self.add_widget(self.body)
        self.build_content()

    def build_content(self) -> None:
        pass

    def refresh(self) -> None:
        self.palette = self.app.palette
        self.body.clear_widgets()
        self.build_content()

    def add_heading(self, title: str, subtitle: str = "") -> None:
        heading = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(68 if subtitle else 42),
            spacing=dp(1),
        )
        heading.add_widget(self.label(title, 23, True, self.palette["text"], dp(34)))
        if subtitle:
            heading.add_widget(
                self.label(subtitle, 12, False, self.palette["muted"], dp(24))
            )
        self.body.add_widget(heading)

    def label(self, text, size=14, bold=False, color=None, height=None):
        color = color or self.palette["text"]
        minimum_height = dp(height) if height is not None else dp(size + 13)
        label = Label(
            text=str(text),
            font_size=dp(size),
            bold=bold,
            color=color,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=minimum_height,
            text_size=(self.width - dp(36), None),
        )
        label.bind(
            width=lambda widget, width: setattr(
                widget, "text_size", (max(0, width), None)
            )
        )
        label.bind(
            texture_size=lambda widget, texture_size: setattr(
                widget, "height", max(minimum_height, texture_size[1] + dp(8))
            )
        )
        return label

    def button(self, text, callback, primary=False, height=44, variant=None):
        variant = variant or ("primary" if primary else "default")
        palette_key = f"button_{variant}"
        background = self.palette[palette_key]
        foreground = self.palette[f"{palette_key}_text"]
        pressed_background = self.palette[f"{palette_key}_pressed"]
        button = Button(
            text=text,
            size_hint_y=None,
            height=dp(height),
            font_size=dp(14),
            bold=primary,
            color=foreground,
            background_normal="",
            background_down="",
            background_color=(0, 0, 0, 0),
            padding=(dp(8), dp(4)),
        )

        from kivy.graphics import Color, RoundedRectangle

        with button.canvas.before:
            fill = Color(*background)
            shape = RoundedRectangle(pos=button.pos, size=button.size, radius=[dp(12)])

        def paint(widget, _value=None):
            shape.pos = widget.pos
            shape.size = widget.size
            fill.rgba = pressed_background if widget.state == "down" else background
            widget.color = foreground

        button.bind(pos=paint, size=paint, state=paint)
        button.bind(on_release=lambda *_: callback())
        return button

    def card(self, background=None, padding=14, spacing=5):
        from kivy.graphics import Color, RoundedRectangle

        box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding=dp(padding),
            spacing=dp(spacing),
        )
        box.bind(minimum_height=box.setter("height"))
        with box.canvas.before:
            Color(*(background or self.palette["surface"]))
            shape = RoundedRectangle(pos=box.pos, size=box.size, radius=[dp(17)])
        box.bind(pos=lambda widget, _: setattr(shape, "pos", widget.pos))
        box.bind(size=lambda widget, _: setattr(shape, "size", widget.size))
        return box

    def scroll(self):
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(12),
            padding=(0, 0, 0, dp(14)),
        )
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        self.body.add_widget(scroll)
        return content

    def section_title(self, parent, title, action_text=None, action=None):
        row = BoxLayout(size_hint_y=None, height=dp(32))
        row.add_widget(self.label(title, 16, True, self.palette["text"], dp(30)))
        if action_text:
            row.add_widget(Label())
            row.add_widget(
                self.button(action_text, action or (lambda: None), height=30)
            )
        parent.add_widget(row)

    def show_message(self, title: str, message: str) -> None:
        content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        content.add_widget(self.label(message, 14, False, self.palette["text"], dp(70)))
        popup = Popup(
            title=title,
            content=content,
            size_hint=(0.88, None),
            height=dp(190),
            auto_dismiss=True,
        )
        close = self.button("Done", popup.dismiss, primary=True, height=42)
        content.add_widget(close)
        popup.open()

    def show_form(
        self,
        title,
        fields,
        on_submit,
        submit_text="Save",
        optional_fields=None,
    ):
        content = BoxLayout(
            orientation="vertical", spacing=dp(9), padding=dp(16), size_hint_y=None
        )
        content.bind(minimum_height=content.setter("height"))
        inputs = {}
        for field in fields:
            key, label_text, hint, input_filter = field[:4]
            initial_value = field[4] if len(field) > 4 else ""
            content.add_widget(self.label(label_text, 12, True, self.palette["muted"], dp(20)))
            widget = TextInput(
                hint_text=hint,
                text=initial_value,
                multiline=False,
                size_hint_y=None,
                height=dp(43),
                padding=(dp(10), dp(10)),
                font_size=dp(14),
                foreground_color=self.palette["text"],
                background_color=self.palette["background"],
                cursor_color=self.palette["mint"],
                input_filter=input_filter,
            )
            inputs[key] = widget
            content.add_widget(widget)
        alarm_checkbox = None
        if optional_fields:
            alarm_row = BoxLayout(
                size_hint_y=None,
                height=dp(42),
                spacing=dp(8),
            )
            alarm_checkbox = CheckBox(
                active=False,
                size_hint=(None, None),
                size=(dp(32), dp(32)),
                color=self.palette["mint"],
            )
            alarm_row.add_widget(alarm_checkbox)
            alarm_row.add_widget(
                self.label(
                    "Add a daily alarm",
                    13,
                    True,
                    self.palette["text"],
                    dp(36),
                )
            )
            content.add_widget(alarm_row)
            optional_container = BoxLayout(
                orientation="vertical",
                size_hint_y=None,
                height=0,
                spacing=dp(9),
            )
            optional_widgets = []
            for field in optional_fields:
                key, label_text, hint, input_filter = field[:4]
                initial_value = field[4] if len(field) > 4 else ""
                label_widget = self.label(
                    label_text,
                    12,
                    True,
                    self.palette["muted"],
                    dp(20),
                )
                optional_container.add_widget(label_widget)
                widget = TextInput(
                    hint_text=hint,
                    text=initial_value,
                    multiline=False,
                    size_hint_y=None,
                    height=dp(43),
                    padding=(dp(10), dp(10)),
                    font_size=dp(14),
                    foreground_color=self.palette["text"],
                    background_color=self.palette["background"],
                    cursor_color=self.palette["mint"],
                    input_filter=input_filter,
                )
                inputs[key] = widget
                optional_container.add_widget(widget)
                optional_widgets.extend((label_widget, widget))

            def set_optional_visibility(_checkbox, active):
                optional_container.height = (
                    sum(widget.height + optional_container.spacing
                        for widget in optional_widgets)
                    if active
                    else 0
                )

            alarm_checkbox.bind(active=set_optional_visibility)
            content.add_widget(optional_container)
            content.add_widget(
                self.label(
                    (
                        "Choose exact 24-hour times and an end date. Android "
                        "notifications repeat daily through that date."
                        if platform == "android"
                        else "Choose exact 24-hour times and an end date. The "
                        "schedule appears in Calendar; system alarms are Android-only."
                    ),
                    11,
                    False,
                    self.palette["muted"],
                    dp(34),
                )
            )
        error_label = self.label("", 11, False, self.palette["danger"], dp(22))
        content.add_widget(error_label)
        buttons = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        scroll.add_widget(content)
        popup = Popup(
            title=title,
            content=scroll,
            size_hint=(0.92, 0.82),
            auto_dismiss=True,
        )
        cancel = self.button("Cancel", popup.dismiss, height=44)

        def submit(*_):
            values = {key: widget.text.strip() for key, widget in inputs.items()}
            if alarm_checkbox is not None:
                values["_optional_enabled"] = alarm_checkbox.active
            try:
                on_submit(values)
            except (ValueError, OSError) as error:
                error_label.text = str(error)
                return
            popup.dismiss()
            self.refresh()

        save = self.button(submit_text, submit, primary=True, height=44)
        buttons.add_widget(cancel)
        buttons.add_widget(save)
        content.add_widget(buttons)
        popup.open()
        return inputs

    def add_dose_card(self, parent, dose) -> None:
        from datetime import datetime

        card = self.card()
        due_at = datetime.fromisoformat(
            dose["snoozed_until"] or dose["due_at"]
        ).strftime("%a, %b %d · %H:%M")
        title = dose["name"]
        if dose["strength"]:
            title += f" · {dose['strength']}"
        card.add_widget(self.label(title, 14, True, self.palette["text"], dp(24)))
        detail = f"{dose['dose']} · {dose['frequency']} · {due_at}"
        card.add_widget(self.label(detail, 12, False, self.palette["muted"], dp(22)))
        if dose["instructions"]:
            card.add_widget(
                self.label(dose["instructions"], 11, False, self.palette["muted"], dp(20))
            )
        actions = BoxLayout(size_hint_y=None, height=dp(35), spacing=dp(6))
        for caption, action in (
            ("Taken", "taken"),
            ("Skip", "skipped"),
            ("Snooze 10 min", "snoozed"),
        ):
            actions.add_widget(
                self.button(
                    caption,
                    lambda reminder_id=dose["id"], selected=action:
                    self.update_dose_reminder(reminder_id, selected),
                    height=33,
                )
            )
        card.add_widget(actions)
        parent.add_widget(card)

    def update_dose_reminder(self, reminder_id: int, action: str) -> None:
        try:
            self.store.update_dose_reminder(reminder_id, action)
        except ValueError as error:
            self.show_message("Couldn't update dose", str(error))
            return
        self.app.sync_dose_notifications()
        for screen_name in ("home", "calendar"):
            screen = self.app.screens.get(screen_name)
            if screen is not None:
                screen.refresh()


class HomeScreen(CabinetScreen):
    def build_content(self):
        self.add_heading(f"Good day", self.app.formatted_today())
        content = self.scroll()
        summary = self.store.dashboard()

        hero = self.card(self.palette["navy"], padding=18, spacing=8)
        hero.add_widget(
            self.label("A calmer way to care for your family", 18, True, (1, 1, 1, 1), dp(30))
        )
        hero.add_widget(
            self.label(
                f"{summary['medicine_count']} medicines in your cabinet",
                13,
                False,
                (0.82, 0.91, 0.91, 1),
                dp(24),
            )
        )
        hero.add_widget(self.button("＋  Add a medicine", self.app.open_add_medicine, True))
        hero.add_widget(
            self.button("Scan Prescription", self.app.open_prescription_scanner, height=42)
        )
        content.add_widget(hero)

        medicines_enabled = (
            self.store.get_setting("feature_medicines", "true") == "true"
        )
        vaccines_enabled = (
            self.store.get_setting("feature_vaccines", "true") == "true"
        )
        if medicines_enabled:
            metrics = BoxLayout(size_hint_y=None, height=dp(106), spacing=dp(10))
            metrics.add_widget(
                self.metric_card(
                    str(summary["medicine_count"]),
                    "Medicines",
                    self.palette["mint_soft"],
                )
            )
            metrics.add_widget(
                self.metric_card(
                    str(len(summary["low_stock"])),
                    "Low stock",
                    self.palette["blue_soft"],
                    self.palette["warning"] if summary["low_stock"] else None,
                )
            )
            metrics.add_widget(
                self.metric_card(
                    str(len(summary["expiring"])),
                    "Expiring soon",
                    self.palette["mint_soft"],
                    self.palette["danger"] if summary["expiring"] else None,
                )
            )
            content.add_widget(metrics)

            self.section_title(content, "Needs a look")
            alerts = self.card()
            if not summary["low_stock"] and not summary["expiring"]:
                alerts.add_widget(
                    self.label(
                        "You're all caught up. Alerts will appear here.",
                        13,
                        False,
                        self.palette["muted"],
                    )
                )
            for medicine in summary["low_stock"][:3]:
                alerts.add_widget(
                    self.label(
                        f"Low stock · {medicine['name']} ({medicine['quantity']} left)",
                        13,
                        True,
                        self.palette["warning"],
                    )
                )
            for medicine in summary["expiring"][:3]:
                expired = medicine["expiry_date"] < summary["today"]
                alerts.add_widget(
                    self.label(
                        f"{'Past expiry' if expired else 'Expiry coming up'} · "
                        f"{medicine['name']} — {medicine['expiry_date']}",
                        13,
                        False,
                        self.palette["danger"],
                    )
                )
            content.add_widget(alerts)

        doses = self.store.list_upcoming_doses(limit=4)
        self.section_title(content, "Medicine doses")
        if doses:
            for dose in doses:
                self.add_dose_card(content, dose)
        else:
            dose_card = self.card()
            dose_card.add_widget(
                self.label(
                    "No upcoming in-app doses. Confirm a prescription to add a schedule.",
                    12,
                    False,
                    self.palette["muted"],
                )
            )
            content.add_widget(dose_card)

        self.section_title(
            content, "Coming up", "Add appointment", self.app.open_add_appointment
        )
        upcoming_card = self.card()
        if not summary["upcoming"]:
            upcoming_card.add_widget(
                self.label(
                    "No upcoming dates recorded. Add an appointment or a due date from an official record.",
                    13,
                    False,
                    self.palette["muted"],
                )
            )
        for item in summary["upcoming"]:
            if (
                not vaccines_enabled
                and item.get("kind") == "Vaccine due date"
            ):
                continue
            detail = f"{item.get('person', '')} · {item['appointment_date']}".strip(" ·")
            upcoming_card.add_widget(
                self.label(item["title"], 14, True, self.palette["text"], dp(24))
            )
            upcoming_card.add_widget(
                self.label(detail, 12, False, self.palette["muted"], dp(20))
            )
        content.add_widget(upcoming_card)

        if menstruation_tab_enabled(self.store):
            cycle_card = self.card(self.palette["blue_soft"])
            cycle_card.add_widget(
                self.label("Your private menstruation history", 15, True, self.palette["text"])
            )
            try:
                records = self.app.get_cycle_store().list_periods()
            except (SecureStorageUnavailable, OSError, ValueError) as error:
                cycle_card.add_widget(
                    self.label(
                        f"Private storage is unavailable: {error}",
                        12,
                        False,
                        self.palette["danger"],
                    )
                )
            else:
                if records:
                    cycle_card.add_widget(
                        self.label(
                            f"Last recorded start: {records[0]['first_day']}",
                            12,
                            False,
                            self.palette["muted"],
                        )
                    )
                else:
                    cycle_card.add_widget(
                        self.label(
                            "No period dates recorded yet.",
                            12,
                            False,
                            self.palette["muted"],
                        )
                    )
                cycle_card.add_widget(
                    self.button(
                        "Open private tracker",
                        lambda: self.app.navigate("cycle"),
                    )
                )
            content.add_widget(cycle_card)

        quick = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        if medicines_enabled:
            quick.add_widget(
                self.button("Add a medicine", self.app.open_add_medicine)
            )
        if vaccines_enabled:
            quick.add_widget(
                self.button("Record a vaccine", lambda: self.app.navigate("vaccines"))
            )
        quick.add_widget(
            self.button("Open calendar", lambda: self.app.navigate("calendar"))
        )
        content.add_widget(quick)

    def metric_card(self, value, title, color, number_color=None):
        card = self.card(color, padding=12, spacing=2)
        card.add_widget(
            self.label(value, 24, True, number_color or self.palette["navy"], dp(33))
        )
        card.add_widget(self.label(title, 10, False, self.palette["muted"], dp(20)))
        return card


class MedicinesScreen(CabinetScreen):
    def __init__(self, app, **kwargs):
        self.search_text = ""
        super().__init__(app, name="medicines", **kwargs)

    def build_content(self):
        self.add_heading("Medicines", "Keep stock and expiry dates up to date.")
        top = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        search = TextInput(
            hint_text="Search your cabinet",
            text=self.search_text,
            multiline=False,
            size_hint_y=None,
            height=dp(42),
            padding=(dp(12), dp(10)),
            background_color=self.palette["surface"],
            foreground_color=self.palette["text"],
        )
        search.bind(on_text_validate=lambda widget: self.apply_search(widget))
        top.add_widget(search)
        top.add_widget(self.button("Search", lambda: self.apply_search(search), height=42))
        top.add_widget(self.button("+ Add", self.open_medicine_form, True))
        self.body.add_widget(top)
        self.body.add_widget(
            self.button("Scan Prescription", self.app.open_prescription_scanner, True)
        )
        content = self.scroll()
        medicines = self.store.list_medicines(self.search_text)
        if not medicines:
            empty = self.card(self.palette["surface"], padding=18)
            empty.add_widget(
                self.label(
                    "Your cabinet starts here",
                    17,
                    True,
                    self.palette["text"],
                    dp(30),
                )
            )
            empty.add_widget(
                self.label(
                    "Add a medicine with its quantity and expiry date. Everything stays on this device.",
                    13,
                    False,
                    self.palette["muted"],
                )
            )
            empty.add_widget(self.button("Add your first medicine", self.open_medicine_form, True))
            content.add_widget(empty)
        for medicine in medicines:
            card = self.card()
            row = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))
            row.add_widget(
                self.label(medicine["name"], 16, True, self.palette["text"], dp(29))
            )
            row.add_widget(Label())
            row.add_widget(
                self.label(
                    f"{medicine['quantity']} left",
                    13,
                    True,
                    self.palette["danger"]
                    if medicine["quantity"] <= medicine["low_stock_threshold"]
                    else self.palette["mint"],
                    dp(28),
                )
            )
            card.add_widget(row)
            details = " · ".join(
                value for value in (medicine["strength"], medicine["form"]) if value
            )
            if details:
                card.add_widget(self.label(details, 12, False, self.palette["muted"], dp(21)))
            expiry = (
                f"Expiry date: {medicine['expiry_date']}"
                if medicine["expiry_date"]
                else "Expiry date not recorded (optional)"
            )
            card.add_widget(self.label(expiry, 12, False, self.palette["muted"], dp(21)))
            actions = BoxLayout(size_hint_y=None, height=dp(37), spacing=dp(7))
            actions.add_widget(
                self.button(
                    "− 1",
                    lambda item=medicine: self.change_stock(item, -1),
                    height=34,
                    variant="minus",
                )
            )
            actions.add_widget(
                self.button(
                    "+ 1",
                    lambda item=medicine: self.change_stock(item, 1),
                    height=34,
                    variant="plus",
                )
            )
            actions.add_widget(
                self.button(
                    "History",
                    lambda item=medicine: self.show_history(item),
                    height=34,
                    variant="history",
                )
            )
            actions.add_widget(
                self.button(
                    "Edit",
                    lambda item=medicine: self.edit_medicine(item),
                    height=34,
                    variant="edit",
                )
            )
            actions.add_widget(
                self.button(
                    "Delete",
                    lambda item=medicine: self.delete_medicine(item),
                    height=34,
                    variant="delete",
                )
            )
            card.add_widget(actions)
            content.add_widget(card)

    def apply_search(self, search):
        self.search_text = search.text
        self.refresh()

    def open_medicine_form(self):
        from datetime import date

        return self.show_form(
            "Add medicine",
            [
                ("name", "Medicine name *", "e.g. Acetaminophen", None),
                ("strength", "Strength", "e.g. 250 mg", None),
                ("form", "Form", "Tablet, liquid, cream…", None),
                ("quantity", "Current quantity *", "0", "int"),
                ("low_stock_threshold", "Alert when at or below", "e.g. 5", "int"),
                (
                    "expiry_date",
                    "Expiry Date (optional)",
                    "YYYY-MM-DD (leave blank if unknown)",
                    None,
                ),
                ("notes", "Notes", "Optional", None),
            ],
            self._save_new_medicine,
            optional_fields=[
                (
                    "alarm_times",
                    "Alarm times (24-hour, comma-separated)",
                    "08:00, 20:00",
                    None,
                ),
                (
                    "alarm_start_date",
                    "Alarm start date",
                    "YYYY-MM-DD",
                    None,
                    date.today().isoformat(),
                ),
                (
                    "alarm_end_date",
                    "Repeat through (end date)",
                    "YYYY-MM-DD",
                    None,
                ),
            ],
        )

    def _save_new_medicine(self, values):
        alarm_enabled = values.pop("_optional_enabled", False)
        alarm_times = None
        if alarm_enabled:
            alarm_times = [
                value.strip() for value in values["alarm_times"].split(",")
            ]
        self.store.add_medicine(
            values["name"],
            values["quantity"],
            values["low_stock_threshold"] or 0,
            values["strength"],
            values["form"],
            values["expiry_date"],
            values["notes"],
            alarm_start_date=values.get("alarm_start_date", ""),
            alarm_end_date=values.get("alarm_end_date", ""),
            alarm_times=alarm_times,
        )
        if alarm_enabled:
            self.app.set_reminders_enabled(True)

    def edit_medicine(self, medicine):
        fields = [
            ("name", "Medicine name *", "Enter medicine name", None, medicine["name"]),
            ("strength", "Strength", "e.g. 250 mg", None, medicine["strength"]),
            ("form", "Form", "Tablet, liquid, cream…", None, medicine["form"]),
            (
                "quantity",
                "Current quantity",
                "Enter quantity",
                "int",
                str(medicine["quantity"]),
            ),
            (
                "low_stock_threshold",
                "Alert when at or below",
                "Enter quantity",
                "int",
                str(medicine["low_stock_threshold"]),
            ),
            (
                "expiry_date",
                "Expiry Date (optional)",
                "YYYY-MM-DD (leave blank if unknown)",
                None,
                medicine["expiry_date"],
            ),
            ("notes", "Notes", "Optional", None, medicine["notes"]),
        ]

        def update(values):
            self.store.update_medicine(
                medicine["id"],
                **{
                    key: values[key]
                    for key in (
                        "name",
                        "strength",
                        "form",
                        "quantity",
                        "low_stock_threshold",
                        "expiry_date",
                        "notes",
                    )
                },
            )
            self.app.sync_dose_notifications()

        return self.show_form("Update medicine", fields, update, "Update")

    def change_stock(self, medicine, change):
        try:
            self.store.change_stock(medicine["id"], change, "Quick stock update")
            self.refresh()
        except ValueError as error:
            self.show_message("Couldn't update stock", str(error))

    def show_history(self, medicine):
        history = self.store.stock_history(medicine["id"])
        from kivy.graphics import Color, RoundedRectangle

        content = BoxLayout(
            orientation="vertical",
            padding=(dp(14), dp(14)),
            spacing=dp(8),
        )
        columns = BoxLayout(size_hint_y=None, height=dp(28), spacing=dp(5))

        def column_label(text, width, color):
            label = Label(
                text=text,
                size_hint=(None, 1) if width is not None else (1, 1),
                width=dp(width) if width is not None else 0,
                font_size=dp(10),
                bold=True,
                color=color,
                halign="left",
                valign="middle",
                shorten=True,
                shorten_from="right",
            )
            label.bind(
                size=lambda widget, size: setattr(widget, "text_size", size)
            )
            return label

        columns.add_widget(column_label("DATE", 78, self.palette["muted"]))
        columns.add_widget(column_label("CHANGE", 52, self.palette["muted"]))
        columns.add_widget(column_label("ON HAND", 64, self.palette["muted"]))
        columns.add_widget(column_label("ACTION / REASON", None, self.palette["muted"]))
        content.add_widget(columns)

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        rows = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(6),
            padding=(0, 0, 0, dp(4)),
        )
        rows.bind(minimum_height=rows.setter("height"))
        if history:
            for record in history:
                row = BoxLayout(
                    size_hint_y=None,
                    height=dp(54),
                    spacing=dp(5),
                    padding=(dp(8), dp(4)),
                )
                with row.canvas.before:
                    Color(*self.palette["surface"])
                    background = RoundedRectangle(
                        pos=row.pos, size=row.size, radius=[dp(9)]
                    )
                row.bind(
                    pos=lambda widget, _value, shape=background: setattr(
                        shape, "pos", widget.pos
                    ),
                    size=lambda widget, _value, shape=background: setattr(
                        shape, "size", widget.size
                    ),
                )
                row.add_widget(
                    column_label(record["changed_at"][:10], 78, self.palette["text"])
                )
                row.add_widget(
                    column_label(
                        f"{record['change_amount']:+}",
                        52,
                        self.palette["mint"],
                    )
                )
                row.add_widget(
                    column_label(
                        str(record["quantity_after"]),
                        64,
                        self.palette["text"],
                    )
                )
                reason = column_label(record["note"] or "Stock update", None, self.palette["muted"])
                reason.font_size = dp(11)
                reason.shorten = True
                row.add_widget(reason)
                rows.add_widget(row)
        else:
            rows.add_widget(
                self.label(
                    "No stock changes recorded.",
                    13,
                    False,
                    self.palette["muted"],
                    dp(40),
                )
            )
        scroll.add_widget(rows)
        content.add_widget(scroll)

        popup = Popup(
            title=f"{medicine['name']} · stock history",
            content=content,
            size_hint=(0.94, 0.86),
            auto_dismiss=True,
        )
        content.add_widget(
            self.button("Done", popup.dismiss, primary=True, height=42)
        )
        popup.open()
        return popup

    def delete_medicine(self, medicine):
        content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        content.add_widget(
            self.label(
                f"Remove {medicine['name']} and its stock history?",
                14,
                False,
                self.palette["text"],
                dp(50),
            )
        )
        buttons = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        popup = Popup(title="Remove medicine?", content=content, size_hint=(0.86, None), height=dp(160))
        buttons.add_widget(self.button("Cancel", popup.dismiss))

        def confirm():
            self.store.delete_medicine(medicine["id"])
            self.app.sync_dose_notifications()
            popup.dismiss()
            self.refresh()

        buttons.add_widget(
            self.button("Remove", confirm, variant="delete")
        )
        content.add_widget(buttons)
        popup.open()
        return popup


class VaccinesScreen(CabinetScreen):
    def __init__(self, app, **kwargs):
        self.search_text = ""
        super().__init__(app, name="vaccines", **kwargs)

    def build_content(self):
        self.add_heading("Vaccines", "Record what your family has received.")
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        search = TextInput(
            hint_text="Search people or records",
            text=self.search_text,
            multiline=False,
            size_hint_y=None,
            height=dp(42),
            padding=(dp(12), dp(10)),
            background_color=self.palette["surface"],
            foreground_color=self.palette["text"],
        )
        search.bind(on_text_validate=lambda widget: self.apply_search(widget))
        row.add_widget(search)
        row.add_widget(self.button("Go", lambda: self.apply_search(search), height=42))
        row.add_widget(self.button("+ Record", self.open_vaccine_form, True))
        self.body.add_widget(row)
        content = self.scroll()
        records = self.store.list_vaccines(self.search_text)
        if not records:
            card = self.card()
            card.add_widget(self.label("Family records, all together", 17, True))
            card.add_widget(
                self.label(
                    "Enter dates from official records or your healthcare professional. Cabinet does not suggest vaccine schedules.",
                    13,
                    False,
                    self.palette["muted"],
                )
            )
            card.add_widget(self.button("Add a vaccine record", self.open_vaccine_form, True))
            content.add_widget(card)
        for record in records:
            card = self.card()
            card.add_widget(
                self.label(record["vaccine_name"], 16, True, self.palette["text"], dp(28))
            )
            card.add_widget(
                self.label(
                    f"{record['person']}"
                    + (f" · {record['dose_label']}" if record["dose_label"] else ""),
                    13,
                    False,
                    self.palette["muted"],
                    dp(22),
                )
            )
            if record["administered_on"]:
                card.add_widget(
                    self.label(
                        f"Recorded date: {record['administered_on']}",
                        12,
                        False,
                        self.palette["muted"],
                        dp(20),
                    )
                )
            if record["next_due_on"]:
                card.add_widget(
                    self.label(
                        f"Next date from your record: {record['next_due_on']}",
                        12,
                        True,
                        self.palette["mint"],
                        dp(20),
                    )
                )
            if record["notes"]:
                card.add_widget(self.label(record["notes"], 12, False, self.palette["muted"]))
            card.add_widget(
                self.button("Remove record", lambda item=record: self.delete_record(item), height=35)
            )
            content.add_widget(card)

    def apply_search(self, search):
        self.search_text = search.text
        self.refresh()

    def open_vaccine_form(self):
        self.show_form(
            "Record a vaccine",
            [
                ("person", "Family member *", "e.g. Alex", None),
                ("vaccine_name", "Vaccine name *", "Use the name on the record", None),
                ("dose_label", "Dose / series label", "e.g. Dose 1", None),
                ("administered_on", "Date given", "YYYY-MM-DD", None),
                ("next_due_on", "Next date on official record", "YYYY-MM-DD", None),
                ("notes", "Notes", "Optional", None),
            ],
            lambda values: self.store.add_vaccine(
                values["person"],
                values["vaccine_name"],
                values["dose_label"],
                values["administered_on"],
                values["next_due_on"],
                values["notes"],
            ),
        )

    def delete_record(self, record):
        content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        content.add_widget(
            self.label(
                f"Remove the {record['vaccine_name']} record for {record['person']}?",
                14,
                False,
                self.palette["text"],
                dp(50),
            )
        )
        buttons = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        popup = Popup(title="Remove vaccine record?", content=content, size_hint=(0.86, None), height=dp(160))
        buttons.add_widget(self.button("Cancel", popup.dismiss))

        def confirm():
            self.store.delete_vaccine(record["id"])
            popup.dismiss()
            self.refresh()

        buttons.add_widget(self.button("Remove", confirm, True))
        content.add_widget(buttons)
        popup.open()


class CalendarScreen(CabinetScreen):
    def __init__(self, app, **kwargs):
        self.display_month = date.today().replace(day=1)
        self.selected_date = date.today()
        super().__init__(app, name="calendar", **kwargs)

    def build_content(self):
        self.add_heading(
            "Calendar",
            "Upcoming medicine doses, vaccine dates, and family appointments.",
        )
        self.body.add_widget(
            self.button("＋  Add appointment or reminder", self.open_appointment_form, True)
        )
        content = self.scroll()
        events_by_date = self._calendar_events()
        self._add_month_calendar(content, events_by_date)
        selected_events = events_by_date.get(self.selected_date.isoformat(), [])
        self.section_title(
            content,
            f"Events on {self.selected_date.strftime('%B %d, %Y')}",
        )
        if not selected_events:
            content.add_widget(
                self.label(
                    "No recorded events for this date.",
                    12,
                    False,
                    self.palette["muted"],
                    dp(28),
                )
            )
        for event in selected_events:
            if event["kind"] == "dose":
                self.add_dose_card(content, event["dose"])
                continue
            card = self.card(
                self.palette["mint_soft"]
                if event["date"] >= date.today().isoformat()
                else self.palette["surface"]
            )
            card.add_widget(
                self.label(
                    self._event_kind_label(event["kind"]),
                    10,
                    True,
                    self.palette["mint"],
                    dp(18),
                )
            )
            card.add_widget(
                self.label(event["title"], 15, True, self.palette["text"], dp(26))
            )
            if event["detail"]:
                card.add_widget(
                    self.label(
                        event["detail"], 12, False, self.palette["muted"], dp(20)
                    )
                )
            if event["kind"] == "appointment":
                card.add_widget(
                    self.button(
                        "Remove appointment",
                        lambda event_id=event["id"]: self.delete_appointment(event_id),
                        height=34,
                    )
                )
            content.add_widget(card)
        history = self.store.dose_history(limit=10)
        if history:
            self.section_title(content, "Recent dose history")
            for dose in history:
                card = self.card()
                card.add_widget(
                    self.label(
                        f"{dose['name']} · {dose['status'].capitalize()}",
                        13,
                        True,
                        self.palette["text"],
                        dp(22),
                    )
                )
                card.add_widget(
                    self.label(
                        f"{dose['due_at']} · {dose['dose']}",
                        11,
                        False,
                        self.palette["muted"],
                        dp(20),
                    )
                )
                content.add_widget(card)

    def _calendar_events(self):
        first_day = self.display_month
        last_day = self.display_month.replace(
            day=month_calendar.monthrange(
                self.display_month.year, self.display_month.month
            )[1]
        )
        today = date.today()
        events_by_date: dict[str, list[dict]] = {}

        def add_event(event):
            event_date = event["date"]
            if first_day.isoformat() <= event_date <= last_day.isoformat():
                events_by_date.setdefault(event_date, []).append(event)

        for item in self.store.list_appointments():
            add_event(
                {
                    "date": item["appointment_date"],
                    "title": item["title"],
                    "detail": " · ".join(
                        value for value in (item["person"], item["kind"]) if value
                    ),
                    "id": item["id"],
                    "kind": "appointment",
                }
            )
        for item in self.store.list_medicines():
            if item["expiry_date"]:
                add_event(
                    {
                        "date": item["expiry_date"],
                        "title": f"{item['name']} expiry",
                        "detail": f"Medicine · {item['quantity']} in stock",
                        "id": None,
                        "kind": "expiry",
                    }
                )
        for item in self.store.list_vaccines():
            if item["administered_on"]:
                add_event(
                    {
                        "date": item["administered_on"],
                        "title": f"{item['vaccine_name']} given",
                        "detail": " · ".join(
                            value
                            for value in (item["person"], item["dose_label"])
                            if value
                        ),
                        "id": None,
                        "kind": "vaccine_given",
                    }
                )
            if item["next_due_on"]:
                add_event(
                    {
                        "date": item["next_due_on"],
                        "title": f"{item['vaccine_name']} due",
                        "detail": item["person"],
                        "id": None,
                        "kind": "vaccine_due",
                    }
                )
        if last_day >= today:
            for dose in self.store.list_dose_reminders_between(
                max(first_day, today), last_day
            ):
                due_at = datetime.fromisoformat(
                    dose["snoozed_until"] or dose["due_at"]
                )
                add_event(
                    {
                        "date": due_at.date().isoformat(),
                        "title": dose["name"],
                        "detail": due_at.strftime("%H:%M"),
                        "id": dose["id"],
                        "kind": "dose",
                        "dose": dose,
                    }
                )
        for events in events_by_date.values():
            events.sort(
                key=lambda event: (
                    event.get("detail", ""),
                    event["title"].casefold(),
                )
            )
        return events_by_date

    @staticmethod
    def _event_kind_label(kind):
        return {
            "appointment": "APPOINTMENT",
            "expiry": "MEDICINE EXPIRY",
            "vaccine_given": "VACCINE GIVEN",
            "vaccine_due": "UPCOMING VACCINE",
        }.get(kind, kind.replace("_", " ").upper())

    def _add_month_calendar(self, parent, events_by_date):
        month_row = BoxLayout(
            size_hint_y=None,
            height=dp(42),
            spacing=dp(8),
        )
        month_row.add_widget(
            self.button("‹", self.previous_month, height=38)
        )
        month_row.add_widget(
            self.label(
                self.display_month.strftime("%B %Y"),
                16,
                True,
                self.palette["text"],
                dp(38),
            )
        )
        month_row.add_widget(
            self.button("›", self.next_month, height=38)
        )
        parent.add_widget(month_row)

        weekdays = GridLayout(
            cols=7,
            size_hint_y=None,
            height=dp(24),
        )
        for weekday in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
            weekdays.add_widget(
                self.label(weekday, 10, True, self.palette["muted"], dp(22))
            )
        parent.add_widget(weekdays)

        days = GridLayout(
            cols=7,
            spacing=dp(3),
            size_hint_y=None,
            height=dp(6 * 48),
        )
        start_weekday, days_in_month = month_calendar.monthrange(
            self.display_month.year, self.display_month.month
        )
        day_cells = [""] * start_weekday + list(range(1, days_in_month + 1))
        day_cells.extend([""] * (42 - len(day_cells)))
        for day_number in day_cells:
            if not day_number:
                days.add_widget(self.label("", 11, height=dp(44)))
                continue
            selected = self.display_month.replace(day=day_number)
            marked = bool(events_by_date.get(selected.isoformat()))
            is_selected = selected == self.selected_date
            background = (
                self.palette["button_primary"]
                if is_selected
                else self.palette["mint_soft"]
                if marked
                else self.palette["surface"]
            )
            foreground = (
                self.palette["button_primary_text"]
                if is_selected
                else self.palette["text"]
            )
            cell = Button(
                text=f"{day_number}\n•" if marked else str(day_number),
                size_hint_y=None,
                height=dp(45),
                font_size=dp(12),
                background_normal="",
                background_down="",
                background_color=background,
                color=foreground,
                on_release=lambda _button, selected_date=selected:
                    self.select_date(selected_date),
            )
            days.add_widget(cell)
        parent.add_widget(days)
        parent.add_widget(
            self.label(
                "A dot marks a medicine, vaccine, expiry, or appointment date.",
                11,
                False,
                self.palette["muted"],
                dp(26),
            )
        )

    def select_date(self, selected_date):
        self.selected_date = selected_date
        self.refresh()

    def previous_month(self):
        month = self.display_month.month - 1
        year = self.display_month.year
        if month == 0:
            month, year = 12, year - 1
        self._change_month(year, month)

    def next_month(self):
        month = self.display_month.month + 1
        year = self.display_month.year
        if month == 13:
            month, year = 1, year + 1
        self._change_month(year, month)

    def _change_month(self, year, month):
        day = min(
            self.selected_date.day,
            month_calendar.monthrange(year, month)[1],
        )
        self.display_month = date(year, month, 1)
        self.selected_date = date(year, month, day)
        self.refresh()

    def open_appointment_form(self):
        self.show_form(
            "Add a calendar item",
            [
                ("title", "Title *", "e.g. Clinic appointment", None),
                ("appointment_date", "Date *", "YYYY-MM-DD", None),
                ("person", "Family member", "Optional", None),
                ("kind", "Type", "Vaccination, medicine reminder…", None),
                ("notes", "Notes", "Optional", None),
            ],
            lambda values: self.store.add_appointment(
                values["title"],
                values["appointment_date"],
                values["person"],
                values["kind"] or "Vaccination",
                values["notes"],
            ),
        )

    def delete_appointment(self, appointment_id):
        try:
            self.store.delete_appointment(appointment_id)
            self.refresh()
        except ValueError as error:
            self.show_message("Couldn't remove appointment", str(error))


class SettingsScreen(CabinetScreen):
    def build_content(self):
        self.add_heading("Settings", "Your data stays yours.")
        content = self.scroll()

        theme = self.card()
        theme.add_widget(self.label("Appearance", 16, True))
        theme.add_widget(
            self.label("Choose a calm light or dark palette.", 12, False, self.palette["muted"])
        )
        choices = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        choices.add_widget(
            self.button(
                "Light",
                lambda: self.app.set_theme("light"),
                self.app.current_theme == "light",
            )
        )
        choices.add_widget(
            self.button(
                "Dark",
                lambda: self.app.set_theme("dark"),
                self.app.current_theme == "dark",
            )
        )
        theme.add_widget(choices)
        content.add_widget(theme)

        privacy = self.card()
        privacy.add_widget(self.label("Privacy", 16, True))
        privacy.add_widget(
            self.label(
                (
                    "You are using local-device mode. Records stay in this app's "
                    "private storage and no login service is contacted."
                    if self.app.current_session is None
                    else "Firebase verifies your email account. Health records stay "
                    "in a separate local database for this account; cloud sync is off."
                ),
                13,
                False,
                self.palette["muted"],
            )
        )
        content.add_widget(privacy)

        data = self.card()
        data.add_widget(self.label("Back up & export", 16, True))
        data.add_widget(
            self.label(
                "Create files in Cabinet's private app storage. Keep backups somewhere safe; exported files may contain sensitive family health details.",
                12,
                False,
                self.palette["muted"],
            )
        )
        data.add_widget(
            self.button("Create a backup", self.create_backup, height=40)
        )
        data.add_widget(self.button("Export all data (JSON)", self.export_json, height=40))
        data.add_widget(self.button("Export medicine list (CSV)", self.export_csv, height=40))
        content.add_widget(data)

        notifications = self.card()
        notifications.add_widget(self.label("Notifications", 16, True))
        notification_description = (
            "Cabinet can send local notifications for confirmed medicine dose "
            "times, even while the app is closed. Allow notifications when "
            "Android asks. Battery-saving settings may delay alerts."
            if platform == "android"
            else "Scheduled system notifications are supported in the Android "
            "app only. Medicine schedules remain visible in Home and Calendar "
            "on this device."
        )
        notifications.add_widget(
            self.label(
                notification_description
                + (
                    f"\n\n{self.app.notification_error}"
                    if self.app.notification_error
                    else ""
                ),
                12,
                False,
                self.palette["muted"],
            )
        )
        reminders_enabled = (
            self.store.get_setting("reminders_enabled", "false") == "true"
        )
        notifications.add_widget(
            self.button(
                "Turn medicine notifications off"
                if reminders_enabled
                else "Turn medicine notifications on",
                self.toggle_reminder_preference,
                height=38,
            )
        )
        content.add_widget(notifications)

        note = self.card(self.palette["blue_soft"])
        note.add_widget(self.label("A note on health records", 15, True))
        note.add_widget(
            self.label(
                "Cabinet organizes information you enter. It does not provide medical advice or recommend vaccine timing. Confirm dates with official records or a healthcare professional.",
                12,
                False,
                self.palette["text"],
            )
        )
        content.add_widget(note)

        content.add_widget(
            self.button(
                "Edit profile and setup preferences",
                self.app.edit_setup_preferences,
                height=40,
            )
        )

        features = self.card()
        features.add_widget(self.label("Cabinet features", 16, True))
        features.add_widget(
            self.label(
                "Hide a section without deleting its records.",
                12,
                False,
                self.palette["muted"],
            )
        )
        for key, title in (
            ("feature_medicines", "Medicine inventory"),
            ("feature_vaccines", "Vaccine tracker"),
        ):
            enabled = self.store.get_setting(key, "true") == "true"
            features.add_widget(
                self.button(
                    f"{'Hide' if enabled else 'Show'} {title}",
                    lambda setting=key, current=enabled: self.toggle_feature(
                        setting, current
                    ),
                    height=38,
                )
            )
        content.add_widget(features)

        cycle_enabled = self.store.get_setting("feature_cycle", "false") == "true"
        cycle = self.card()
        cycle.add_widget(self.label("Private Menstruation tracker", 16, True))
        cycle.add_widget(
            self.label(
                "Period history is stored in a separate encrypted database. "
                "On Windows its key is protected by Credential Manager; on Android "
                "it uses Android Keystore. Tracking is opt-in and the data is not "
                "included in inventory exports. The navigation tab is shown only "
                "for Female profiles aged 12 or older. "
                "Hiding it never deletes records.",
                12,
                False,
                self.palette["muted"],
            )
        )
        cycle.add_widget(
            self.button(
                "Disable tracker" if cycle_enabled else "Enable private tracker",
                self.toggle_cycle,
                primary=not cycle_enabled,
                height=40,
            )
        )
        if cycle_enabled:
            cycle.add_widget(
                self.button(
                    "Delete all cycle records",
                    self.confirm_delete_cycle_records,
                    height=40,
                )
            )
        content.add_widget(cycle)

        if self.app.current_session is not None:
            account = self.card()
            account.add_widget(self.label("Account", 16, True))
            account.add_widget(
                self.label(
                    f"Signed in as {self.app.current_session.email}. "
                    "Records are stored locally in this account's private app folder; "
                    "cloud sync is not enabled.",
                    12,
                    False,
                    self.palette["muted"],
                )
            )
            account.add_widget(
                self.button("Log out", self.app.logout, height=40)
            )
            self.account_error = self.label("", 12, False, self.palette["danger"])
            account.add_widget(self.account_error)
            self.error = self.account_error
            self.delete_account_button = self.button(
                "Delete account and local records",
                self.confirm_delete_account,
                height=40,
            )
            account.add_widget(self.delete_account_button)
            content.add_widget(account)
        else:
            account = self.card()
            account.add_widget(self.label("Optional account", 16, True))
            account.add_widget(
                self.label(
                    "Sign in or create a Firebase account to keep a separate local "
                    "profile on this device. Health records are not uploaded or synced.",
                    12,
                    False,
                    self.palette["muted"],
                )
            )
            account.add_widget(
                self.button(
                    "Create account",
                    lambda: self.app.show_flow("signup"),
                    primary=True,
                    height=40,
                )
            )
            account.add_widget(
                self.button(
                    "Log in",
                    lambda: self.app.show_flow("login"),
                    height=40,
                )
            )
            content.add_widget(account)

    def toggle_cycle(self):
        enabled = self.store.get_setting("feature_cycle", "false") == "true"
        if enabled:
            self.store.set_setting("feature_cycle", "false")
            self.app.configure_navigation()
            self.refresh()
            return
        try:
            self.app.get_cycle_store()
        except (SecureStorageUnavailable, OSError, ValueError) as error:
            self.show_message("Secure storage unavailable", str(error))
            return
        self.store.set_setting("feature_cycle", "true")
        self.app.configure_navigation()
        self.refresh()

    def confirm_delete_cycle_records(self):
        self.confirm_action(
            "Delete all cycle records?",
            "This permanently erases the private cycle database and its encryption key.",
            self.delete_cycle_records,
        )

    def delete_cycle_records(self):
        try:
            self.app.get_cycle_store().erase_all()
        except (SecureStorageUnavailable, OSError, ValueError) as error:
            self.show_message("Couldn't erase records", str(error))
            return
        self.app._cycle_store = None
        self.app._cycle_store_uid = None
        try:
            self.app.get_cycle_store()
        except (SecureStorageUnavailable, OSError, ValueError) as error:
            self.show_message("Private tracker disabled", str(error))
            return
        self.show_message("Records erased", "Private cycle history was deleted.")
        self.refresh()

    def confirm_delete_account(self):
        self.confirm_action(
            "Delete Cabinet account?",
            "This deletes the Firebase account and local Cabinet records for this account. This cannot be undone.",
            self.delete_account,
        )

    def delete_account(self):
        session = self.app.current_session
        if session is None:
            return
        self.app.authenticate(
            self.delete_account_button,
            self.app.delete_account_data,
            lambda _result: self.app.logout(),
        )

    def confirm_action(self, title, message, on_confirm):
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(8))
        content.add_widget(self.label(message, 13, False, self.palette["text"]))
        buttons = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        popup = Popup(
            title=title,
            content=content,
            size_hint=(0.9, None),
            height=dp(210),
        )
        buttons.add_widget(self.button("Cancel", popup.dismiss))

        def confirm():
            popup.dismiss()
            on_confirm()

        buttons.add_widget(self.button("Continue", confirm, True))
        content.add_widget(buttons)
        popup.open()

    def toggle_reminder_preference(self):
        enabled = self.store.get_setting("reminders_enabled", "false") == "true"
        self.app.set_reminders_enabled(not enabled)
        self.refresh()

    def toggle_feature(self, setting, current_value):
        self.store.set_setting(setting, str(not current_value).lower())
        self.app.configure_navigation()
        self.refresh()

    def create_backup(self):
        path = (
            Path(self.app.profile_data_dir)
            / "backups"
            / f"cabinet-{date.today().isoformat()}.sqlite3"
        )
        saved = self.store.create_backup(path)
        self.show_message("Backup created", f"Saved on this device at:\n{saved}")

    def export_json(self):
        path = Path(self.app.profile_data_dir) / "exports" / "cabinet-export.json"
        saved = self.store.export_json(path)
        self.show_message("Export ready", f"Saved on this device at:\n{saved}")

    def export_csv(self):
        path = Path(self.app.profile_data_dir) / "exports" / "medicines.csv"
        saved = self.store.export_medicines_csv(path)
        self.show_message("Export ready", f"Saved on this device at:\n{saved}")
