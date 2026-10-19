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
