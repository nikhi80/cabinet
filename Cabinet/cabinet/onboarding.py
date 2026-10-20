"""Five-step first-run setup for Cabinet."""

from __future__ import annotations

from pathlib import Path

from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from cabinet.preferences import (
    GENDER_OPTIONS,
    save_setup_preferences,
    validate_date_of_birth,
    validate_gender,
)


def _rgba(hex_color):
    value = hex_color.lstrip("#")
    return tuple(int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)) + (1,)


COMPLETION = {
    "background": _rgba("#F7F2E6"),
    "heading": _rgba("#214747"),
    "body": _rgba("#647875"),
    "label": _rgba("#A87516"),
    "progress": _rgba("#E9B949"),
    "border": _rgba("#D8D0BE"),
    "surface": _rgba("#FFFEFA"),
}


def _serif_font():
    candidates = (
        Path("C:/Windows/Fonts/georgia.ttf"),
        Path("/system/fonts/NotoSerif-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
    )
    return next((str(path) for path in candidates if path.is_file()), "Roboto")


class ProgressSegment(Widget):
    def __init__(self, color, **kwargs):
        super().__init__(**kwargs)
        self.color_value = color
        self.bind(size=self.draw, pos=self.draw)
        self.draw()

    def draw(self, *_):
        from kivy.graphics import Color, RoundedRectangle

        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.color_value)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(3)])


class SetupScreen(Screen):
    STEP_TITLES = (
        "About you",
        "Personalize",
        "Your health tools",
        "Preferences",
        "All set",
    )

    def __init__(self, app, **kwargs):
        super().__init__(name="setup", **kwargs)
        self.app = app
        self.step = 0
        self.display_name = ""
        self.date_of_birth = ""
        self.gender = "Prefer not to say"
        self.profile_error = ""
        self.features = {"medicines": True, "vaccines": True, "cycle": False}
        self.reminders = False
        self.household = ""
        self.return_to_settings = False
        self._render()

    def load_preferences(self, store):
        self.display_name = store.get_setting("display_name", "")
        self.date_of_birth = store.get_setting("date_of_birth", "")
        self.gender = store.get_setting("gender", "Prefer not to say")
        if self.gender not in GENDER_OPTIONS:
            self.gender = "Prefer not to say"
        self.profile_error = ""
        self.features = {
            "medicines": store.get_setting("feature_medicines", "true") == "true",
            "vaccines": store.get_setting("feature_vaccines", "true") == "true",
            "cycle": store.get_setting("feature_cycle", "false") == "true",
        }
        self.reminders = store.get_setting("reminders_enabled", "false") == "true"
        self.household = store.get_setting("household_name", "")
        self.step = 0
        self.return_to_settings = True
        self._render()

    def start_new(self, display_name=""):
        self.display_name = display_name
        self.date_of_birth = ""
        self.gender = "Prefer not to say"
        self.profile_error = ""
        self.features = {"medicines": True, "vaccines": True, "cycle": False}
        self.reminders = False
        self.household = ""
        self.step = 0
        self.return_to_settings = False
        self._render()

    def _render(self):
        palette = self.app.palette
        is_completion = self.step == 4
        self.clear_widgets()
        outer = BoxLayout(orientation="vertical", padding=(dp(22), dp(20)), spacing=dp(12))
        if is_completion:
            outer.canvas.before.clear()
            with outer.canvas.before:
                Color(*COMPLETION["background"])
                outer_background = RoundedRectangle(pos=outer.pos, size=outer.size, radius=[0])
            outer.bind(
                pos=lambda widget, _value: setattr(outer_background, "pos", widget.pos),
                size=lambda widget, _value: setattr(outer_background, "size", widget.size),
            )
        outer.add_widget(
            Label(
                text="CABINET · SETUP",
                size_hint_y=None,
                height=dp(22),
                font_size=dp(12 if is_completion else 10),
                bold=True,
                color=COMPLETION["label"] if is_completion else palette["gold"],
                halign="left",
            )
        )
        outer.add_widget(
            Label(
                text=f"Step {self.step + 1} of 5 · {self.STEP_TITLES[self.step]}",
                size_hint_y=None,
                height=dp(36 if is_completion else 32),
                font_size=dp(23 if is_completion else 21),
                bold=True,
                color=COMPLETION["heading"] if is_completion else palette["text"],
                halign="left",
            )
        )
        track = BoxLayout(size_hint_y=None, height=dp(5), spacing=dp(4))
        for index in range(5):
            track.add_widget(ProgressSegment(
                (COMPLETION["progress"] if is_completion else palette["gold"])
                if index <= self.step
                else (COMPLETION["border"] if is_completion else palette["line"])
            )
            )
        outer.add_widget(track)
        from kivy.uix.scrollview import ScrollView

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        if is_completion:
            anchor = AnchorLayout(anchor_x="center", anchor_y="center", size_hint_y=None)
            content = BoxLayout(
                orientation="vertical",
                size_hint=(None, None),
                spacing=dp(18),
                padding=(dp(24), dp(12)),
            )
            content.bind(minimum_height=content.setter("height"))
            anchor.add_widget(content)
            scroll.add_widget(anchor)

            def fit_completion(*_):
                content.width = min(max(0, anchor.width - dp(24)), dp(680))
                anchor.height = max(scroll.height, content.height)

            anchor.bind(width=fit_completion)
            content.bind(height=fit_completion)
            scroll.bind(height=fit_completion)
            fit_completion()
            self._completion_content(content)
        else:
            content = BoxLayout(
                orientation="vertical", size_hint_y=None, spacing=dp(12), padding=(0, dp(8))
            )
            content.bind(minimum_height=content.setter("height"))
            scroll.add_widget(content)
            self._step_content(content)
        outer.add_widget(scroll)
        buttons = BoxLayout(
            size_hint=(None, None) if is_completion else (1, None),
            height=dp(52 if is_completion else 48),
            spacing=dp(10 if is_completion else 8),
        )
        if is_completion:
            buttons.width = min(max(0, self.width - dp(44)), dp(680))
            footer = AnchorLayout(anchor_x="center", size_hint_y=None, height=dp(52))
            footer.add_widget(buttons)
            footer.bind(
                width=lambda _widget, value: setattr(
                    buttons, "width", min(max(0, value - dp(44)), dp(680))
                )
            )
        if self.return_to_settings:
            buttons.add_widget(self._button("Cancel", self.cancel, False, is_completion))
        if self.step > 0:
            buttons.add_widget(self._button("Back", self.previous, False, is_completion))
        if self.step < 4:
            buttons.add_widget(self._button("Continue", self.next_step, True))
        else:
            buttons.add_widget(self._button("Go to Cabinet", self.finish, True, True))
        if is_completion:
            outer.add_widget(footer)
        else:
            outer.add_widget(buttons)
        self.add_widget(outer)

    def _label(self, text, size=14, color=None, bold=False):
        label = Label(
            text=text,
            size_hint_y=None,
            size_hint_x=1,
            font_size=dp(size),
            bold=bold,
            color=color or self.app.palette["text"],
            halign="left",
            valign="middle",
            text_size=(None, None),
        )
        label.bind(width=self._fit_label, texture_size=self._fit_label)
        return label

    @staticmethod
    def _fit_label(label, _value):
        label.text_size = (max(0, label.width), None)
        label.height = max(label.texture_size[1], label.font_size + dp(8))

    def _completion_content(self, content):
        name = self.display_name.strip() or "your family"
        welcome = self._label(
            f"Welcome, {name}.",
            32,
            COMPLETION["heading"],
            True,
        )
        welcome.font_name = _serif_font()
        welcome.font_size = dp(min(34, max(28, self.width / 12)))
        welcome.halign = "center"
        description = self._label(
            "Your Cabinet is ready. Add medicine and vaccination records using information "
            "from official documents or your healthcare professional.",
            17,
            COMPLETION["body"],
        )
        description.line_height = 1.25
        description.halign = "center"
        disclaimer = self._label(
            "Cabinet organizes health records. It does not provide medical advice or determine "
            "vaccination schedules.",
            14,
            COMPLETION["body"],
        )
        disclaimer.line_height = 1.2
        disclaimer.halign = "center"
        content.add_widget(welcome)
        content.add_widget(description)
        content.add_widget(disclaimer)

    def _input(self, hint, text=""):
        field = TextInput(
            hint_text=hint,
            text=text,
            multiline=False,
            size_hint_y=None,
            height=dp(46),
            padding=(dp(12), dp(11)),
            font_size=dp(14),
            foreground_color=self.app.palette["text"],
            background_color=self.app.palette["surface"],
        )
        return field

    def _button(self, text, callback, primary=False, completion=False):
        if completion:
            button = Button(
                text=text,
                size_hint_x=1,
                height=dp(52),
                background_normal="",
                background_down="",
                background_color=(0, 0, 0, 0),
                color=(1, 1, 1, 1) if primary else COMPLETION["heading"],
                bold=True,
            )

            def paint_button(widget, *_):
                widget.canvas.before.clear()
                with widget.canvas.before:
                    fill = COMPLETION["heading"] if primary else COMPLETION["surface"]
                    if widget.state == "down":
                        fill = tuple(channel * 0.90 for channel in fill[:3]) + (fill[3],)
                    Color(*fill)
                    RoundedRectangle(pos=widget.pos, size=widget.size, radius=[dp(14)])
                    if not primary:
                        Color(*COMPLETION["border"])
                        Line(rounded_rectangle=(*widget.pos, *widget.size, dp(14)), width=1)

            button.bind(pos=paint_button, size=paint_button, state=paint_button)
        else:
            button = Button(
                text=text,
                size_hint_y=None,
                height=dp(46),
                background_normal="",
                background_color=(
                    self.app.palette["mint"] if primary else self.app.palette["surface"]
                ),
                color=(1, 1, 1, 1) if primary else self.app.palette["text"],
                bold=primary,
            )
        button.bind(on_release=lambda *_: callback())
        return button

    def _choice(self, content, text, selected, callback):
        content.add_widget(
            self._button(
                ("✓  " if selected else "   ") + text,
                callback,
                selected,
            )
        )

    def _step_content(self, content):
        if self.step == 0:
            content.add_widget(self._label("Let's make Cabinet feel like yours."))
            content.add_widget(self._label("DISPLAY NAME", 10, self.app.palette["muted"], True))
            self.name_input = self._input("Your name", self.display_name)
            content.add_widget(self.name_input)
            content.add_widget(
                self._label("DATE OF BIRTH", 10, self.app.palette["muted"], True)
            )
            self.dob_input = self._input("YYYY-MM-DD", self.date_of_birth)
            content.add_widget(self.dob_input)
            content.add_widget(
                self._label(
                    "Your birth date is used only to calculate age for the optional Menstruation tab. It stays in this account's local profile."
                )
            )
            if self.profile_error:
                content.add_widget(
                    self._label(self.profile_error, 12, self.app.palette["danger"])
                )
        elif self.step == 1:
            content.add_widget(self._label("Choose a gender option."))
            content.add_widget(
                self._label(
                    "The Menstruation tab appears for Female profiles aged 12 or older. The tracker itself is optional and can be enabled later in Settings. Changing gender or date of birth may change tab visibility, but never deletes records."
                )
            )
            for choice in GENDER_OPTIONS:
                self._choice(
                    content,
                    choice,
                    self.gender == choice,
                    lambda value=choice: self._set_gender(value),
                )
        elif self.step == 2:
            content.add_widget(self._label("Choose the tools you'd like to use."))
            options = (
                ("medicines", "Household medicine inventory"),
                ("vaccines", "Vaccine tracker"),
                ("cycle", "Menstruation tracker (optional)"),
            )
            for key, title in options:
                self._choice(
                    content,
                    title,
                    self.features[key],
                    lambda name=key: self._toggle_feature(name),
                )
            content.add_widget(
                self._label(
                    "This private tracker is opt-in. Profile details never enable it automatically, and hiding its tab never deletes its records."
                )
            )
            self._choice(
                content,
                "Reminders and notifications (preference only)",
                self.reminders,
                self._toggle_reminders,
            )
        elif self.step == 3:
            content.add_widget(self._label("Make a few finishing choices."))
            content.add_widget(self._label("THEME", 10, self.app.palette["muted"], True))
            for theme in ("light", "dark"):
                self._choice(
                    content,
                    theme.title(),
                    self.app.current_theme == theme,
                    lambda selected=theme: self.app.set_theme(selected),
                )
            content.add_widget(self._label("HOUSEHOLD NAME (OPTIONAL)", 10, self.app.palette["muted"], True))
            self.household_input = self._input("e.g. The Rivera family", self.household)
            content.add_widget(self.household_input)
            content.add_widget(
                self._label(
                    "You can update your feature and reminder preferences later in Settings."
                )
            )
        else:
            display_name = self.display_name or "your family"
            content.add_widget(self._label(f"Welcome, {display_name}.", 27, bold=True))
            content.add_widget(
                self._label(
                    "Your Cabinet is ready. Add records using details from official documents or your healthcare professional."
                )
            )
            content.add_widget(
                self._label(
                    "Cabinet organizes records; it does not provide medical advice or recommend vaccine timing."
                )
            )

    def _set_gender(self, value):
        self.gender = value
        self._render()

    def _toggle_feature(self, name):
        self.features[name] = not self.features[name]
        self._render()

    def _toggle_reminders(self):
        self.reminders = not self.reminders
        self._render()

    def next_step(self):
        if self.step == 0:
            display_name = self.name_input.text.strip()
            date_of_birth = self.dob_input.text.strip()
            try:
                if not display_name:
                    raise ValueError("Enter a name or preferred display name.")
                validate_date_of_birth(date_of_birth)
            except ValueError as error:
                self.profile_error = str(error)
                self._render()
                return
            self.display_name = display_name
            self.date_of_birth = date_of_birth
            self.profile_error = ""
        elif self.step == 3:
            self.household = self.household_input.text.strip()
        self.step = min(4, self.step + 1)
        self._render()

    def previous(self):
        if self.step == 1:
            self.display_name = self.name_input.text.strip() if hasattr(self, "name_input") else self.display_name
            self.date_of_birth = self.dob_input.text.strip() if hasattr(self, "dob_input") else self.date_of_birth
        self.step = max(0, self.step - 1)
        self._render()

    def finish(self):
        store = self.app.store
        settings = {
            "display_name": self.display_name,
            "date_of_birth": self.date_of_birth,
            "gender": self.gender,
            "feature_medicines": str(self.features["medicines"]).lower(),
            "feature_vaccines": str(self.features["vaccines"]).lower(),
            "feature_cycle": str(self.features["cycle"]).lower(),
            "reminders_enabled": str(self.reminders).lower(),
            "household_name": self.household,
            "setup_complete": "true",
        }
        try:
            validated_profile = {
                "display_name": settings["display_name"],
                "date_of_birth": validate_date_of_birth(settings["date_of_birth"]),
                "gender": validate_gender(settings["gender"]),
            }
        except ValueError as error:
            self.profile_error = str(error)
            self.step = 0
            self._render()
            return

        existing_profile = store.get_setting("setup_complete", "false") == "true"
        profile_changed = any(
            store.get_setting(key, "") != value
            for key, value in validated_profile.items()
        )
        if existing_profile and profile_changed:
            self._confirm_profile_update(settings, validated_profile)
            return
        self._save_setup(settings)

    def _confirm_profile_update(self, settings, validated_profile):
        old_gender = self.app.store.get_setting("gender", "")
        old_date_of_birth = self.app.store.get_setting("date_of_birth", "")
        eligibility_changed = (
            old_gender != validated_profile["gender"]
            or old_date_of_birth != validated_profile["date_of_birth"]
        )
        message = "Save these profile changes?"
        if eligibility_changed:
            tracker_enabled = self.app.store.get_setting("feature_cycle", "false") == "true"
            message += (
                "\n\nChanging gender or date of birth may show or hide the "
                "Menstruation tab. The tracker setting remains "
                f"{'enabled' if tracker_enabled else 'disabled'} and no records are deleted."
            )
            if settings["feature_cycle"] != str(tracker_enabled).lower():
                message += (
                    f"\n\nThis setup also changes the optional tracker to "
                    f"{'enabled' if settings['feature_cycle'] == 'true' else 'disabled'}."
                )
        content = BoxLayout(
            orientation="vertical", padding=dp(14), spacing=dp(10)
        )
        content.add_widget(
            Label(
                text=message,
                color=self.app.palette["text"],
                halign="left",
                valign="middle",
            )
        )
        buttons = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        popup = Popup(
            title="Confirm profile update",
            content=content,
            size_hint=(0.9, None),
            height=dp(250),
        )
        buttons.add_widget(self._button("Cancel", popup.dismiss))
        buttons.add_widget(
            self._button(
                "Save changes",
                lambda: self._save_setup(settings, popup),
                True,
            )
        )
        content.add_widget(buttons)
        popup.open()

    def _save_setup(self, settings, popup=None):
        save_setup_preferences(
            self.app.store,
            settings,
            confirm_profile_overwrite=popup is not None,
        )
        if hasattr(self.app, "configure_navigation"):
            self.app.configure_navigation()
        if popup is not None:
            popup.dismiss()
        if self.return_to_settings:
            self.return_to_settings = False
            self.app.navigate("settings")
        else:
            self.app.navigate("home")

    def cancel(self):
        self.return_to_settings = False
        self.app.navigate("settings")
