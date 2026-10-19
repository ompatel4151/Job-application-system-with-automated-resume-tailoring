"""A rule-based ATS readiness check for a resume.

Real applicant tracking systems (Workday, Greenhouse, Lever...) don't publish
a score, so this doesn't pretend to predict one. It checks the things that
commonly make a resume hard for that kind of software to use, in code, with
no LLM: the same resume always gets the same report, and every point lost
comes with the reason.

Points (100 total): the PDF's text reads back 25, standard headings 10,
email and phone 15, job keywords 35, bullets with numbers 10, length 5.
"""

import io
import re

from pypdf import PdfReader

from app.schemas import AtsCheck, AtsReport, ResumeContent
from app.services.pdf import latin1, render_pdf

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
# A bullet "has a number" if it states a quantity: 40%, 3 tools, $2M, 10x.
NUMBER = re.compile(r"\d")


def _squash(text: str) -> str:
    """Lowercase with all whitespace collapsed, so line wrapping in the PDF
    doesn't affect comparisons."""
    return " ".join(text.split()).lower()


def _all_text(content: ResumeContent) -> str:
    parts = [content.full_name, content.contact, content.summary, *content.skills]
    for e in content.experience:
        parts += [e.title, e.company, e.dates, *e.bullets]
    for p in content.projects:
        parts += [p.name, p.description, *p.technologies, *p.bullets]
    for ed in content.education:
        parts += [ed.school, ed.degree, ed.dates, *ed.details]
    return "\n".join(parts)


def _bullets(content: ResumeContent) -> list[str]:
    return [b for e in content.experience for b in e.bullets] + [
        b for p in content.projects for b in p.bullets
    ]


def _parse_check(content: ResumeContent, pdf: bytes) -> AtsCheck:
    """Render the real PDF, extract its text, and look for everything that
    should be there: the name, each section's heading, and every bullet."""
    extracted = _squash("\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages))
    expected = [content.full_name] if content.full_name else []
    sections = {
        "Summary": content.summary, "Skills": content.skills, "Experience": content.experience,
        "Projects": content.projects, "Education": content.education,
    }
    expected += [title.upper() for title, value in sections.items() if value]
    expected += _bullets(content)
    lost = [item for item in expected if _squash(latin1(item)) not in extracted]
    if lost:
        return AtsCheck(
            name="parse", label="Text reads back from the PDF", passed=False, points=0,
            max_points=25, detail=f"{len(lost)} item(s) didn't come back out of the PDF text.",
            missing=lost[:5],
        )
    found = sum(1 for v in sections.values() if v)
    return AtsCheck(
        name="parse", label="Text reads back from the PDF", passed=True, points=25,
        max_points=25, detail=f"All text reads back from the PDF ({found} sections).",
    )


def _headings_check(content: ResumeContent) -> AtsCheck:
    required = {
        "Summary": content.summary, "Skills": content.skills,
        "Experience": content.experience, "Education": content.education,
    }
    missing = [title for title, value in required.items() if not value]
    points = round(10 * (len(required) - len(missing)) / len(required))
    detail = (
        "Has the standard sections: Summary, Skills, Experience, Education."
        if not missing else f"No {', '.join(missing)} section."
    )
    return AtsCheck(
        name="headings", label="Standard sections", passed=not missing, points=points,
        max_points=10, detail=detail, missing=missing,
    )


def _has_phone(text: str) -> bool:
    # At least 10 digits, so a year range like "2020-2024" isn't a phone.
    return any(sum(ch.isdigit() for ch in m.group()) >= 10 for m in PHONE.finditer(text))


def _contact_check(content: ResumeContent) -> AtsCheck:
    email, phone = bool(EMAIL.search(content.contact)), _has_phone(content.contact)
    absent = [name for name, ok in (("email", email), ("phone", phone)) if not ok]
    return AtsCheck(
        name="contact", label="Email and phone", passed=not absent,
        points=10 * email + 5 * phone, max_points=15,
        detail="Email and phone found." if not absent else f"No {' or '.join(absent)} found.",
        missing=absent,
    )


def _keywords_check(content: ResumeContent, keywords: list[str]) -> AtsCheck:
    """Whole-word, case-insensitive: "Go" doesn't match inside "Google"."""
    text = _all_text(content)
    keywords = list(dict.fromkeys(k for k in keywords if k.strip()))  # dedupe, keep order
    if not keywords:
        return AtsCheck(
            name="keywords", label="Job keywords", passed=True, points=35, max_points=35,
            detail="No job keywords to check against.",
        )
    missing = [
        k for k in keywords
        if not re.search(rf"(?<!\w){re.escape(k)}(?!\w)", text, re.IGNORECASE)
    ]
    found = len(keywords) - len(missing)
    return AtsCheck(
        name="keywords", label="Job keywords", passed=not missing,
        points=round(35 * found / len(keywords)), max_points=35,
        detail=f"{found} of {len(keywords)} keywords from the job are in the resume.",
        missing=missing,
    )


def _numbers_check(content: ResumeContent) -> AtsCheck:
    bullets = _bullets(content)
    with_numbers = sum(1 for b in bullets if NUMBER.search(b))
    # Full marks once half the bullets state a number; recruiters skim for them.
    ratio = with_numbers / len(bullets) if bullets else 0
    points = round(10 * min(1, ratio / 0.5))
    return AtsCheck(
        name="numbers", label="Bullets with numbers", passed=points == 10, points=points,
        max_points=10, detail=f"{with_numbers} of {len(bullets)} bullets include a number.",
    )


def _length_check(pdf: bytes) -> AtsCheck:
    pages = len(PdfReader(io.BytesIO(pdf)).pages)
    ok = pages <= 2
    return AtsCheck(
        name="length", label="Length", passed=ok, points=5 if ok else 0, max_points=5,
        detail=f"{pages} page{'s' if pages != 1 else ''}." + ("" if ok else " Aim for 1 or 2."),
    )


def ats_check(content: ResumeContent, keywords: list[str]) -> AtsReport:
    """`keywords`: what the job asks for (the match analysis's matched and
    missing keywords); whether each is in the resume is decided here, in code."""
    pdf = render_pdf(content)
    checks = [
        _parse_check(content, pdf),
        _headings_check(content),
        _contact_check(content),
        _keywords_check(content, keywords),
        _numbers_check(content),
        _length_check(pdf),
    ]
    return AtsReport(score=sum(c.points for c in checks), checks=checks)
