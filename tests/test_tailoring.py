import pytest

from app.schemas import MatchAnalysis, ResumeContent
from app.services.tailoring import TailoringResult, render_markdown


@pytest.fixture()
def fake_tailoring(monkeypatch, sample_resume_content):
    """Replace the Claude call with a deterministic fake."""

    def _fake(resume_content, job_description, company, role):
        content = ResumeContent.model_validate(resume_content)
        content.summary = f"Engineer targeting {role} at {company}."
        return TailoringResult(
            tailored_resume=content,
            match_analysis=MatchAnalysis(
                match_score=82,
                matched_keywords=["Python", "FastAPI"],
                missing_keywords=["Kubernetes"],
                recommendations=["Highlight the Job Tracker project."],
            ),
        )

    monkeypatch.setattr("app.routers.tailoring.tailoring.tailor_resume", _fake)


def test_tailor_uses_default_resume(client, make_application, make_resume, fake_tailoring):
    make_resume()
    app_data = make_application()

    resp = client.post(f"/api/applications/{app_data['id']}/tailor", json={})
    assert resp.status_code == 201, resp.text
    tailored = resp.json()
    assert tailored["match_analysis"]["match_score"] == 82
    assert "Backend Engineer at Globex" in tailored["content"]["summary"]
    assert tailored["markdown"].startswith("# Om Patel")


def test_tailor_with_explicit_resume(client, make_application, make_resume, fake_tailoring):
    resume = make_resume(is_default=False)
    app_data = make_application()

    resp = client.post(
        f"/api/applications/{app_data['id']}/tailor",
        json={"resume_id": resume["id"]},
    )
    assert resp.status_code == 201
    assert resp.json()["resume_id"] == resume["id"]


def test_tailor_requires_job_description(client, make_application, make_resume, fake_tailoring):
    make_resume()
    app_data = make_application(job_description=None)

    resp = client.post(f"/api/applications/{app_data['id']}/tailor", json={})
    assert resp.status_code == 400


def test_tailor_without_default_resume(client, make_application, fake_tailoring):
    app_data = make_application()
    resp = client.post(f"/api/applications/{app_data['id']}/tailor", json={})
    assert resp.status_code == 400


def test_list_and_download_tailored(client, make_application, make_resume, fake_tailoring):
    make_resume()
    app_data = make_application()
    client.post(f"/api/applications/{app_data['id']}/tailor", json={})
    client.post(f"/api/applications/{app_data['id']}/tailor", json={})

    resp = client.get(f"/api/applications/{app_data['id']}/tailored")
    assert resp.status_code == 200
    tailored_list = resp.json()
    assert len(tailored_list) == 2

    md = client.get(f"/api/tailored/{tailored_list[0]['id']}/markdown")
    assert md.status_code == 200
    assert md.headers["content-type"].startswith("text/markdown")
    assert "## Experience" in md.text

    # Application card reflects the tailored count
    resp = client.get(f"/api/applications/{app_data['id']}")
    assert resp.json()["tailored_count"] == 2


def test_tailoring_failure_returns_502(client, make_application, make_resume, monkeypatch):
    make_resume()
    app_data = make_application()

    def _boom(**kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("app.routers.tailoring.tailoring.tailor_resume", _boom)
    resp = client.post(f"/api/applications/{app_data['id']}/tailor", json={})
    assert resp.status_code == 502


def test_render_markdown_full_document(sample_resume_content):
    md = render_markdown(ResumeContent.model_validate(sample_resume_content))
    assert md.startswith("# Om Patel")
    for section in ("## Summary", "## Skills", "## Experience", "## Projects", "## Education"):
        assert section in md
    assert "- Built internal tooling in Python." in md


def test_missing_api_key_raises_friendly_error(monkeypatch, sample_resume_content):
    from app.config import settings
    from app.services.tailoring import tailor_resume

    monkeypatch.setattr(settings, "llm_provider", "claude")
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    with pytest.raises(RuntimeError, match="Anthropic API key is not configured"):
        tailor_resume(
            resume_content=sample_resume_content,
            job_description="Python role",
            company="Globex",
            role="Backend Engineer",
        )
