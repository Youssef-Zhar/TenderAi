"""
app/services/deadline_parser.py
--------------------------------
Parse human-written procurement deadlines into ``datetime.date`` objects.

The AI model returns the submission deadline verbatim (usually in French, e.g.
``"15 novembre 2026 à 12 h 00"``). This module normalises common written
forms and parses the calendar date and, separately, an explicit 24-hour time.
Unrecognised or ambiguous values return ``None``; the original source wording
is preserved by the API for review.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time

_MONTHS: dict[str, int] = {
    # French
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
    # English (kept for backward compatibility)
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# Common abbreviated month names seen in extracted text.
_MONTH_ABBREVIATIONS: dict[str, int] = {
    "janv": 1,
    "fev": 2,
    "fevr": 2,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_NUMERIC_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")

_TEXTUAL_RE = re.compile(
    r"(\d{1,2})(?:er)?\s+([a-z]+)\.?\s+(\d{4})",
    re.IGNORECASE,
)


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _normalise(value: str) -> str:
    text = _strip_accents(value).lower()
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_deadline(value: str | None) -> date | None:
    """
    Return the calendar date encoded in ``value``, or ``None``.

    Recognised forms include ISO (``2026-11-15``), slash/dash numeric
    (``15/11/2026``, ``15-11-2026``) and textual month names with an optional
    time (``15 novembre 2026``, ``15 novembre 2026 à 12 h 00``,
    ``15 novembre 2026 à 12:00``). Accented and unaccented French month names
    are both accepted, and the ``1er`` ordinal is supported.
    """
    if not value or not isinstance(value, str):
        return None

    cleaned = _normalise(value)
    if not cleaned:
        return None

    for fmt in _NUMERIC_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    match = _TEXTUAL_RE.search(cleaned)
    if match:
        day, month_name, year = match.groups()
        month = _MONTHS.get(month_name) or _MONTH_ABBREVIATIONS.get(month_name)
        if month:
            try:
                return date(int(year), month, int(day))
            except ValueError:
                return None

    return None


def parse_deadline_time(value: str | None) -> time | None:
    """Parse one explicit 24-hour time; ambiguous or invalid values return None."""
    if not value or not isinstance(value, str):
        return None
    matches = list(re.finditer(
        r"(?<!\d)(\d{1,2})\s*(?:h|:)\s*(\d{2})(?!\d)",
        _normalise(value),
        re.IGNORECASE,
    ))
    if len(matches) != 1:
        return None
    hour, minute = int(matches[0].group(1)), int(matches[0].group(2))
    if hour > 23 or minute > 59:
        return None
    return time(hour=hour, minute=minute)
