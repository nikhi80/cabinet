"""Kivy application shell, navigation, and theme lifecycle."""

from __future__ import annotations

from datetime import date, datetime, timezone
import logging
from math import cos, pi, sin
from pathlib import Path
from threading import Thread

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import FadeTransition, ScreenManager
from kivy.uix.widget import Widget
from kivy.utils import platform

from cabinet.database import CabinetStore
from cabinet.auth import AuthenticationError, AuthSession, FirebaseEmailAuth
from cabinet.auth_screens import (
    ForgotPasswordScreen,
    LoginScreen,
    SignupScreen,
    WelcomeScreen,
)
from cabinet.cycle import account_database_path, private_store_path
from cabinet.onboarding import SetupScreen
from cabinet.preferences import is_menstruation_eligible
from cabinet.screens import (
    CalendarScreen,
    HomeScreen,
    MedicinesScreen,
    SettingsScreen,
    VaccinesScreen,
)
from cabinet.prescription_screen import PrescriptionScreen
from cabinet.secure_storage import supports_private_storage
from cabinet.theme import DARK, LIGHT

logger = logging.getLogger(__name__)


class _NavigationTab(ButtonBehavior, BoxLayout):
    pass


class _NavigationIcon(Widget):
    def __init__(self, app, icon_name: str, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.icon_name = icon_name
        self.selected = False
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def _redraw(self, *_args) -> None:
        from kivy.graphics import (
            Color,
            Ellipse,
            Line,
            PopMatrix,
            PushMatrix,
            Rotate,
        )

        self.canvas.clear()
        size = min(self.width, self.height) * 0.82
        left = self.center_x - size / 2
        bottom = self.center_y - size / 2
        right = left + size
        top = bottom + size
        cx, cy = self.center

        with self.canvas:
            Color(
                *(
                    self.app.palette["mint"]
                    if self.selected
                    else self.app.palette["muted"]
                )
            )
            if self.icon_name == "home":
                Line(
                    points=[
                        left + size * 0.12,
                        bottom + size * 0.48,
                        cx,
                        top - size * 0.04,
                        right - size * 0.12,
                        bottom + size * 0.48,
                    ],
                    width=1.25,
                    joint="round",
                )
                Line(
                    rectangle=(
                        left + size * 0.25,
                        bottom + size * 0.10,
                        size * 0.50,
                        size * 0.40,
                    ),
                    width=1.25,
                )
                Line(
                    rectangle=(
                        left + size * 0.43,
                        bottom + size * 0.10,
                        size * 0.16,
                        size * 0.24,
                    ),
                    width=1.0,
                )
            elif self.icon_name == "medicine":
                PushMatrix()
                Rotate(angle=45, origin=(cx, cy))
                Line(
                    rounded_rectangle=(
                        cx - size * 0.32,
                        cy - size * 0.14,
                        size * 0.64,
                        size * 0.28,
                        size * 0.14,
                    ),
                    width=1.25,
                )
                Line(
                    points=[cx, cy - size * 0.13, cx, cy + size * 0.13],
                    width=1.0,
                )
                PopMatrix()
            elif self.icon_name == "vaccine":
                Line(
                    points=[
                        left + size * 0.18,
                        bottom + size * 0.20,
                        left + size * 0.72,
                        bottom + size * 0.74,
                    ],
                    width=1.35,
                    joint="round",
                )
                Line(
                    points=[
                        left + size * 0.12,
                        bottom + size * 0.14,
                        left + size * 0.30,
                        bottom + size * 0.32,
                    ],
                    width=1.25,
                )
                Line(
                    points=[
                        left + size * 0.62,
                        bottom + size * 0.84,
                        left + size * 0.83,
                        bottom + size * 0.63,
                    ],
                    width=1.25,
                )
                Line(
                    points=[
                        left + size * 0.76,
                        bottom + size * 0.78,
                        right - size * 0.08,
                        top - size * 0.06,
                    ],
                    width=1.1,
                )
                Line(
                    points=[
                        left + size * 0.39,
                        bottom + size * 0.43,
                        left + size * 0.53,
                        bottom + size * 0.29,
                    ],
                    width=1.0,
                )
            elif self.icon_name == "calendar":
                Line(
                    rounded_rectangle=(
                        left + size * 0.13,
                        bottom + size * 0.12,
                        size * 0.74,
                        size * 0.73,
                        size * 0.08,
                    ),
                    width=1.25,
                )
                Line(
                    points=[
                        left + size * 0.14,
                        bottom + size * 0.59,
                        right - size * 0.14,
                        bottom + size * 0.59,
                    ],
                    width=1.1,
                )
                for fraction in (0.32, 0.68):
                    Line(
                        points=[
                            left + size * fraction,
                            bottom + size * 0.72,
                            left + size * fraction,
                            bottom + size * 0.87,
                        ],
                        width=1.5,
                    )
                for x_fraction in (0.34, 0.52, 0.70):
                    Ellipse(
                        pos=(
                            left + size * x_fraction - dp(0.6),
                            bottom + size * 0.23 - dp(0.6),
                        ),
                        size=(dp(1.2), dp(1.2)),
                    )
            elif self.icon_name == "settings":
                radius = size * 0.22
                Line(circle=(cx, cy, radius), width=1.25, segments=32)
                Line(circle=(cx, cy, size * 0.08), width=1.1, segments=24)
                for index in range(8):
                    angle = 2 * pi * index / 8
                    Line(
                        points=[
                            cx + cos(angle) * size * 0.27,
                            cy + sin(angle) * size * 0.27,
                            cx + cos(angle) * size * 0.39,
                            cy + sin(angle) * size * 0.39,
                        ],
                        width=1.6,
                    )


class CabinetApp(App):
    """Main Cabinet app."""

    title = "Cabinet"

    def build(self) -> BoxLayout:
        self.local_database_path = Path(self.user_data_dir) / "cabinet.sqlite3"
        self.profile_data_dir = Path(self.user_data_dir) / "local-profile"
        self.store = CabinetStore(self.local_database_path)
        self.current_uid = "local"
        self.current_session: AuthSession | None = None
        self._cycle_store = None
        self._cycle_store_uid = None
        self.auth_client = FirebaseEmailAuth.from_workspace(Path(self.directory))
        self.current_theme = self.store.get_setting("theme", "light")
        self.palette = DARK if self.current_theme == "dark" else LIGHT
        if platform not in {"android", "ios"}:
            Window.size = (430, 860)
            Window.minimum_width = 360
            Window.clearcolor = self.palette["background"]

        self.root_layout = BoxLayout(orientation="vertical")
        self.root_layout.canvas.before.clear()
        self.root_layout.bind(size=self._paint_root, pos=self._paint_root)

        self.header = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(78),
            padding=(dp(20), dp(10), dp(20), dp(8)),
            spacing=dp(12),
        )
        self.header.bind(size=self._paint_header, pos=self._paint_header)
        brand = BoxLayout(orientation="vertical", spacing=dp(0))
        self.title_label = self._label("Cabinet", 22, True, self.palette["navy"])
        self.tagline_label = self._label(
            "Your family's health, organized.", 11, False, self.palette["muted"]
        )
        brand.add_widget(self.title_label)
        brand.add_widget(self.tagline_label)
        self.header.add_widget(self._logo())
        self.header.add_widget(brand)
        self.settings_shortcut = Button(
            text="Settings",
            size_hint=(None, None),
            size=(dp(64), dp(38)),
            font_size=dp(11),
            background_normal="",
            background_color=self.palette["mint_soft"],
            color=self.palette["text"],
        )
        self.settings_shortcut.bind(on_release=lambda *_: self.navigate("settings"))
        self.header.add_widget(self.settings_shortcut)
        self.root_layout.add_widget(self.header)

        self.manager = ScreenManager(transition=FadeTransition(duration=0.12))
        self.screens = {
            "home": HomeScreen(self, name="home"),
            "medicines": MedicinesScreen(self),
            "vaccines": VaccinesScreen(self),
            "calendar": CalendarScreen(self, name="calendar"),
            "settings": SettingsScreen(self, name="settings"),
            "setup": SetupScreen(self),
            "welcome": WelcomeScreen(self, name="welcome"),
            "login": LoginScreen(self, name="login"),
            "signup": SignupScreen(self, name="signup"),
            "forgot": ForgotPasswordScreen(self, name="forgot"),
            "prescription": PrescriptionScreen(self),
        }
        for name, screen in self.screens.items():
            self.manager.add_widget(screen)
        self.root_layout.add_widget(self.manager)

        self.nav = BoxLayout(
            size_hint_y=None,
            height=dp(66),
            padding=(dp(6), dp(5)),
            spacing=dp(2),
        )
        self.nav.bind(size=self._paint_nav, pos=self._paint_nav)
        self.nav_buttons: dict[str, _NavigationTab] = {}
        self.manager.bind(current=self._sync_navigation_selection)
        self.root_layout.add_widget(self.nav)
        self.enter_guest_mode()
        return self.root_layout

    @staticmethod
    def _label(text: str, size: int, bold: bool, color: tuple) -> Label:
        return Label(
            text=text,
            font_size=dp(size),
            bold=bold,
            color=color,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(size + 8),
            text_size=(None, None),
        )

    def _logo(self) -> Widget:
        logo = Widget(size_hint=(None, None), size=(dp(48), dp(48)))
        logo.bind(pos=self._paint_logo, size=self._paint_logo)
        self.logo_widget = logo
        self._paint_logo(logo)
        return logo

    def _paint_logo(self, logo: Widget, _value=None) -> None:
        from kivy.graphics import Color, Ellipse, Line, RoundedRectangle

        x, y = logo.pos
        width, height = logo.size
        canvas = logo.canvas.before
        canvas.clear()
        with canvas:
            Color(*self.palette["mint"])
            RoundedRectangle(pos=logo.pos, size=logo.size, radius=[dp(15)])
            Color(1, 1, 1, 0.96)
            cabinet = (x + width * 0.22, y + height * 0.19, width * 0.56, height * 0.62)
            Line(rectangle=cabinet, width=1.25)
            Line(
                points=[
                    x + width * 0.50,
                    y + height * 0.19,
                    x + width * 0.50,
                    y + height * 0.81,
                ],
                width=1.1,
            )
            Line(
                points=[
                    x + width * 0.33,
                    y + height * 0.56,
                    x + width * 0.45,
                    y + height * 0.56,
                ],
                width=1.8,
            )
            Line(
                points=[
                    x + width * 0.39,
                    y + height * 0.50,
                    x + width * 0.39,
                    y + height * 0.62,
                ],
                width=1.8,
            )
            Ellipse(
                pos=(x + width * 0.56, y + height * 0.47),
                size=(dp(2.2), dp(2.2)),
            )

    def _paint_root(self, _widget, _value) -> None:
        from kivy.graphics import Color, Rectangle

        canvas = self.root_layout.canvas.before
        canvas.clear()
        with canvas:
            Color(*self.palette["background"])
            Rectangle(pos=self.root_layout.pos, size=self.root_layout.size)

    def _paint_header(self, _widget, _value) -> None:
        from kivy.graphics import Color, Rectangle

        canvas = self.header.canvas.before
        canvas.clear()
        with canvas:
            Color(*self.palette["surface"])
            Rectangle(pos=self.header.pos, size=self.header.size)

    def _paint_nav(self, _widget, _value) -> None:
        from kivy.graphics import Color, Rectangle

        canvas = self.nav.canvas.before
        canvas.clear()
        with canvas:
            Color(*self.palette["surface"])
            Rectangle(pos=self.nav.pos, size=self.nav.size)

    def navigate(self, name: str) -> None:
        main_screens = {"home", "medicines", "vaccines", "calendar", "settings", "cycle"}
        if name not in main_screens or name not in self.screens:
            raise ValueError(f"Unknown Cabinet screen: {name}")
        self.configure_navigation()
        if name == "cycle" and name not in self.nav_buttons:
            raise ValueError("The Menstruation tab is not enabled for this profile.")
        self.header.height = dp(78)
        self.header.opacity = 1
        self.nav.height = dp(66)
        self.nav.opacity = 1
        self.manager.current = name
        screen = self.screens[name]
        if hasattr(screen, "refresh"):
            screen.refresh()

    def _sync_navigation_selection(self, _manager, name: str) -> None:
        for button_name, button in self.nav_buttons.items():
            selected = button_name == name
            button._nav_selected = selected
            button._nav_label.color = (
                self.palette["text"] if selected else self.palette["muted"]
            )
            button._nav_label.bold = selected
            button._nav_icon.selected = selected
            button._nav_icon._redraw()
            button._paint_background()

    def show_flow(self, name: str) -> None:
        if name not in {"setup", "welcome", "login", "signup", "forgot"}:
            raise ValueError(f"Unknown Cabinet flow screen: {name}")
        self.header.height = 0
        self.header.opacity = 0
        self.nav.height = 0
        self.nav.opacity = 0
        self.manager.current = name

    def configure_navigation(self) -> None:
        if not hasattr(self, "nav"):
            return
        eligible_profile = supports_private_storage(
            platform
        ) and is_menstruation_eligible(
            self.store.get_setting("gender", ""),
            self.store.get_setting("date_of_birth", ""),
        )
        cycle_screen = self.screens.get("cycle")
        if eligible_profile and cycle_screen is not None and cycle_screen.owner_uid != self.current_uid:
            self.manager.remove_widget(self.screens["cycle"])
            self.screens.pop("cycle")
            cycle_screen = None
        if eligible_profile and cycle_screen is None:
            from cabinet.cycle_screen import CycleScreen

            self.screens["cycle"] = CycleScreen(self)
            self.manager.add_widget(self.screens["cycle"])
        elif not eligible_profile and "cycle" in self.screens:
            cycle_screen = self.screens.pop("cycle")
            if self.manager.current == "cycle":
                self.manager.current = "home"
            self.manager.remove_widget(cycle_screen)

        for button in self.nav_buttons.values():
            self.nav.remove_widget(button)
        self.nav_buttons.clear()
        entries = [
            ("home", "Home"),
        ]
        if self.store.get_setting("feature_medicines", "true") == "true":
            entries.append(("medicines", "Medicine"))
        if self.store.get_setting("feature_vaccines", "true") == "true":
            entries.append(("vaccines", "Vaccines"))
        entries.append(("calendar", "Calendar"))
        if eligible_profile:
            entries.append(("cycle", "Menstruation"))
        entries.append(("settings", "Settings"))
        icon_names = {
            "home": "home",
            "medicines": "medicine",
            "vaccines": "vaccine",
            "calendar": "calendar",
            "settings": "settings",
            "cycle": "calendar",
        }
        for name, label in entries:
            selected = self.manager.current == name
            button = _NavigationTab(
                orientation="vertical",
                padding=(dp(1), dp(2)),
                spacing=dp(1),
            )
            button._nav_selected = selected
            button.size_hint = (1, 1)
            from kivy.graphics import Color, RoundedRectangle
            from kivy.uix.anchorlayout import AnchorLayout

            with button.canvas.before:
                button._nav_fill = Color(0, 0, 0, 0)
                button._nav_shape = RoundedRectangle(
                    pos=button.pos, size=button.size, radius=[dp(13)]
                )

            def paint_background(widget, _value=None):
                widget._nav_shape.pos = widget.pos
                widget._nav_shape.size = widget.size
                if widget.state == "down":
                    widget._nav_fill.rgba = self.palette["nav_pressed"]
                elif widget._nav_selected:
                    widget._nav_fill.rgba = self.palette["nav_active"]
                else:
                    widget._nav_fill.rgba = (0, 0, 0, 0)

            button._paint_background = lambda widget=button: paint_background(widget)
            button.bind(pos=paint_background, size=paint_background, state=paint_background)

            icon_slot = AnchorLayout(
                anchor_x="center",
                anchor_y="center",
            )
            icon = _NavigationIcon(
                self,
                icon_names[name],
                size_hint=(None, None),
                size=(dp(20), dp(20)),
            )
            icon_slot.add_widget(icon)
            caption = Label(
                text="Menstru\nation" if label == "Menstruation" else label,
                size_hint=(1, None),
                height=dp(28) if label == "Menstruation" else dp(18),
                font_size=dp(10) if label == "Menstruation" else dp(11),
                color=self.palette["text"]
                if selected
                else self.palette["muted"],
                bold=selected,
                halign="center",
                valign="center",
                shorten=True,
                shorten_from="right",
            )
            caption.bind(size=lambda widget, size: setattr(widget, "text_size", size))
            button.add_widget(icon_slot)
            button.add_widget(caption)
            button._nav_icon = icon
            button._nav_label = caption
            icon.selected = selected
            icon._redraw()
            button._paint_background()
            button.bind(on_release=lambda _button, target=name: self.navigate(target))
            self.nav_buttons[name] = button
            self.nav.add_widget(button)
        self._sync_navigation_selection(self.manager, self.manager.current)

    def enter_guest_mode(self, start_setup: bool = False) -> None:
        self.current_uid = "local"
        self.current_session = None
        self.profile_data_dir = Path(self.user_data_dir) / "local-profile"
        self._cycle_store = None
        self._cycle_store_uid = None
        self.store = CabinetStore(self.local_database_path)
        self._bind_store()
        self._restore_profile_theme()
        self.configure_navigation()
        if self.store.get_setting("setup_complete", "false") == "true":
            self.navigate("home")
        elif self.store.list_medicines() or self.store.list_vaccines():
            self.store.set_setting("setup_complete", "true")
            self.navigate("home")
        else:
            self.show_flow("setup" if start_setup else "welcome")

    def on_authenticated(
        self, session: AuthSession, display_name: str = ""
    ) -> None:
        self.current_uid = session.uid
        self.current_session = session
        self._cycle_store = None
        self._cycle_store_uid = None
        account_path = account_database_path(self.user_data_dir, session.uid)
        self.profile_data_dir = account_path.parent
        self.store = CabinetStore(account_path)
        self._bind_store()
        if session.is_new_user:
            self.store.set_setting(
                "policy_accepted_at",
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            self.store.set_setting("policy_version", "2026-10-13")
        self._restore_profile_theme()
        self.configure_navigation()
        if self.store.get_setting("setup_complete", "false") == "true":
            self.navigate("home")
        else:
            self.screens["setup"].start_new(
                display_name or self.store.get_setting("display_name", "")
            )
            self.show_flow("setup")

    def _bind_store(self) -> None:
        for screen in self.screens.values():
            if hasattr(screen, "store"):
                screen.store = self.store
            if hasattr(screen, "app"):
                screen.app = self

    def _restore_profile_theme(self) -> None:
        self.current_theme = self.store.get_setting("theme", "light")
        self.palette = DARK if self.current_theme == "dark" else LIGHT
        Window.clearcolor = self.palette["background"]
        if hasattr(self, "header"):
            self.title_label.color = self.palette["navy"]
            self.tagline_label.color = self.palette["muted"]
            self.settings_shortcut.background_color = self.palette["mint_soft"]
            self.settings_shortcut.color = self.palette["text"]
            self._paint_logo(self.logo_widget)
            self._paint_header(self.header, None)
            self._paint_nav(self.nav, None)
            for name, button in self.nav_buttons.items():
                button._nav_label.color = (
                    self.palette["mint"]
                    if button._nav_selected
                    else self.palette["muted"]
                )
                button._nav_icon._redraw()
                button._paint_background()

    def authenticate(self, button, operation, on_success) -> None:
        button.disabled = True
        original_text = button.text
        button.text = "Connecting securely…"

        def worker():
            try:
                result = operation()
            except (AuthenticationError, ValueError) as error:
                Clock.schedule_once(
                    lambda _dt, message=str(error): self._auth_finished(
                        button, original_text, message
                    ),
                    0,
                )
            except Exception:
                logger.exception("Unexpected authentication failure")
                Clock.schedule_once(
                    lambda _dt: self._auth_finished(
                        button,
                        original_text,
                        "Cabinet couldn't complete sign-in. Please try again.",
                    ),
                    0,
                )
            else:
                Clock.schedule_once(
                    lambda _dt: self._auth_success(
                        button, original_text, result, on_success
                    ),
                    0,
                )

        Thread(target=worker, name="cabinet-auth", daemon=True).start()

    def _auth_finished(self, button, original_text, error="") -> None:
        button.disabled = False
        button.text = original_text
        screen = self.screens.get(self.manager.current)
        if hasattr(screen, "error"):
            screen.error.text = error

    def _auth_success(self, button, original_text, result, callback) -> None:
        button.disabled = False
        button.text = original_text
        for name in ("login", "signup"):
            screen = self.screens.get(name)
            if hasattr(screen, "clear_secrets"):
                screen.clear_secrets()
        callback(result)

    def logout(self) -> None:
        self.current_session = None
        self._cycle_store = None
        self._cycle_store_uid = None
        self.enter_guest_mode()

    def get_cycle_store(self):
        from cabinet.cycle import MenstrualStore, private_store_path
        from cabinet.secure_storage import PrivateDataCipher

        uid = self.current_uid or "local"
        if self._cycle_store is not None and self._cycle_store_uid == uid:
            return self._cycle_store
        cipher = PrivateDataCipher(uid, platform)
        self._cycle_store = MenstrualStore(
            private_store_path(self.user_data_dir, uid), cipher
        )
        self._cycle_store_uid = uid
        return self._cycle_store

    def edit_setup_preferences(self) -> None:
        setup = self.screens["setup"]
        setup.load_preferences(self.store)
        self.show_flow("setup")

    def delete_account_data(self) -> None:
        if self.current_session is None:
            raise AuthenticationError("Log in before deleting an account.")
        import shutil

        session = self.current_session
        account_root = (Path(self.user_data_dir) / "accounts").resolve()
        private_root = (Path(self.user_data_dir) / "private-health").resolve()
        account_directory = (account_root / session.uid).resolve()
        private_directory = (private_root / session.uid).resolve()
        if account_directory.parent != account_root or private_directory.parent != private_root:
            raise ValueError("Account storage path is invalid.")

        def remove_after_provider_delete():
            self.auth_client.delete_account(session.id_token)
            if private_directory.exists():
                self.get_cycle_store().erase_all()
            if account_directory.exists():
                shutil.rmtree(account_directory)
            if private_directory.exists():
                shutil.rmtree(private_directory)

        return remove_after_provider_delete()

    def reset_local_data(self) -> None:
        """Erase only the active Cabinet profile, retaining any Firebase account."""
        import shutil

        data_root = Path(self.user_data_dir).resolve()
        session = self.current_session
        uid = session.uid if session is not None else "local"
        if session is not None:
            profile_directory = account_database_path(
                data_root, uid
            ).parent.resolve()
            accounts_root = (data_root / "accounts").resolve()
            if profile_directory.parent != accounts_root:
                raise ValueError("Account storage path is invalid.")
            database_path = (profile_directory / "cabinet.sqlite3").resolve()
            if database_path.parent != profile_directory:
                raise ValueError("Account database path is invalid.")
            if Path(self.store.database_path).resolve() != database_path:
                raise ValueError("Active account database does not match its profile.")
        else:
            profile_directory = (data_root / "local-profile").resolve()
            database_path = (data_root / "cabinet.sqlite3").resolve()
            if (
                profile_directory.parent != data_root
                or database_path.parent != data_root
                or Path(self.store.database_path).resolve() != database_path
            ):
                raise ValueError("Local profile storage path is invalid.")

        private_directory = (
            data_root / "private-health" / uid
        ).resolve()
        private_root = (data_root / "private-health").resolve()
        private_database = (
            private_directory / "menstrual.sqlite3"
        ).resolve()
        if (
            private_directory.parent != private_root
            or private_database.parent != private_directory
        ):
            raise ValueError("Private tracker storage path is invalid.")

        cycle_store = (
            self._cycle_store
            if self._cycle_store_uid == uid
            else None
        )
        if cycle_store is None and private_database.exists():
            cycle_store = self.get_cycle_store()
        if cycle_store is not None:
            cycle_store.erase_all()
        if private_directory.exists():
            shutil.rmtree(private_directory)

        if session is not None:
            if profile_directory.exists():
                shutil.rmtree(profile_directory)
        else:
            for suffix in ("", "-wal", "-shm"):
                path = Path(str(database_path) + suffix)
                if path.exists() or path.is_symlink():
                    path.unlink()
            if profile_directory.exists():
                shutil.rmtree(profile_directory)

        if session is None:
            capture_path = data_root / "prescriptions" / "capture.jpg"
            if capture_path.exists() or capture_path.is_symlink():
                capture_path.unlink()

        self._cycle_store = None
        self._cycle_store_uid = None
        self.store = CabinetStore(database_path)
        self._bind_store()
        self._restore_profile_theme()
        self.configure_navigation()
        self.screens["setup"].start_new()
        self.show_flow("setup")

    def set_theme(self, theme: str) -> None:
        if theme not in {"light", "dark"}:
            raise ValueError("Theme must be light or dark.")
        self.current_theme = theme
        self.store.set_setting("theme", theme)
        self.palette = DARK if theme == "dark" else LIGHT
        Window.clearcolor = self.palette["background"]
        self.title_label.color = self.palette["navy"]
        self.tagline_label.color = self.palette["muted"]
        self._paint_logo(self.logo_widget)
        self._paint_header(self.header, None)
        self._paint_nav(self.nav, None)
        self.configure_navigation()
        for screen in self.screens.values():
            if hasattr(screen, "refresh"):
                screen.refresh()
        current = self.manager.current
        if current in {"setup", "welcome", "login", "signup", "forgot"}:
            self.show_flow(current)
        elif current in {"home", "medicines", "vaccines", "calendar", "settings", "cycle"}:
            self.navigate(current)

    def open_add_medicine(self) -> None:
        self.screens["medicines"].open_medicine_form()
        self.navigate("medicines")

    def open_add_appointment(self) -> None:
        self.screens["calendar"].open_appointment_form()
        self.navigate("calendar")

    def open_prescription_scanner(self) -> None:
        screen = self.screens["prescription"]
        screen.refresh()
        self.manager.current = "prescription"

    def formatted_today(self) -> str:
        return date.today().strftime("%A, %B %d")

    def on_resume(self) -> None:
        if self.manager.current in {"setup", "welcome", "login", "signup", "forgot"}:
            self.show_flow(self.manager.current)
        else:
            self.configure_navigation()
            if self.manager.current == "cycle" and "cycle" not in self.nav_buttons:
                self.manager.current = "home"
            self.navigate(self.manager.current)
