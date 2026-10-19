"""The rule-based ATS check: the same answer every time, a reason for every
point lost, and no LLM call."""

from app.schemas import MatchAnalysis, ResumeContent
from app.services.ats import ats_check, job_keywords
from tests.tokens import USER_B, auth_header

STRONG = {
    "full_name": "Om Patel",
    "contact": "om@example.com | (555) 123-4567 | github.com/om",
    "summary": "Backend engineer working in Python and PostgreSQL.",
    "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
    "experience": [
        {
            "company": "Acme",
            "title": "Software Engineer Intern",
            "dates": "2025",
            "bullets": ["Cut API latency by 40% with caching.", "Built 3 internal tools in Python."],
        }
    ],
    "education": [{"school": "Penn State", "degree": "BS Computer Science", "dates": "2027"}],
}
KEYWORDS = ["Python", "PostgreSQL", "Docker"]


def _check(name, report):
    return next(c for c in report.checks if c.name == name)


def test_a_strong_resume_scores_100():
    report = ats_check(ResumeContent.model_validate(STRONG), KEYWORDS)

    assert report.score == 100
    assert all(c.passed for c in report.checks)
    assert sum(c.max_points for c in report.checks) == 100


def test_the_same_resume_always_gets_the_same_report():
    content = ResumeContent.model_validate(STRONG)

    assert ats_check(content, KEYWORDS) == ats_check(content, KEYWORDS)


def test_missing_keywords_are_named_and_cost_points():
    report = ats_check(ResumeContent.model_validate(STRONG), [*KEYWORDS, "Kubernetes", "Kafka"])

    keywords = _check("keywords", report)
    assert not keywords.passed
    assert keywords.missing == ["Kubernetes", "Kafka"]
    assert keywords.points == round(35 * 3 / 5)
    assert "3 of 5" in keywords.detail


def test_found_keywords_are_listed_too():
    keywords = _check("keywords", ats_check(ResumeContent.model_validate(STRONG), [*KEYWORDS, "Kafka"]))

    assert keywords.found == KEYWORDS
    assert keywords.missing == ["Kafka"]
    assert "word for word" in keywords.label


def test_unicode_hyphens_match_plain_ones():
    """Seen live: "full‑stack" (U+2011) in the resume vs "full-stack" in the job."""
    content = ResumeContent.model_validate({**STRONG, "summary": "Full\u2011stack engineer."})

    assert _check("keywords", ats_check(content, ["full-stack"])).found == ["full-stack"]


def test_job_keywords_keep_only_terms_that_are_really_in_the_posting():
    """The AI is asked to copy terms from the posting; anything it paraphrased
    or invented is dropped instead of counted."""
    analysis = MatchAnalysis(match_score=70, ats_keywords=["Python", "REST APIs", "distributed systems", "python"])
    posting = "We use Python to build REST APIs at scale."

    assert job_keywords(analysis, posting) == ["Python", "REST APIs"]


def test_job_keywords_fall_back_for_resumes_tailored_before_this_existed():
    analysis = MatchAnalysis(match_score=70, matched_keywords=["Python"], missing_keywords=["Kafka"])

    assert job_keywords(analysis, "Python and Kafka") == ["Python", "Kafka"]


def test_keywords_match_whole_words_case_insensitively():
    """"Go" must not match inside "Google"; "postgresql" matches "PostgreSQL"."""
    content = ResumeContent.model_validate({**STRONG, "summary": "Worked at Google."})

    report = ats_check(content, ["Go", "postgresql", "C++"])

    assert _check("keywords", report).missing == ["Go", "C++"]


def test_no_email_or_phone_is_flagged():
    content = ResumeContent.model_validate({**STRONG, "contact": "github.com/om"})

    contact = _check("contact", ats_check(content, KEYWORDS))

    assert not contact.passed
    assert contact.points == 0
    assert "email" in contact.detail and "phone" in contact.detail


def test_a_year_range_is_not_a_phone_number():
    content = ResumeContent.model_validate({**STRONG, "contact": "om@example.com | 2020-2024"})

    contact = _check("contact", ats_check(content, KEYWORDS))

    assert contact.missing == ["phone"]
    assert contact.points == 10


def test_curly_quotes_still_read_back():
    """The PDF swaps them for plain quotes; the check must compare like with like."""
    bullets = ["Led the team’s “v2” launch — 3 weeks early."]
    content = ResumeContent.model_validate(
        {**STRONG, "experience": [{**STRONG["experience"][0], "bullets": bullets}]}
    )

    assert _check("parse", ats_check(content, KEYWORDS)).passed


def test_missing_standard_sections_are_named():
    content = ResumeContent.model_validate({**STRONG, "summary": "", "education": []})

    headings = _check("headings", ats_check(content, KEYWORDS))

    assert not headings.passed
    assert headings.missing == ["Summary", "Education"]


def test_bullets_without_numbers_lose_points():
    content = ResumeContent.model_validate(
        {**STRONG, "experience": [{**STRONG["experience"][0], "bullets": ["Built tools.", "Wrote docs."]}]}
    )

    numbers = _check("numbers", ats_check(content, KEYWORDS))

    assert not numbers.passed
    assert numbers.points == 0
    assert "0 of 2" in numbers.detail


def test_the_pdf_round_trip_is_checked():
    """The check renders the real PDF and reads it back, so it fails if the
    PDF text ever stops being extractable."""
    report = ats_check(ResumeContent.model_validate(STRONG), KEYWORDS)

    parse = _check("parse", report)
    assert parse.passed
    assert "reads back" in parse.detail


def test_ats_endpoint(client, make_application, make_resume, fake_tailoring):
    make_resume()
    app_id = make_application()["id"]
    tailored = client.post(f"/api/applications/{app_id}/tailor", json={}).json()

    resp = client.get(f"/api/tailored/{tailored['id']}/ats")

    assert resp.status_code == 200
    body = resp.json()
    assert 0 <= body["score"] <= 100
    assert {c["name"] for c in body["checks"]} == {
        "parse", "headings", "contact", "keywords", "numbers", "length",
    }
    # The fake analysis lists Python, FastAPI and Go as ATS keywords; the job
    # description only says Python and FastAPI, so Go is dropped, not counted.
    keywords = next(c for c in body["checks"] if c["name"] == "keywords")
    assert keywords["found"] == ["Python", "FastAPI"]
    assert keywords["missing"] == []
    assert client.get(f"/api/tailored/{tailored['id']}/ats", headers=auth_header(USER_B)).status_code == 404


def _missing(body, name):
    return next(c for c in body["checks"] if c["name"] == name)["missing"]
