"""
IBVAP — Indian number-plate grammar.

`parse_plate(raw)` fits an OCR string to the plate formats in use and repairs
characters OCR routinely confuses (O/0, I/1, B/8, S/5, ...) using the position:
a slot that must be a digit turns "O" into "0", a letter slot turns "0" into "O".

Formats:
  standard  SS DD L{0-3} NNNN   state code, 1-2 digit district, series, number
                                (covers the old Delhi "DL 3C AB 1234" style)
  bharat    YY BH NNNN L{1-2}   BH series for transferable vehicles

Nepali/Bhutanese plates are not handled: Nepali plates are Devanagari and need
a different OCR model.
"""

import re
from dataclasses import dataclass

STATE_CODES = frozenset(
    "AN AP AR AS BR CG CH DD DL DN GA GJ HP HR JH JK KA KL LA LD MH ML MN MP MZ "
    "NL OD OR PB PY RJ SK TN TR TS UA UK UP WB".split()
)

_TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "U": "0", "I": "1", "L": "1", "T": "1", "J": "1",
             "Z": "2", "S": "5", "B": "8", "G": "6", "A": "4"}
_TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "4": "A"}
# A misread state code often only makes sense with the other reading of "0".
_STATE_ALTERNATIVES = {"0": ("O", "D")}
MAX_CORRECTIONS = 3
_NON_ALNUM = re.compile(r"[^A-Z0-9]")


@dataclass(frozen=True)
class PlateReading:
    text: str
    kind: str  # standard | bharat | unknown
    corrections: int = 0

    @property
    def valid(self) -> bool:
        return self.kind != "unknown"


def _templates():
    """(kind, pattern) where pattern is a string of 'L' (letter) / 'D' (digit)."""
    out = []
    for district in (2, 1):
        for series in (2, 1, 3, 0):
            out.append(("standard", "LL" + "D" * district + "L" * series + "DDDD"))
    for series in (2, 1):
        out.append(("bharat", "DDLLDDDD" + "L" * series))
    return out


_TEMPLATES = _templates()


def _fit(text: str, pattern: str) -> tuple[str, int] | None:
    fixed, changes = [], 0
    for char, slot in zip(text, pattern):
        if slot == "D":
            if char.isdigit():
                fixed.append(char)
            elif char in _TO_DIGIT:
                fixed.append(_TO_DIGIT[char])
                changes += 1
            else:
                return None
        else:
            if char.isalpha():
                fixed.append(char)
            elif char in _TO_LETTER:
                fixed.append(_TO_LETTER[char])
                changes += 1
            else:
                return None
    return "".join(fixed), changes


def _repair_state(raw_state: str, value: str) -> str | None:
    options = [_STATE_ALTERNATIVES.get(c, (value[i],)) for i, c in enumerate(raw_state)]
    for first in options[0]:
        for second in options[1]:
            if first + second in STATE_CODES:
                return first + second + value[2:]
    return None


def _candidates(text: str):
    yield text
    if text.startswith("IND") and len(text) > 3:
        yield text[3:]


def parse_plate(raw: str | None) -> PlateReading:
    cleaned = _NON_ALNUM.sub("", (raw or "").upper())
    best: PlateReading | None = None
    for text in _candidates(cleaned):
        for kind, pattern in _TEMPLATES:
            if len(pattern) != len(text):
                continue
            fitted = _fit(text, pattern)
            if fitted is None:
                continue
            value, changes = fitted
            if kind == "standard" and value[:2] not in STATE_CODES:
                value = _repair_state(text[:2], value)
                if value is None:
                    continue
            if kind == "bharat" and value[2:4] != "BH":
                continue
            # Template order is the tie-breaker (most common layouts first).
            if changes > MAX_CORRECTIONS:
                continue
            if best is None or changes < best.corrections:
                best = PlateReading(value, kind, changes)
    return best or PlateReading(cleaned, "unknown")
