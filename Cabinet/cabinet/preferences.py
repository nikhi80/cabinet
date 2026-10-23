"""First-run preference persistence independent of the Kivy UI."""

from datetime import date


GENDER_OPTIONS = ("Female", "Male", "Prefer not to say")


def format_date_of_birth_input(value: str) -> str:
    """Format typed digits as YYYY-MM-DD, inserting separators automatically."""
    digits = "".join(
        character for character in value if "0" <= character <= "9"
    )[:8]
    if len(digits) > 6:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    if len(digits) > 4:
        return f"{digits[:4]}-{digits[4:]}"
    return digits


def validate_date_of_birth(value: str, today: date | None = None) -> str:
    cleaned = value.strip()
    try:
        birth_date = date.fromisoformat(cleaned)
    except ValueError as error:
        raise ValueError("Date of birth must use YYYY-MM-DD format.") from error
    if birth_date.isoformat() != cleaned:
        raise ValueError("Date of birth must use YYYY-MM-DD format.")
    current_date = today or date.today()
    if birth_date.year > current_date.year:
        raise ValueError("Year of birth cannot be later than the current year.")
    age = calculate_age(cleaned, today)
    if age > 120:
        raise ValueError("Enter a valid date of birth.")
    return cleaned


def calculate_age(value: str, today: date | None = None) -> int:
    birth_date = date.fromisoformat(value)
    current_date = today or date.today()
    if birth_date > current_date:
        raise ValueError("Date of birth cannot be in the future.")
    return current_date.year - birth_date.year - (
        (current_date.month, current_date.day)
        < (birth_date.month, birth_date.day)
    )


def validate_gender(value: str) -> str:
    if value not in GENDER_OPTIONS:
        raise ValueError("Choose Female, Male, or Prefer not to say.")
    return value


def is_menstruation_eligible(
    gender: str, date_of_birth: str, today: date | None = None
) -> bool:
    try:
        return (
            validate_gender(gender) == "Female"
            and calculate_age(validate_date_of_birth(date_of_birth, today), today) >= 12
        )
    except ValueError:
        return False


def menstruation_tab_enabled(store, today: date | None = None) -> bool:
    return (
        store.get_setting("feature_cycle", "false") == "true"
        and is_menstruation_eligible(
            store.get_setting("gender", ""),
            store.get_setting("date_of_birth", ""),
            today,
        )
    )


def save_setup_preferences(
    store, settings, *, confirm_profile_overwrite: bool = False
):
    if "date_of_birth" in settings or "gender" in settings:
        display_name = settings.get("display_name", "").strip()
        if not display_name:
            raise ValueError("Enter a name or preferred display name.")
        settings = {
            **settings,
            "display_name": display_name,
            "date_of_birth": validate_date_of_birth(settings.get("date_of_birth", "")),
            "gender": validate_gender(settings.get("gender", "")),
        }
        profile_changed = any(
            store.get_setting(key, "") != value
            for key, value in (
                ("display_name", settings["display_name"]),
                ("date_of_birth", settings["date_of_birth"]),
                ("gender", settings["gender"]),
            )
        )
        if (
            store.get_setting("setup_complete", "false") == "true"
            and profile_changed
            and not confirm_profile_overwrite
        ):
            raise ValueError("Confirm profile changes before saving.")
    for key, value in settings.items():
        store.set_setting(key, value)
    store.set_setting("setup_complete", "true")
