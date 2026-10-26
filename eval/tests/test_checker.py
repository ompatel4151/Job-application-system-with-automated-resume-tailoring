"""The invented-fact checker: deterministic, so it gets ordinary unit tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checker import Checker, Fact, bullets_of, numbers_in  # noqa: E402

FACTS = [
    Fact("idx", "Added an index that cut the query from 10.8 ms to 0.35 ms.", ["10.8 ms", "0.35 ms"], ["PostgreSQL"]),
    Fact("rag", "Retrieval over 1,235 chunks; stress test at ~500K+ items/sec.", ["1,235", "500K+"], ["FAISS"]),
    Fact("tests", "218 tests with 92% coverage.", ["218", "92%"], ["pytest"]),
]


def check(bullet):
    return Checker(FACTS).check(bullet)


def test_numbers_from_the_sheet_are_supported_in_any_spelling():
    assert check("Cut a PostgreSQL query from 10.8ms to 0.35 ms.").supported
    assert check("Indexed 1235 chunks with FAISS and hit 500,000 items/sec.").supported
    assert check("Wrote 218 tests (92 % coverage) with pytest.").supported


def test_a_number_not_on_the_sheet_is_flagged():
    verdict = check("Cut latency by 40% with PostgreSQL.")

    assert not verdict.supported
    assert verdict.unsupported_numbers == ["40%"]


def test_units_must_agree_when_both_sides_have_one():
    """10.8 ms on the sheet doesn't support "10.8%"."""
    assert check("Improved hit rate to 10.8%.").unsupported_numbers == ["10.8%"]


def test_a_tool_not_on_the_sheet_is_flagged():
    verdict = check("Deployed it on Kubernetes with PostgreSQL.")

    assert verdict.unsupported_terms == ["Kubernetes"]


def test_short_terms_match_case_sensitively():
    """"Go" the language, not "go" the verb; "Java" doesn't match "JavaScript"."""
    assert check("Helped the team go faster.").supported
    assert check("Rewrote a service in Go.").unsupported_terms == ["Go"]
    assert check("Built JavaScript tooling.").unsupported_terms == ["JavaScript"]


def test_identifiers_with_digits_are_not_metrics():
    """ES256, p95 and v1.2 are names, not numbers to verify."""
    assert check("Verified ES256 tokens and tracked p95 in v1.2.").unsupported_numbers == []


def test_unicode_dashes_and_spaces_dont_hide_a_number():
    assert check("Cut it from 10.8 ms to 0.35 ms.").supported
    assert numbers_in("full‑stack 36 %") == {(36.0, "%")}


def test_bullets_of_counts_summary_sentences_and_all_bullets():
    resume = {
        "summary": "Backend engineer. Builds reliable APIs!",
        "experience": [{"bullets": ["A.", "B."]}],
        "projects": [{"bullets": ["C."]}],
    }

    assert bullets_of(resume) == ["Backend engineer.", "Builds reliable APIs!", "A.", "B.", "C."]
