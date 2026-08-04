import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


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
