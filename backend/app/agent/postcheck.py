"""The citation post-check (AGENT_EXPERIMENT.md 3.3), deterministic.

A bullet is rejected if it has a number, or a named tool, that isn't in the
facts it cites. "In" means the fact's text, numbers or tools, so a number that
is on the user's sheet but in a different fact still fails: the bullet has to
cite where it came from.

Numbers are compared as values with an optional unit after the PDF's
character cleanup ("1,235" == "1235", "500K+" == 500000, "10.8ms" == "10.8 ms").
If both sides give a unit they must match. The same rules as eval/checker.py,
which scores the experiment; they're kept as separate copies so the
pre-registered checker never changes.

Tools: the fixed vocabulary in tech_terms.txt plus every tool on the user's
sheet. Terms of 3 characters or fewer match case-sensitively ("Go", "C").
"""

import functools
import re
from pathlib import Path

from app.services.pdf import latin1

_NUMBER = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?(%|ms|sec|s|x|k|b|gb|mb|kb)?(?:\+)?(?![a-z0-9])",
    re.IGNORECASE,
)


def numbers_in(text: str) -> set[tuple[float, str]]:
    found = set()
    for value, unit in _NUMBER.findall(latin1(text)):
        number, unit = float(value.replace(",", "")), unit.lower()
        unit = {"sec": "s", "x": ""}.get(unit, unit)
        if unit == "k":
            number, unit = number * 1000, ""
        found.add((number, unit))
    return found


@functools.cache
def _vocabulary() -> tuple[str, ...]:
    lines = (Path(__file__).with_name("tech_terms.txt").read_text().splitlines())
    return tuple(t for t in (line.strip() for line in lines) if t and not t.startswith("#"))


@functools.cache
def _pattern(term: str) -> re.Pattern:
    flags = 0 if len(term) <= 3 else re.IGNORECASE
    return re.compile(rf"(?<![\w]){re.escape(latin1(term))}(?![\w+#])", flags)


def problems(bullet: str, cited, sheet_tools=()) -> list[str]:
    """Why the bullet fails, or [] if it passes. `cited` are the facts it
    cites (anything with text, numbers and tools)."""
    source = latin1("\n".join([f.text for f in cited] + [x for f in cited for x in [*f.numbers, *f.tools]]))
    have = numbers_in(source)
    text = latin1(bullet)
    found = [
        f"number {v:g}{u} is not in the cited facts"
        for v, u in sorted(numbers_in(text))
        if not any(v == hv and (not u or not hu or u == hu) for hv, hu in have)
    ]
    for term in dict.fromkeys([*_vocabulary(), *sheet_tools]):
        pattern = _pattern(term)
        if pattern.search(text) and not pattern.search(source):
            found.append(f"{term} is not in the cited facts")
    return found
