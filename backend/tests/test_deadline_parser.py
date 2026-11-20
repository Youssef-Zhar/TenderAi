from datetime import time

import pytest

from app.services.deadline_parser import parse_deadline_time


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("15 novembre 2026 à 10:30", time(10, 30)),
        ("15 novembre 2026 à 9h05", time(9, 5)),
        ("15 novembre 2026 à 10 h 00", time(10, 0)),
        ("15 novembre 2026", None),
        ("15 novembre 2026 à 24:00", None),
        ("15 novembre 2026 à 10:60", None),
        ("15 novembre 2026 à 10:30 et 11:00", None),
        (None, None),
        ("", None),
    ],
)
def test_parse_deadline_time(value, expected):
    assert parse_deadline_time(value) == expected
