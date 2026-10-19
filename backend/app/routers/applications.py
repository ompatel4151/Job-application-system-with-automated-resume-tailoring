from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import idempotency, models
from app.auth import CurrentUser
from app.database import get_db, get_owned
from app.idempotency import IdempotencyKeyHeader
from app.models import ApplicationStatus, utcnow
from app.pagination import DEFAULT_LIMIT, Cursor, Limit, paginate
from app.schemas import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationPage,
    ApplicationUpdate,
    PipelineStats,
)

router = APIRouter(prefix="/api/applications", tags=["applications"])

# Every stage that implies the application has actually been submitted. Reaching
# any of these for the first time is what stamps applied_at; moving straight to
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
def create_application(
    payload: ApplicationCreate,
    request: Request,
    user: CurrentUser,
    idempotency_key: IdempotencyKeyHeader = None,
    db: Session = Depends(get_db),
):
    row, replay = idempotency.claim(
        db, user, idempotency_key, request.method, request.url.path,
        payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay

    application = models.Application(**payload.model_dump(), user_id=user)
    if application.status in APPLIED_STAGES:
        application.applied_at = utcnow()
    db.add(application)
    db.flush()  # assigns the id; the commit happens once, below
    out = _to_out(application)
    idempotency.save(row, 201, out.model_dump(mode="json"))
    db.commit()
    return out


@router.get("", response_model=ApplicationPage)
def list_applications(
    user: CurrentUser,
    status: ApplicationStatus | None = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    db: Session = Depends(get_db),
):
    """Most recently updated first."""
    query = db.query(models.Application).filter(models.Application.user_id == user)
    if status is not None:
        query = query.filter(models.Application.status == status)
    apps, next_cursor = paginate(
        query, models.Application.updated_at, models.Application.id, limit, cursor
    )
    counts = _tailored_counts(db, [a.id for a in apps])
    return ApplicationPage(
        items=[_to_out(a, counts.get(a.id, 0)) for a in apps], next_cursor=next_cursor
    )


@router.get("/stats", response_model=PipelineStats)
def pipeline_stats(user: CurrentUser, db: Session = Depends(get_db)):
    rows = (
        db.query(models.Application.status, func.count(models.Application.id))
        .filter(models.Application.user_id == user)
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
def get_application(application_id: int, user: CurrentUser, db: Session = Depends(get_db)):
    application = get_owned(db, models.Application, application_id, user, "Application")
    return _to_out(application, _tailored_count(db, application_id))


@router.patch("/{application_id}", response_model=ApplicationOut)
def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    application = get_owned(db, models.Application, application_id, user, "Application")
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
def delete_application(application_id: int, user: CurrentUser, db: Session = Depends(get_db)):
    application = get_owned(db, models.Application, application_id, user, "Application")
    db.delete(application)
    db.commit()
