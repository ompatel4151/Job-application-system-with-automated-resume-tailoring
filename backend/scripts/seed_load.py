"""Seed a synthetic dataset for the local load test (milestone 6).

Synthetic on purpose: 2,000 applications with 100 tailored resumes each is far
more than one person would create. It's sized so query costs are visible.
Fixed seed and fixed timestamps, so every run creates identical data.

All rows belong to one user, LOAD_USER (the `sub` of the token from
scripts/dev_jwks.py), because every list is now scoped to the caller.

WARNING: drops the whole public schema in DATABASE_URL, then migrates.
Local use only.

Usage (from backend/):
  DATABASE_URL=postgresql://app:app@localhost:5432/jobtracker \
    PYTHONPATH=. ../.venv/bin/python scripts/seed_load.py
"""

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, text

from app import models
from app.database import engine, migrate

APPLICATIONS = 2_000
TAILORED_PER_APPLICATION = 100
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
CONTENT = {"full_name": "Test User", "summary": "Backend engineer.", "skills": ["Python"]}
ANALYSIS = {"match_score": 70, "matched_keywords": ["Python"], "missing_keywords": []}
LOAD_USER = "33333333-3333-4333-8333-333333333333"


def main() -> None:
    if not engine.url.drivername.startswith("postgresql"):
        raise SystemExit("Refusing to run: point DATABASE_URL at the local Postgres.")
    rng = random.Random(42)
    statuses = list(models.ApplicationStatus)

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    migrate()

    with engine.begin() as conn:
        conn.execute(
            insert(models.Resume),
            [{"id": 1, "user_id": LOAD_USER, "name": "Base", "is_default": True,
              "content": CONTENT, "created_at": T0, "updated_at": T0}],
        )
        conn.execute(
            insert(models.Application),
            [
                {
                    "id": i,
                    "user_id": LOAD_USER,
                    "company": f"Company {i}",
                    "role": "Software Engineer",
                    "status": rng.choice(statuses),
                    "job_description": "Python, FastAPI, Postgres.",
                    "created_at": T0 + timedelta(minutes=i),
                    "updated_at": T0 + timedelta(minutes=i),
                }
                for i in range(1, APPLICATIONS + 1)
            ],
        )
        rows = [
            {
                "user_id": LOAD_USER,
                "application_id": app_id,
                "resume_id": 1,
                "content": CONTENT,
                "match_analysis": ANALYSIS,
                "markdown": "# Test User\n",
                "created_at": T0 + timedelta(seconds=n),
            }
            for n, app_id in enumerate(
                a for a in range(1, APPLICATIONS + 1) for _ in range(TAILORED_PER_APPLICATION)
            )
        ]
        # Shuffle so one application's rows are spread across the table, like
        # rows that arrived over time, not stored next to each other.
        rng.shuffle(rows)
        conn.execute(insert(models.TailoredResume), rows)

        # Explicit ids don't advance the id sequences; move them past the data.
        for table in ("resumes", "applications", "tailored_resumes"):
            conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"(SELECT max(id) FROM {table}))"
            ))
        conn.execute(text("ANALYZE"))  # fresh planner statistics

    print(f"Seeded {APPLICATIONS} applications, "
          f"{APPLICATIONS * TAILORED_PER_APPLICATION} tailored resumes.")


if __name__ == "__main__":
    main()
