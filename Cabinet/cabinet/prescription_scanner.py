"""Local prescription OCR and conservative extraction of readable fields."""

from __future__ import annotations

import hashlib
import json
import re
import time
from importlib import import_module
from pathlib import Path
from typing import Any

from kivy.utils import platform


_STRENGTH = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mcg|μg|mg|g|kg|ml|mL|iu|units?)\b"
    r"|\b\d+(?:\.\d+)?\s*%",
    re.IGNORECASE,
)
_DOSE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:tablets?|tabs?|capsules?|caps?|ml|mL|drops?|puffs?)\b",
    re.IGNORECASE,
)
_FREQUENCIES = (
    (
        re.compile(r"\b(?:once|1\s+time)\s+(?:daily|a day|per day)\b", re.IGNORECASE),
        "once daily",
    ),
    (
        re.compile(
            r"\b(?:twice|2\s+times)\s+(?:daily|a day|per day)\b", re.IGNORECASE
        ),
        "twice daily",
    ),
    (
        re.compile(
            r"\b(?:three|3)\s+times\s+(?:daily|a day|per day)\b", re.IGNORECASE
        ),
        "three times daily",
    ),
    (
        re.compile(
            r"\b(?:four|4)\s+times\s+(?:daily|a day|per day)\b", re.IGNORECASE
        ),
        "four times daily",
    ),
    (
        re.compile(r"\bevery\s+\d+\s+hours?\b", re.IGNORECASE),
        "",
    ),
)
_DURATION = re.compile(
    r"\bfor\s+(\d+)\s*(days?|weeks?)\b", re.IGNORECASE
)
_QUANTITY = re.compile(
    r"\b(?:qty|quantity|dispense|dispensed)\s*[:#]?\s*(\d+)\b", re.IGNORECASE
)
_INSTRUCTIONS = re.compile(
    r"\b(before food|after food|with food|with meals|on an empty stomach)\b",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_CLOCK_TIME = re.compile(r"\b(0?[1-9]|1[0-2])(?::([0-5]\d))?\s*([ap])\.?m\.?\b", re.I)
_MILITARY_TIME = re.compile(r"\b([01]\d|2[0-3]):([0-5]\d)\b")


def _clean_line(line: str) -> str:
    return re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()


def _candidate_from_lines(lines: list[str]) -> dict[str, Any]:
    text = " ".join(lines)
    strength_match = _STRENGTH.search(text)
    dose_match = _DOSE.search(text)
    name = ""
    if strength_match:
        name = text[: strength_match.start()]
    elif dose_match:
        name = text[: text.find(dose_match.group(0))]
    name = re.sub(
        r"^(?:rx\s*[:.-]?\s*|(?:medicine|medication)\s*[:.-]\s*)",
        "",
        name,
        flags=re.I,
    )
    name = re.sub(r"\b(?:take|use|give|apply)\s*$", "", name, flags=re.I)
    name = re.sub(r"[\s,;:–—-]+$", "", name).strip()

    strength = strength_match.group(0).strip() if strength_match else ""
    frequency = ""
    for pattern, normalized in _FREQUENCIES:
        frequency_match = pattern.search(text)
        if frequency_match:
            frequency = normalized or frequency_match.group(0).casefold()
            break
    duration_match = _DURATION.search(text)
    duration_days = ""
    if duration_match:
        duration_days = str(int(duration_match.group(1)) * (
            7 if duration_match.group(2).casefold().startswith("week") else 1
        ))
    quantity_match = _QUANTITY.search(text)
    date_match = _ISO_DATE.search(text)
    instructions_match = _INSTRUCTIONS.search(text)
    reminder_times = []
    for match in _CLOCK_TIME.finditer(text):
        hour = int(match.group(1)) % 12
        if match.group(3).casefold() == "p":
            hour += 12
        reminder_times.append(f"{hour:02d}:{int(match.group(2) or 0):02d}")
    reminder_times.extend(
        f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"
        for match in _MILITARY_TIME.finditer(text)
    )
    return {
        "name": name,
        "strength": strength,
        "dose": dose_match.group(0).strip() if dose_match else "",
        "frequency": frequency,
        "instructions": instructions_match.group(0).casefold()
        if instructions_match
        else "",
        "start_date": date_match.group(1) if date_match else "",
        "duration_days": duration_days,
        "prescribed_quantity": quantity_match.group(1) if quantity_match else "",
        "reminder_times": ", ".join(dict.fromkeys(reminder_times)),
        "confirmed": False,
    }


def extract_medicines(text: str) -> list[dict[str, Any]]:
    """Extract only values matching explicit, narrow patterns; never auto-confirm."""
    lines = [_clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    strength_starts = [
        index
        for index, line in enumerate(lines)
        if _STRENGTH.search(line)
    ]
    starts = strength_starts or [
        index
        for index, line in enumerate(lines)
        if _DOSE.search(line)
        and any(
            pattern.search(" ".join(lines[index : index + 2]))
            for pattern, _normalized in _FREQUENCIES
        )
    ]
    candidates: list[dict[str, Any]] = []
    for position, start in enumerate(starts):
        end = (
            starts[position + 1]
            if position + 1 < len(starts)
            else min(len(lines), start + 4)
        )
        block_start = start
        strength_on_line = _STRENGTH.search(lines[start])
        strength_name = (
            lines[start][: strength_on_line.start()].strip()
            if strength_on_line
            else ""
        )
        if start > 0 and not strength_name:
            previous = lines[start - 1]
            if not _STRENGTH.search(previous) and not _DOSE.search(previous):
                block_start = start - 1
        candidate = _candidate_from_lines(lines[block_start:end])
        if any(
            candidate[key]
            for key in ("name", "strength", "dose", "frequency", "duration_days")
        ):
            candidates.append(candidate)
    return candidates


def image_sha256(image_path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(image_path).open("rb") as image_file:
        for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prescription_fingerprint(items: list[dict[str, Any]]) -> str:
    canonical_items = [
        {
            key: str(item.get(key, "")).strip().casefold()
            for key in (
                "name",
                "strength",
                "dose",
                "frequency",
                "instructions",
                "start_date",
                "duration_days",
                "prescribed_quantity",
            )
        }
        for item in items
    ]
    canonical_items.sort(key=lambda item: json.dumps(item, sort_keys=True))
    encoded = json.dumps(canonical_items, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def read_prescription_text(image_path: str | Path) -> str:
    """Run local OCR using bundled ML Kit on Android and Tesseract on desktop."""
    if platform == "android":
        try:
            jnius = import_module("jnius")
        except ImportError as error:
            raise RuntimeError(
                "Android OCR is unavailable because the ML Kit bridge was not packaged."
            ) from error
        autoclass = getattr(jnius, "autoclass")
        java_exception = getattr(jnius, "JavaException")
        recognizer = None
        bitmap = None
        try:
            bitmap_factory = autoclass("android.graphics.BitmapFactory")
            bitmap_options = autoclass("android.graphics.BitmapFactory$Options")()
            bitmap_options.inJustDecodeBounds = True
            bitmap_factory.decodeFile(str(image_path), bitmap_options)
            if bitmap_options.outWidth <= 0 or bitmap_options.outHeight <= 0:
                raise RuntimeError("Android couldn't decode this prescription image.")
            max_dimension = 2048
            sample_size = 1
            while (
                bitmap_options.outWidth // sample_size > max_dimension
                or bitmap_options.outHeight // sample_size > max_dimension
            ):
                sample_size *= 2
            bitmap_options.inJustDecodeBounds = False
            bitmap_options.inSampleSize = sample_size
            bitmap = bitmap_factory.decodeFile(str(image_path), bitmap_options)
            if bitmap is None:
                raise RuntimeError("Android couldn't decode this prescription image.")
            input_image = autoclass(
                "com.google.mlkit.vision.common.InputImage"
            ).fromBitmap(bitmap, 0)
            options = autoclass(
                "com.google.mlkit.vision.text.latin.TextRecognizerOptions"
            ).DEFAULT_OPTIONS
            recognizer = autoclass(
                "com.google.mlkit.vision.text.TextRecognition"
            ).getClient(options)
            task = recognizer.process(input_image)
            deadline = time.monotonic() + 120
            while not task.isComplete():
                if time.monotonic() >= deadline:
                    raise RuntimeError("Android OCR took too long. Try a smaller image.")
                time.sleep(0.05)
            if not task.isSuccessful():
                failure = task.getException()
                raise RuntimeError(f"Android ML Kit OCR failed: {failure}")
            return str(task.getResult().getText()).strip()
        except java_exception as error:
            raise RuntimeError(f"Android ML Kit OCR failed: {error}") from error
        finally:
            if recognizer is not None:
                try:
                    recognizer.close()
                except java_exception as error:
                    raise RuntimeError(
                        f"Android ML Kit could not close the OCR session: {error}"
                    ) from error
            if bitmap is not None and not bitmap.isRecycled():
                bitmap.recycle()

    if platform not in {"win", "linux", "macosx"}:
        raise RuntimeError(
            f"Local prescription OCR is not packaged for the {platform} platform."
        )
    try:
        from PIL import Image, ImageOps
        import pytesseract
    except ImportError as error:
        raise RuntimeError(
            "Prescription OCR needs Pillow and pytesseract. Install the Python "
            "dependencies, then install the Tesseract OCR engine."
        ) from error

    try:
        with Image.open(image_path) as image:
            readable_image = ImageOps.autocontrast(image.convert("L"))
            return pytesseract.image_to_string(readable_image, config="--psm 6").strip()
    except pytesseract.pytesseract.TesseractNotFoundError as error:
        raise RuntimeError(
            "Tesseract OCR is not installed or is not on PATH. Install the Tesseract "
            "engine for this device, then reopen Cabinet."
        ) from error
    except pytesseract.pytesseract.TesseractError as error:
        raise RuntimeError(f"Tesseract could not recognize this image: {error}") from error
    except OSError as error:
        raise RuntimeError(f"Cabinet couldn't read this prescription image: {error}") from error
