"""Probe suspected weaknesses against an in-memory DB. Audit evidence only."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def override():
    db = Session()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override
c = TestClient(app, raise_server_exceptions=False)

body = {"company": "Acme", "role": "SWE", "job_description": "Python"}
r1 = c.post("/api/applications", json=body)
r2 = c.post("/api/applications", json=body)
print("1. same POST twice ->", r1.status_code, r2.status_code,
      "| rows now:", len(c.get("/api/applications").json()))

r = c.post("/api/applications", json={"company": "", "role": ""})
print("2. empty company+role ->", r.status_code)

r = c.post("/api/applications", json={"company": "X" * 300, "role": "SWE"})
print("3. 300-char company (column is VARCHAR(200)) on SQLite ->", r.status_code)

r = c.post("/api/applications", json={"company": "A", "role": "B", "job_url": "javascript:alert(1)"})
print("4. job_url='javascript:alert(1)' ->", r.status_code)

app_id = r1.json()["id"]
r = c.patch(f"/api/applications/{app_id}", json={"company": None})
print("5. PATCH company=null ->", r.status_code, r.text[:60])

r = c.post("/api/applications", json={"company": "A", "role": "B", "job_description": "x" * 2_000_000})
print("6. 2,000,000-char job_description ->", r.status_code)

print("7. error body shapes:")
print("   404:", c.get("/api/applications/99999").json())
print("   422 detail type:", type(c.post("/api/applications", json={}).json()["detail"]).__name__)
