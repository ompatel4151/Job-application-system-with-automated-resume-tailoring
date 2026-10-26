"""The deterministic half of the invented-fact metric (AGENT_EXPERIMENT.md, 7a).

A bullet is unsupported if it contains a number, or a named tool from
eval/tech_terms.txt, that no fact on the sheet contains. It can't judge plain
claims ("led a team", "recent graduate"); the LLM judge covers those, and the
headline number is the union of both.

Numbers are compared as values with an optional unit: "1,235" == "1235",
"500K+" == "500000", "36 %" == "36%". If both sides state a unit, the units
must match ("10 ms" doesn't support "10%"); if either side has none, the value
alone counts.
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.services.pdf import latin1  # noqa: E402  (same character cleanup as the PDF)

TERMS_FILE = Path(__file__).with_name("tech_terms.txt")

# A number not glued to a letter or dot on its left ("ES256", "p95" and "v1.2"
# aren't metrics), with an optional unit.
_NUMBER = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?(%|ms|sec|s|x|k|b|gb|mb|kb)?(?:\+)?(?![a-z0-9])",
    re.IGNORECASE,
)
_UNIT = {"sec": "s"}


def numbers_in(text: str) -> set[tuple[float, str]]:
    found = set()
    for value, unit in _NUMBER.findall(latin1(text)):
        number = float(value.replace(",", ""))
        unit = _UNIT.get(unit.lower(), unit.lower())
        if unit == "k":
            number, unit = number * 1000, ""
        elif unit == "x":
            unit = ""
        found.add((number, unit))
    return found


def load_terms(path: Path = TERMS_FILE) -> list[str]:
    lines = (line.strip() for line in path.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def _term_pattern(term: str) -> re.Pattern:
    flags = 0 if len(term) <= 3 else re.IGNORECASE
    return re.compile(rf"(?<![\w]){re.escape(term)}(?![\w+#])", flags)


@dataclass
class Fact:
    id: str
    text: str
    numbers: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    context: str = ""


@dataclass
class Verdict:
    supported: bool
    unsupported_numbers: list[str]
    unsupported_terms: list[str]


class Checker:
    def __init__(self, facts: list[Fact], terms: list[str] | None = None):
        self.terms = [(t, _term_pattern(t)) for t in (terms or load_terms())]
        sheet = "\n".join(
            [f.text for f in facts] + [n for f in facts for n in f.numbers] + [t for f in facts for t in f.tools]
        )
        self._sheet_numbers = numbers_in(sheet)
        self._sheet_text = latin1(sheet)

    def _number_supported(self, number: tuple[float, str]) -> bool:
        value, unit = number
        return any(
            v == value and (not unit or not u or unit == u) for v, u in self._sheet_numbers
        )

    def check(self, bullet: str) -> Verdict:
        text = latin1(bullet)
        bad_numbers = sorted(
            f"{v:g}{u}" for v, u in numbers_in(text) if not self._number_supported((v, u))
        )
        bad_terms = [
            term for term, pattern in self.terms
            if pattern.search(text) and not pattern.search(self._sheet_text)
        ]
        return Verdict(not bad_numbers and not bad_terms, bad_numbers, bad_terms)


def bullets_of(resume: dict) -> list[str]:
    """The units the metric counts: experience and project bullets, plus each
    summary sentence."""
    summary = [s for s in re.split(r"(?<=[.!?])\s+", resume.get("summary") or "") if s.strip()]
    experience = [b for e in resume.get("experience", []) for b in e.get("bullets", [])]
    projects = [b for p in resume.get("projects", []) for b in p.get("bullets", [])]
    return summary + experience + projects
