"""Desktop and Android entry point for Cabinet."""

import traceback


def _show_startup_error(details: str) -> None:
    """Show a startup error on screen so it is not a silent crash."""
    from kivy.app import App
    from kivy.uix.label import Label
    from kivy.uix.scrollview import ScrollView

    class StartupErrorApp(App):
        def build(self):
            label = Label(
                text="Cabinet could not start.\n\n" + details,
                size_hint_y=None,
                halign="left",
                valign="top",
                padding=(12, 12),
            )
            label.bind(
                width=lambda widget, value: setattr(widget, "text_size", (value, None)),
                texture_size=lambda widget, value: setattr(widget, "height", value[1]),
            )
            scroll = ScrollView()
            scroll.add_widget(label)
            return scroll

    StartupErrorApp().run()


if __name__ == "__main__":
    try:
        from cabinet.app import CabinetApp
    except Exception:
        details = traceback.format_exc()
        try:
            _show_startup_error(details)
        except Exception:
            pass
        raise
    CabinetApp().run()
