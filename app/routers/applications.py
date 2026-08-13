from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.models import ApplicationStatus, utcnow
from app.schemas import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationUpdate,
    PipelineStats,
)

router = APIRouter(prefix="/api/applications", tags=["applications"])

# Every stage that implies the application has actually been submitted. Reaching
# any of these for the first time is what stamps applied_at — moving straight to
# "interview" still means you applied.
APPLIED_STAGES = frozenset(
    {
        ApplicationStatus.applied,
        ApplicationStatus.screening,
        ApplicationStatus.interview,
        ApplicationStatus.offer,
    }
)


def _to_out(application: models.Application, tailored_count: int = 0) -> ApplicationOut:
    out = ApplicationOut.model_validate(application)
    out.tailored_count = tailored_count
    return out


def _tailored_counts(db: Session, application_ids: list[int]) -> dict[int, int]:
    """Tailored-resume counts for many applications in one query (avoids N+1)."""
    if not application_ids:
        return {}
    rows = (
        db.query(
            models.TailoredResume.application_id,
            func.count(models.TailoredResume.id),
        )
        .filter(models.TailoredResume.application_id.in_(application_ids))
        .group_by(models.TailoredResume.application_id)
        .all()
    )
    return {application_id: count for application_id, count in rows}


def _tailored_count(db: Session, application_id: int) -> int:
    return (
        db.query(func.count(models.TailoredResume.id))
        .filter(models.TailoredResume.application_id == application_id)
        .scalar()
        or 0
    )


@router.post("", response_model=ApplicationOut, status_code=201)
def create_application(payload: ApplicationCreate, db: Session = Depends(get_db)):
    application = models.Application(**payload.model_dump())
    if application.status in APPLIED_STAGES:
        application.applied_at = utcnow()
    db.add(application)
    db.commit()
    db.refresh(application)
    return _to_out(application)


@router.get("", response_model=list[ApplicationOut])
def list_applications(
    status: ApplicationStatus | None = None, db: Session = Depends(get_db)
):
    query = db.query(models.Application)
    if status is not None:
        query = query.filter(models.Application.status == status)
    apps = query.order_by(models.Application.updated_at.desc()).all()
    counts = _tailored_counts(db, [a.id for a in apps])
    return [_to_out(a, counts.get(a.id, 0)) for a in apps]


@router.get("/stats", response_model=PipelineStats)
def pipeline_stats(db: Session = Depends(get_db)):
    rows = (
        db.query(models.Application.status, func.count(models.Application.id))
        .group_by(models.Application.status)
        .all()
    )
    by_status = {s.value: 0 for s in ApplicationStatus}
    total = 0
    for status, count in rows:
        by_status[status.value] = count
        total += count
    return PipelineStats(total=total, by_status=by_status)


@router.get("/{application_id}", response_model=ApplicationOut)
def get_application(application_id: int, db: Session = Depends(get_db)):
    application = db.get(models.Application, application_id)
    if not application:
        raise HTTPException(404, "Application not found")
    return _to_out(application, _tailored_count(db, application_id))


@router.patch("/{application_id}", response_model=ApplicationOut)
def update_application(
    application_id: int, payload: ApplicationUpdate, db: Session = Depends(get_db)
):
    application = db.get(models.Application, application_id)
    if not application:
        raise HTTPException(404, "Application not found")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(application, field, value)
    # Stamp applied_at the first time the application reaches any applied stage.
    if application.status in APPLIED_STAGES and application.applied_at is None:
        application.applied_at = utcnow()
    db.commit()
    db.refresh(application)
    return _to_out(application, _tailored_count(db, application_id))


@router.delete("/{application_id}", status_code=204)
def delete_application(application_id: int, db: Session = Depends(get_db)):
    application = db.get(models.Application, application_id)
    if not application:
        raise HTTPException(404, "Application not found")
    db.delete(application)
    db.commit()
