"""Indian number-plate grammar and OCR correction."""

import numpy as np
import pytest

from src.anpr.plate_format import parse_plate


@pytest.mark.parametrize(
    "raw, expected, kind",
    [
        ("MH12AB3456", "MH12AB3456", "standard"),
        ("mh 12 ab 3456", "MH12AB3456", "standard"),
        ("MH12A83456", "MH12AB3456", "standard"),  # 8 read in a letter slot
        ("MHI2AB3456", "MH12AB3456", "standard"),  # I read in a digit slot
        ("0L01C0001", "DL01C0001", "standard"),  # 0 read in the state code
        ("KA05MN9999", "KA05MN9999", "standard"),
        ("DL3CAB1234", "DL3CAB1234", "standard"),  # old Delhi 1-digit district, 3-letter series
        ("UP320001", "UP320001", "standard"),  # no series letters
        ("IND MH12AB3456", "MH12AB3456", "standard"),  # hologram text read as a prefix
        ("22BH1234AA", "22BH1234AA", "bharat"),
        ("22BH1234A", "22BH1234A", "bharat"),
        ("Z2BHI234AA", "22BH1234AA", "bharat"),
    ],
)
def test_valid_plates_are_normalised(raw, expected, kind):
    reading = parse_plate(raw)
    assert reading.valid
    assert reading.text == expected
    assert reading.kind == kind


def test_corrections_are_counted():
    assert parse_plate("MH12AB3456").corrections == 0
    assert parse_plate("MH12A83456").corrections == 1


@pytest.mark.parametrize("raw", ["", "HELLO", "12345678", "XX12AB3456", "MH12XY3", "MH12ABCD3456", "STOP"])
def test_non_plates_are_rejected(raw):
    reading = parse_plate(raw)
    assert not reading.valid
    assert reading.kind == "unknown"


def test_extract_plate_applies_grammar(monkeypatch):
    import src.features.anpr as anpr

    monkeypatch.setattr(anpr, "_plate_detector", lambda: None)
    crop = np.zeros((40, 120, 3), np.uint8)

    monkeypatch.setattr(anpr, "read_plate", lambda img: ("MH12A83456", 0.9))
    plate = anpr.extract_plate(crop)
    assert plate["text"] == "MH12AB3456"
    assert plate["format"] == "standard"
    assert plate["confidence"] < 0.9  # a corrected read is trusted a little less

    monkeypatch.setattr(anpr, "read_plate", lambda img: ("SPEED LIMIT", 0.95))
    assert anpr.extract_plate(crop)["text"] == "Unknown"
    # Foreign / non-standard plates can still be kept when strict mode is off.
    loose = anpr.extract_plate(crop, strict_format=False)
    assert loose["text"] == "SPEEDLIMIT" and loose["format"] == "unknown"
