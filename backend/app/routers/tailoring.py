from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from app import idempotency, models, observability
from app.auth import CurrentUser
from app.config import settings
from app.database import get_db, get_owned
from app.idempotency import IdempotencyKeyHeader
from app.pagination import DEFAULT_LIMIT, Cursor, Limit, paginate
from app.schemas import (
    AtsReport,
    MatchAnalysis,
    ResumeContent,
    TailoredResumeOut,
    TailoredResumePage,
    TailorRequest,
)
from app.services import ats, pdf, tailoring

router = APIRouter(prefix="/api", tags=["tailoring"])


@router.post(
    "/applications/{application_id}/tailor",
    response_model=TailoredResumeOut,
    status_code=201,
)
def tailor_for_application(
    application_id: int,
    payload: TailorRequest,
    request: Request,
    user: CurrentUser,
    idempotency_key: IdempotencyKeyHeader = None,
    db: Session = Depends(get_db),
):
    # Claim first: a retried tailor must not pay for a second LLM call.
    row, replay = idempotency.claim(
        db, user, idempotency_key, request.method, request.url.path,
        payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay

    application = get_owned(db, models.Application, application_id, user, "Application")
    if not application.job_description:
        raise HTTPException(
            400, "Application has no job description to tailor against"
        )

    if payload.resume_id is not None:
        resume = get_owned(db, models.Resume, payload.resume_id, user, "Resume")
    else:
        # Order explicitly so the choice is deterministic if data ever ends up
        # with more than one default.
        resume = (
            db.query(models.Resume)
            .filter(models.Resume.user_id == user, models.Resume.is_default.is_(True))
            .order_by(models.Resume.id)
            .first()
        )
        if not resume:
            raise HTTPException(
                400, "No resume_id given and no default resume configured"
            )

    try:
        with observability.llm_timer(settings.resolve_provider(), "tailor"):
            result = tailoring.tailor_resume(
                resume_content=resume.content,
                job_description=application.job_description,
                company=application.company,
                role=application.role,
            )
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc

    tailored = models.TailoredResume(
        user_id=user,
        application_id=application.id,
        resume_id=resume.id,
        content=result.tailored_resume.model_dump(),
        match_analysis=result.match_analysis.model_dump(),
        markdown=tailoring.render_markdown(result.tailored_resume),
    )
    db.add(tailored)
    db.flush()
    out = TailoredResumeOut.model_validate(tailored)
    idempotency.save(row, 201, out.model_dump(mode="json"))
    db.commit()
    return out


@router.get("/applications/{application_id}/tailored", response_model=TailoredResumePage)
def list_tailored(
    application_id: int,
    user: CurrentUser,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    db: Session = Depends(get_db),
):
    """Newest first."""
    get_owned(db, models.Application, application_id, user, "Application")
    query = db.query(models.TailoredResume).filter(
        models.TailoredResume.application_id == application_id
    )
    rows, next_cursor = paginate(
        query, models.TailoredResume.created_at, models.TailoredResume.id, limit, cursor
    )
    return TailoredResumePage(
        items=[TailoredResumeOut.model_validate(t) for t in rows], next_cursor=next_cursor
    )


@router.get("/tailored/{tailored_id}", response_model=TailoredResumeOut)
def get_tailored(tailored_id: int, user: CurrentUser, db: Session = Depends(get_db)):
    return get_owned(db, models.TailoredResume, tailored_id, user, "Tailored resume")


@router.get("/tailored/{tailored_id}/markdown", response_class=PlainTextResponse)
def download_markdown(tailored_id: int, user: CurrentUser, db: Session = Depends(get_db)):
    tailored = get_owned(db, models.TailoredResume, tailored_id, user, "Tailored resume")
    return PlainTextResponse(
        tailored.markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f"attachment; filename=resume-{tailored_id}.md"
        },
    )


@router.get("/tailored/{tailored_id}/pdf", response_class=Response)
def download_pdf(tailored_id: int, user: CurrentUser, db: Session = Depends(get_db)):
    tailored = get_owned(db, models.TailoredResume, tailored_id, user, "Tailored resume")
    return Response(
        pdf.render_pdf(ResumeContent.model_validate(tailored.content)),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=resume-{tailored_id}.pdf"},
    )


@router.get("/tailored/{tailored_id}/ats", response_model=AtsReport)
def ats_report(tailored_id: int, user: CurrentUser, db: Session = Depends(get_db)):
    """Rule-based ATS readiness of this tailored resume, computed on request
    (no LLM call, nothing stored)."""
    tailored = get_owned(db, models.TailoredResume, tailored_id, user, "Tailored resume")
    analysis = MatchAnalysis.model_validate(tailored.match_analysis)
    return ats.ats_check(
        ResumeContent.model_validate(tailored.content),
        analysis.matched_keywords + analysis.missing_keywords,
    )
