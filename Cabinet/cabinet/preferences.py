"""First-run preference persistence independent of the Kivy UI."""


def save_setup_preferences(
    store, settings, *, confirm_profile_overwrite: bool = False
) -> None:
    display_name = settings.get("display_name", "").strip()
    if not display_name:
        raise ValueError("Enter a name or preferred display name.")
    settings = {**settings, "display_name": display_name}
    if (
        store.get_setting("setup_complete", "false") == "true"
        and store.get_setting("display_name", "") != display_name
        and not confirm_profile_overwrite
    ):
        raise ValueError("Confirm profile changes before saving.")
    for key, value in settings.items():
        store.set_setting(key, value)
    store.set_setting("setup_complete", "true")
