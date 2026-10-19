"""Tailored resumes as PDF: one column of real text that a parser can read back."""

import io

from pypdf import PdfReader

from app.schemas import ResumeContent
from app.services.pdf import render_pdf
from tests.tokens import USER_B, auth_header


def _text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


def test_the_pdf_reads_back_as_text(sample_resume_content):
    pdf = render_pdf(ResumeContent.model_validate(sample_resume_content))

    assert pdf.startswith(b"%PDF")
    text = _text(pdf)
    for expected in (
        "Om Patel", "om@example.com", "SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS",
        "EDUCATION", "Acme Corp", "Built internal tooling in Python.", "State University",
    ):
        assert expected in text, expected


def test_a_short_resume_is_one_page(sample_resume_content):
    pdf = render_pdf(ResumeContent.model_validate(sample_resume_content))

    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1


def test_typographic_characters_do_not_break_it():
    """Built-in PDF fonts only cover Latin-1. Curly quotes, dashes and bullets
    from an LLM or a pasted resume are swapped for plain ones, not dropped."""
    content = ResumeContent(
        full_name="José Núñez",
        summary="Led a team’s “migration” — 2020–2024 … • shipped",
        skills=["C++", "Node.js"],
    )

    text = _text(render_pdf(content))

    assert "José Núñez" in text  # accented Latin letters are kept
    assert "team's \"migration\" - 2020-2024 ... - shipped" in text


def test_characters_outside_latin_1_become_question_marks_not_an_error():
    content = ResumeContent(full_name="Li 李", summary="Fine")

    text = _text(render_pdf(content))

    assert "Li ?" in text


def test_pdf_endpoint(client, make_application, make_resume, fake_tailoring):
    make_resume()
    app_id = make_application()["id"]
    tailored = client.post(f"/api/applications/{app_id}/tailor", json={}).json()

    resp = client.get(f"/api/tailored/{tailored['id']}/pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"] == f"attachment; filename=resume-{tailored['id']}.pdf"
    assert "Engineer targeting Backend Engineer at Globex." in _text(resp.content)
    # Someone else's tailored resume is not found, like every other endpoint.
    assert client.get(f"/api/tailored/{tailored['id']}/pdf", headers=auth_header(USER_B)).status_code == 404


def test_unicode_hyphens_and_spaces_are_kept_as_plain_ones():
    """Seen live: "full‑stack" (U+2011) and "10.8 ms" (U+202F) printed as "?"."""
    content = ResumeContent(
        full_name="Om Patel",
        summary="Built full‑stack apps; cut latency 10.8 ms → 0.35 ms (≈ 30x).",
    )

    text = _text(render_pdf(content))

    assert "full-stack" in text
    assert "10.8 ms -> 0.35 ms (~ 30x)" in text
    assert "?" not in text


def _text_runs(pdf: bytes):
    """(text, x, y) for every piece of text drawn on page 1, in points."""
    runs = []

    def visit(text, cm, tm, font_dict, font_size):
        if text.strip():
            runs.append((text.strip(), tm[4], tm[5]))

    PdfReader(io.BytesIO(pdf)).pages[0].extract_text(visitor_text=visit)
    return runs


def test_a_long_title_wraps_instead_of_running_into_the_date():
    """Seen live: a long title and organization overlapped the right-aligned dates."""
    from fpdf import FPDF

    title = "Undergraduate Research Assistant, Machine Learning, Pennsylvania State University - Harrisburg"
    dates = "Aug 2025 - Present"
    content = ResumeContent(
        full_name="Om Patel",
        experience=[{"company": "Lab", "title": title, "dates": dates, "bullets": ["Did things."]}],
    )

    runs = _text_runs(render_pdf(content))

    [(_, date_x, date_y)] = [r for r in runs if r[0] == dates]
    measure = FPDF(unit="pt")
    measure.set_font("Helvetica", "B", 10)
    same_line = [r for r in runs if abs(r[2] - date_y) < 1 and r[0] != dates]
    assert same_line, "the title's first line should share the date's line"
    for text, x, _ in same_line:
        assert x + measure.get_string_width(text) <= date_x, f"{text!r} runs into the date"
    # Nothing was cut: the whole title is still in the PDF, across its lines.
    assert " ".join(_text(render_pdf(content)).split()).count("Pennsylvania State University - Harrisburg") == 1
