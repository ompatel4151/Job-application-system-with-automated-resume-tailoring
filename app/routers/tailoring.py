from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.schemas import TailoredResumeOut, TailorRequest
from app.services import tailoring

router = APIRouter(prefix="/api", tags=["tailoring"])


@router.post(
    "/applications/{application_id}/tailor",
    response_model=TailoredResumeOut,
    status_code=201,
)
def tailor_for_application(
    application_id: int, payload: TailorRequest, db: Session = Depends(get_db)
):
    application = db.get(models.Application, application_id)
    if not application:
        raise HTTPException(404, "Application not found")
    if not application.job_description:
        raise HTTPException(
            400, "Application has no job description to tailor against"
        )

    if payload.resume_id is not None:
        resume = db.get(models.Resume, payload.resume_id)
        if not resume:
            raise HTTPException(404, "Resume not found")
    else:
        resume = (
            db.query(models.Resume)
            .filter(models.Resume.is_default.is_(True))
            .first()
        )
        if not resume:
            raise HTTPException(
                400, "No resume_id given and no default resume configured"
            )

    try:
        result = tailoring.tailor_resume(
            resume_content=resume.content,
            job_description=application.job_description,
            company=application.company,
            role=application.role,
        )
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc

    tailored = models.TailoredResume(
        application_id=application.id,
        resume_id=resume.id,
        content=result.tailored_resume.model_dump(),
        match_analysis=result.match_analysis.model_dump(),
        markdown=tailoring.render_markdown(result.tailored_resume),
    )
    db.add(tailored)
    db.commit()
    db.refresh(tailored)
    return tailored


@router.get(
    "/applications/{application_id}/tailored",
    response_model=list[TailoredResumeOut],
)
def list_tailored(application_id: int, db: Session = Depends(get_db)):
    application = db.get(models.Application, application_id)
    if not application:
        raise HTTPException(404, "Application not found")
    return (
        db.query(models.TailoredResume)
        .filter(models.TailoredResume.application_id == application_id)
        .order_by(models.TailoredResume.created_at.desc())
        .all()
    )


@router.get("/tailored/{tailored_id}", response_model=TailoredResumeOut)
def get_tailored(tailored_id: int, db: Session = Depends(get_db)):
    tailored = db.get(models.TailoredResume, tailored_id)
    if not tailored:
        raise HTTPException(404, "Tailored resume not found")
    return tailored


@router.get("/tailored/{tailored_id}/markdown", response_class=PlainTextResponse)
def download_markdown(tailored_id: int, db: Session = Depends(get_db)):
    tailored = db.get(models.TailoredResume, tailored_id)
    if not tailored:
        raise HTTPException(404, "Tailored resume not found")
    return PlainTextResponse(
        tailored.markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f"attachment; filename=resume-{tailored_id}.md"
        },
    )
