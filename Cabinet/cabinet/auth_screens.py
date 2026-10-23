"""Welcome and Firebase email-account screens."""

from __future__ import annotations

from pathlib import Path

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from cabinet.auth import validate_email, validate_password


class FlowScreen(Screen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.palette = app.palette
        self.layout = BoxLayout(
            orientation="vertical", padding=(dp(24), dp(20)), spacing=dp(14)
        )
        self.add_widget(self.layout)
        self.build_content()

    def build_content(self) -> None:
        raise NotImplementedError

    def label(self, text, size=14, bold=False, color=None, height=None):
        palette = self.app.palette
        label = Label(
            text=text,
            font_size=dp(size),
            bold=bold,
            color=color or palette["text"],
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(height or size + 16),
            text_size=(self.width - dp(48), None),
        )
        label.bind(
            width=lambda widget, width: setattr(
                widget, "text_size", (max(0, width - dp(40)), None)
            )
        )
        label.bind(
            texture_size=lambda widget, size: setattr(
                widget, "height", max(dp(height or 0), size[1] + dp(10))
            )
        )
        return label

    def button(self, text, callback, primary=False):
        palette = self.app.palette
        button = Button(
            text=text,
            size_hint_y=None,
            height=dp(50),
            font_size=dp(14),
            bold=primary,
            background_normal="",
            background_down="",
            background_color=palette["mint"] if primary else palette["surface"],
            color=(1, 1, 1, 1) if primary else palette["text"],
        )
        button.bind(on_release=lambda *_: callback())
        return button

    def create_content(self):
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        content = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=dp(12)
        )
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        self.layout.add_widget(scroll)
        return content

    def add_heading(self, content, title, subtitle):
        content.add_widget(self.label(title, 29, True, height=42))
        content.add_widget(self.label(subtitle, 13, False, self.app.palette["muted"]))

    def text_field(self, content, label_text, hint, password=False):
        content.add_widget(
            self.label(label_text.upper(), 10, True, self.app.palette["muted"], 22)
        )
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        field = TextInput(
            hint_text=hint,
            password=password,
            multiline=False,
            size_hint_y=None,
            height=dp(47),
            padding=(dp(12), dp(12)),
            font_size=dp(14),
            foreground_color=self.app.palette["text"],
            background_color=self.app.palette["surface"],
            cursor_color=self.app.palette["gold"],
        )
        row.add_widget(field)
        if password:
            toggle = self.button("Show", lambda: self.toggle_password(field, toggle))
            toggle.size_hint_x = None
            toggle.width = dp(62)
            row.add_widget(toggle)
        content.add_widget(row)
        return field

    @staticmethod
    def toggle_password(field, button):
        field.password = not field.password
        button.text = "Show" if field.password else "Hide"

    def show_policy(self):
        documents = []
        for filename in ("PRIVACY.md", "TERMS.md"):
            path = Path(self.app.directory) / filename
            try:
                documents.append(path.read_text(encoding="utf-8"))
            except OSError:
                documents.append(
                    f"{filename} is unavailable in this installation. "
                    "Please reinstall the application package."
                )
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        text = Label(
            text="\n\n".join(documents),
            size_hint_y=None,
            halign="left",
            valign="top",
            font_size=dp(12),
            color=self.app.palette["text"],
            text_size=(dp(320), None),
        )
        text.bind(
            width=lambda widget, width: setattr(
                widget, "text_size", (max(dp(160), width - dp(30)), None)
            )
        )
        text.bind(texture_size=lambda widget, size: setattr(widget, "height", size[1] + dp(20)))
        scroll.add_widget(text)
        Popup(
            title="Privacy notice and terms",
            content=scroll,
            size_hint=(0.92, 0.86),
        ).open()

    def error_label(self, content):
        label = self.label("", 12, False, self.app.palette["danger"])
        content.add_widget(label)
        return label

    def navigate(self, target):
        self.app.show_flow(target)


class WelcomeScreen(FlowScreen):
    def build_content(self):
        content = self.create_content()
        content.add_widget(Label(size_hint_y=None, height=dp(26)))
        logo = self.label("✳", 38, True, self.app.palette["gold"], 54)
        logo.halign = "center"
        content.add_widget(logo)
        title = self.label("Cabinet", 34, True, self.app.palette["text"], 50)
        title.halign = "center"
        content.add_widget(title)
        tagline = self.label(
            "Your family's health, organized.", 14, False, self.app.palette["muted"], 34
        )
        tagline.halign = "center"
        content.add_widget(tagline)
        content.add_widget(Label(size_hint_y=None, height=dp(35)))
        content.add_widget(self.label("CARE, THOUGHTFULLY KEPT", 10, True, self.app.palette["gold"], 20))
        content.add_widget(
            self.label(
                "A quieter place for your family's health records.",
                25,
                True,
                self.app.palette["text"],
                78,
            )
        )
        content.add_widget(
            self.label(
                "Keep medicines, appointments and personal records together, at your pace.",
                14,
                False,
                self.app.palette["muted"],
                54,
            )
        )
        content.add_widget(self.button("Create an account with email", lambda: self.navigate("signup"), True))
        content.add_widget(self.button("Log in", lambda: self.navigate("login")))
        content.add_widget(
            self.button(
                "Continue on this device",
                lambda: self.app.enter_guest_mode(start_setup=True),
            )
        )
        content.add_widget(
            self.label(
                "Google sign-in isn't enabled in this build. It requires a configured native Android/iOS OAuth integration; no fake sign-in action is provided.",
                11,
                False,
                self.app.palette["muted"],
                58,
            )
        )


class LoginScreen(FlowScreen):
    def build_content(self):
        content = self.create_content()
        self.add_heading(content, "Welcome back", "Log in to your Cabinet account.")
        self.email = self.text_field(content, "Email address", "you@example.com")
        self.password = self.text_field(content, "Password", "Your password", True)
        self.error = self.error_label(content)
        content.add_widget(
            self.button("Forgot password?", lambda: self.navigate("forgot"))
        )
        self.submit_button = self.button("Log in", self.submit, True)
        content.add_widget(self.submit_button)
        content.add_widget(
            self.button("Create an account", lambda: self.navigate("signup"))
        )
        content.add_widget(self.button("Back", lambda: self.navigate("welcome")))

    def submit(self):
        try:
            email = validate_email(self.email.text)
            if not self.password.text:
                raise ValueError("Enter your password.")
        except ValueError as error:
            self.error.text = str(error)
            return
        self.error.text = ""
        self.app.authenticate(
            self.submit_button,
            lambda: self.app.auth_client.sign_in(email, self.password.text),
            lambda session: self.app.on_authenticated(session),
        )

    def clear_secrets(self):
        self.password.text = ""


class SignupScreen(FlowScreen):
    def build_content(self):
        content = self.create_content()
        self.add_heading(content, "Create your Cabinet", "A few details to get started.")
        self.display_name = self.text_field(content, "Display name", "Your name")
        self.email = self.text_field(content, "Email address", "you@example.com")
        self.password = self.text_field(content, "Password", "At least 8 characters", True)
        self.confirm = self.text_field(content, "Confirm password", "Enter it again", True)
        self.accepted = False
        content.add_widget(
            self.button("Read Privacy Notice & Terms", self.show_policy)
        )
        self.consent_button = self.button(
            "I agree to the Privacy Policy and Terms (not accepted)",
            self.toggle_consent,
        )
        content.add_widget(self.consent_button)
        content.add_widget(
            self.label(
                "Cabinet uses Firebase Authentication for your account. Health records remain local to this device and account profile in this release.",
                11,
                False,
                self.app.palette["muted"],
                48,
            )
        )
        self.error = self.error_label(content)
        self.submit_button = self.button("Create account", self.submit, True)
        content.add_widget(self.submit_button)
        content.add_widget(self.button("Already have an account? Log in", lambda: self.navigate("login")))
        content.add_widget(self.button("Back", lambda: self.navigate("welcome")))

    def toggle_consent(self):
        self.accepted = not self.accepted
        self.consent_button.text = (
            "Agreed to the Privacy Policy and Terms (tap to undo)"
            if self.accepted
            else "I agree to the Privacy Policy and Terms (not accepted)"
        )
        self.consent_button.background_color = (
            self.app.palette["mint"]
            if self.accepted
            else self.app.palette["surface"]
        )
        self.consent_button.color = (
            (1, 1, 1, 1) if self.accepted else self.app.palette["text"]
        )

    def submit(self):
        try:
            display_name = self.display_name.text.strip()
            if not display_name:
                raise ValueError("Enter a display name.")
            email = validate_email(self.email.text)
            validate_password(self.password.text)
            if self.password.text != self.confirm.text:
                raise ValueError("The passwords don't match.")
            if not self.accepted:
                raise ValueError("Please accept the Privacy Policy and Terms to continue.")
        except ValueError as error:
            self.error.text = str(error)
            return
        self.error.text = ""
        self.app.authenticate(
            self.submit_button,
            lambda: self.app.auth_client.sign_up(email, self.password.text),
            lambda session: self.app.on_authenticated(session, display_name),
        )

    def clear_secrets(self):
        self.password.text = ""
        self.confirm.text = ""


class ForgotPasswordScreen(FlowScreen):
    def build_content(self):
        content = self.create_content()
        self.add_heading(
            content,
            "Reset your password",
            "Firebase will email a password-reset link if the account can be found.",
        )
        self.email = self.text_field(content, "Email address", "you@example.com")
        self.error = self.error_label(content)
        self.submit_button = self.button("Send reset email", self.submit, True)
        content.add_widget(self.submit_button)
        content.add_widget(self.button("Back to login", lambda: self.navigate("login")))

    def submit(self):
        try:
            email = validate_email(self.email.text)
        except ValueError as error:
            self.error.text = str(error)
            return
        self.error.text = ""

        def done(_result):
            self.error.color = self.app.palette["mint"]
            self.error.text = "If the account exists, a reset email is on its way."

        self.app.authenticate(
            self.submit_button,
            lambda: self.app.auth_client.send_password_reset(email),
            done,
        )
