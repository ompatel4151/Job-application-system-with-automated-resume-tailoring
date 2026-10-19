import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth, ratelimit
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.schemas import MatchAnalysis, ResumeContent
from app.services.tailoring import TailoringResult
from tests.tokens import SIGNING_KEY, SUPABASE_URL, USER_A, auth_header

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _test_auth(monkeypatch):
    """Point token verification at the test key, never at the network."""
    monkeypatch.setattr(settings, "supabase_url", SUPABASE_URL)
    monkeypatch.setattr(auth, "_signing_key", lambda token: SIGNING_KEY.public_key())
    # The test database is built below with create_all; don't migrate the dev DB.
    monkeypatch.setattr("app.main.migrate", lambda: None)


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """Rate limiting stays on in every test, but each test starts with full buckets."""
    ratelimit.reset()


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, headers=auth_header(USER_A)) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db(client):
    """A session on the same test database the client uses, for direct setup."""
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture()
def sample_resume_content():
    return {
        "full_name": "Om Patel",
        "contact": "om@example.com | github.com/ompatel",
        "summary": "Software engineer with full-stack experience.",
        "skills": ["Python", "FastAPI", "SQL", "JavaScript"],
        "experience": [
            {
                "company": "Acme Corp",
                "title": "Software Engineer Intern",
                "dates": "Summer 2025",
                "bullets": ["Built internal tooling in Python."],
            }
        ],
        "projects": [
            {
                "name": "Job Tracker",
                "description": "Full-stack application tracker",
                "technologies": ["FastAPI", "SQLite"],
                "bullets": ["Designed REST API with 15+ endpoints."],
            }
        ],
        "education": [
            {
                "school": "State University",
                "degree": "BS Computer Science",
                "dates": "2022-2026",
                "details": ["GPA 3.8"],
            }
        ],
    }


@pytest.fixture()
def make_application(client):
    def _make(**overrides):
        payload = {
            "company": "Globex",
            "role": "Backend Engineer",
            "job_description": "We need Python and FastAPI experience.",
            **overrides,
        }
        resp = client.post("/api/applications", json=payload)
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make


@pytest.fixture()
def fake_tailoring(monkeypatch, sample_resume_content):
    """Replace the LLM call with a deterministic fake, so no test spends tokens."""

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


@pytest.fixture()
def make_resume(client, sample_resume_content):
    def _make(**overrides):
        payload = {
            "name": "Base resume",
            "is_default": True,
            "content": sample_resume_content,
            **overrides,
        }
        resp = client.post("/api/resumes", json=payload)
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make
