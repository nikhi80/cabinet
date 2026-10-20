"""Optional menstrual record screen with private storage boundaries."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.textinput import TextInput

from cabinet.cycle import estimate_next_period_window
from cabinet.secure_storage import SecureStorageUnavailable


class CycleScreen(Screen):
    def __init__(self, app, **kwargs):
        super().__init__(name="cycle", **kwargs)
        self.app = app
        self.owner_uid = app.current_uid
        self.store = None
        self.storage_error = ""
        self.display_month = date.today().replace(day=1)
        if self.app.store.get_setting("feature_cycle", "false") == "true":
            self._prepare_store()
        self.refresh()

    def _prepare_store(self):
        try:
            self.store = self.app.get_cycle_store()
        except (SecureStorageUnavailable, OSError, ValueError) as error:
            self.storage_error = str(error)

    def refresh(self):
        self.clear_widgets()
        palette = self.app.palette
        body = BoxLayout(
            orientation="vertical", padding=dp(18), spacing=dp(12)
        )
        body.add_widget(
            Label(
                text="Menstruation history",
                font_size=dp(24),
                bold=True,
                color=palette["text"],
                halign="left",
                size_hint_y=None,
                height=dp(38),
            )
        )
        scroll = __import__("kivy.uix.scrollview", fromlist=["ScrollView"]).ScrollView(
            do_scroll_x=False, bar_width=dp(3)
        )
        content = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=dp(10)
        )
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        body.add_widget(scroll)
        tracker_enabled = (
            self.app.store.get_setting("feature_cycle", "false") == "true"
        )
        if not tracker_enabled:
            content.add_widget(
                self._label(
                    "The private tracker is optional and currently disabled. "
                    "Your profile only controls tab visibility; it does not enable "
                    "tracking or reveal saved records.",
                    palette["muted"],
                )
            )
            content.add_widget(
                self._button(
                    "Enable private tracker",
                    self.enable_tracker,
                    True,
                )
            )
        elif self.store is None:
            self._prepare_store()
        if tracker_enabled and self.store is None:
            content.add_widget(
                self._label(
                    self.storage_error
                    or "Secure storage is unavailable; private tracking stays disabled.",
                    palette["danger"],
                )
            )
        elif tracker_enabled:
            content.add_widget(
                self._label(
                    "Cycle dates can vary naturally. Cabinet records what you enter; "
                    "it does not diagnose, identify ovulation, or predict fertility."
                )
            )
            content.add_widget(self._button("＋  Log period", self.open_form, True))
            records = self.store.list_periods()
            self._add_calendar(content, records)
            estimate = estimate_next_period_window(
                [record["first_day"] for record in records]
            )
            if estimate:
                content.add_widget(
                    self._label(
                        "Historical estimate only · based on the range of your "
                        "last recorded intervals; it may be inaccurate.\n"
                        f"Possible next start window: {estimate[0].isoformat()} – "
                        f"{estimate[1].isoformat()}",
                        palette["muted"],
                    )
                )
            else:
                content.add_widget(
                    self._label(
                        "Possible date estimates are shown only after at least four "
                        "start dates have been recorded."
                    )
                )
            for record in records:
                card = BoxLayout(
                    orientation="vertical",
                    size_hint_y=None,
                    padding=dp(12),
                    spacing=dp(5),
                )
                card.bind(minimum_height=card.setter("height"))
                card.add_widget(
                    self._label(
                        record["first_day"]
                        + (
                            f" — {record['last_day']}"
                            if record["last_day"]
                            else ""
                        ),
                        palette["text"],
                        bold=True,
                    )
                )
                for key, title in (
                    ("symptoms", "Symptoms"),
                    ("notes", "Notes"),
                ):
                    if record.get(key):
                        card.add_widget(
                            self._label(
                                f"{title}: {record[key]}", palette["muted"]
                            )
                        )
                actions = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(7))
                actions.add_widget(
                    self._button(
                        "Edit",
                        lambda item=record: self.open_form(item),
                    )
                )
                actions.add_widget(
                    self._button(
                        "Delete",
                        lambda item=record: self.confirm_delete(item),
                    )
                )
                card.add_widget(actions)
                content.add_widget(card)
        self.add_widget(body)

    def enable_tracker(self):
        self.app.screens["settings"].toggle_cycle()
        self.refresh()

    def _add_calendar(self, parent, records):
        palette = self.app.palette
        month_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
        month_row.add_widget(self._button("‹", self.previous_month))
        month_row.add_widget(
            self._label(
                self.display_month.strftime("%B %Y"),
                palette["text"],
                bold=True,
            )
        )
        month_row.add_widget(self._button("›", self.next_month))
        parent.add_widget(month_row)

        marked_days = set()
        for record in records:
            first = date.fromisoformat(record["first_day"])
            last = date.fromisoformat(record["last_day"] or record["first_day"])
            current = first
            while current <= last:
                marked_days.add(current)
                current += timedelta(days=1)

        grid = GridLayout(cols=7, spacing=dp(3), size_hint_y=None, height=dp(238))
        for weekday in ("M", "T", "W", "T", "F", "S", "S"):
            grid.add_widget(
                Label(
                    text=weekday,
                    font_size=dp(10),
                    bold=True,
                    color=palette["muted"],
                )
            )
        month_start_weekday, days_in_month = calendar.monthrange(
            self.display_month.year, self.display_month.month
        )
        for _ in range(month_start_weekday):
            grid.add_widget(Label(text=""))
        for day in range(1, days_in_month + 1):
            current = self.display_month.replace(day=day)
            selected = current in marked_days
            grid.add_widget(
                Button(
                    text=str(day),
                    font_size=dp(11),
                    background_normal="",
                    background_color=(
                        palette["gold"] if selected else palette["surface"]
                    ),
                    color=palette["text"],
                    disabled=True,
                )
            )
        for _ in range((7 - ((month_start_weekday + days_in_month) % 7)) % 7):
            grid.add_widget(Label(text=""))
        parent.add_widget(grid)
        parent.add_widget(
            self._label("Gold marks dates you've logged.", palette["muted"])
        )

    def previous_month(self):
        month = self.display_month.month - 1
        year = self.display_month.year
        if month == 0:
            month, year = 12, year - 1
        self.display_month = self.display_month.replace(year=year, month=month)
        self.refresh()

    def next_month(self):
        month = self.display_month.month + 1
        year = self.display_month.year
        if month == 13:
            month, year = 1, year + 1
        self.display_month = self.display_month.replace(year=year, month=month)
        self.refresh()

    def _label(self, text, color=None, bold=False):
        return Label(
            text=text,
            size_hint_y=None,
            height=dp(50 if "\n" in text else 34),
            font_size=dp(13),
            bold=bold,
            color=color or self.app.palette["text"],
            halign="left",
            valign="middle",
            text_size=(dp(340), None),
        )

    def _button(self, text, callback, primary=False):
        button = Button(
            text=text,
            size_hint_y=None,
            height=dp(42),
            font_size=dp(13),
            background_normal="",
            background_color=(
                self.app.palette["mint"]
                if primary
                else self.app.palette["surface"]
            ),
            color=(1, 1, 1, 1) if primary else self.app.palette["text"],
        )
        button.bind(on_release=lambda *_: callback())
        return button

    def open_form(self, record=None):
        if self.store is None:
            self.show_error(self.storage_error)
            return
        content = BoxLayout(
            orientation="vertical",
            padding=dp(16),
            spacing=dp(8),
            size_hint_y=None,
        )
        content.bind(minimum_height=content.setter("height"))
        fields = {}
        for key, label, hint in (
            ("first_day", "First day *", "YYYY-MM-DD"),
            ("last_day", "Last day (optional)", "YYYY-MM-DD"),
            ("symptoms", "Symptoms (optional)", "Optional"),
            ("notes", "Notes (optional)", "Private note"),
        ):
            content.add_widget(self._label(label, self.app.palette["muted"]))
            field = TextInput(
                hint_text=hint,
                text=(record or {}).get(key, ""),
                multiline=False,
                size_hint_y=None,
                height=dp(42),
                padding=(dp(10), dp(10)),
                foreground_color=self.app.palette["text"],
                background_color=self.app.palette["background"],
            )
            fields[key] = field
            content.add_widget(field)
        error = self._label("", self.app.palette["danger"])
        content.add_widget(error)
        buttons = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        save = self._button("Save privately", lambda: None, True)
        cancel = self._button("Cancel", lambda: popup.dismiss())
        buttons.add_widget(cancel)
        buttons.add_widget(save)
        content.add_widget(buttons)
        scroll = __import__("kivy.uix.scrollview", fromlist=["ScrollView"]).ScrollView(
            do_scroll_x=False
        )
        scroll.add_widget(content)
        popup = Popup(
            title="Edit period record" if record else "Log a period",
            content=scroll,
            size_hint=(0.92, 0.86),
        )

        def submit():
            values = {key: field.text.strip() for key, field in fields.items()}
            try:
                if record:
                    self.store.update_period(record["id"], **values)
                else:
                    self.store.add_period(**values)
            except (ValueError, SecureStorageUnavailable, OSError) as exception:
                error.text = str(exception)
                return
            popup.dismiss()
            self.refresh()

        save.bind(on_release=lambda *_: submit())
        popup.open()

    def confirm_delete(self, record):
        content = BoxLayout(
            orientation="vertical", padding=dp(14), spacing=dp(8)
        )
        content.add_widget(
            self._label(
                "Delete this private period record? This cannot be undone."
            )
        )
        buttons = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        popup = Popup(
            title="Delete private record?",
            content=content,
            size_hint=(0.88, None),
            height=dp(170),
        )
        buttons.add_widget(self._button("Cancel", popup.dismiss))

        def delete():
            self.store.delete_period(record["id"])
            popup.dismiss()
            self.refresh()

        buttons.add_widget(self._button("Delete", delete, True))
        content.add_widget(buttons)
        popup.open()

    def show_error(self, message):
        content = BoxLayout(orientation="vertical", padding=dp(14))
        content.add_widget(self._label(message, self.app.palette["danger"]))
        close = Button(
            text="Close",
            size_hint_y=None,
            height=dp(42),
            background_normal="",
            background_color=self.app.palette["mint"],
            color=(1, 1, 1, 1),
        )
        popup = Popup(title="Private tracker unavailable", content=content, size_hint=(0.9, None), height=dp(160))
        close.bind(on_release=popup.dismiss)
        content.add_widget(close)
        popup.open()
