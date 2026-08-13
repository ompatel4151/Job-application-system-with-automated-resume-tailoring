from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.models import utcnow
from app.schemas import ResumeCreate, ResumeOut, ResumeUpdate

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


def _clear_default(db: Session) -> None:
    # A bulk UPDATE bypasses the ORM's onupdate hook, so bump updated_at by hand
    # — otherwise a demoted resume keeps a stale timestamp.
    db.query(models.Resume).filter(models.Resume.is_default.is_(True)).update(
        {"is_default": False, "updated_at": utcnow()}, synchronize_session=False
    )


@router.post("", response_model=ResumeOut, status_code=201)
def create_resume(payload: ResumeCreate, db: Session = Depends(get_db)):
    if payload.is_default:
        _clear_default(db)
    resume = models.Resume(
        name=payload.name,
        is_default=payload.is_default,
        content=payload.content.model_dump(),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


@router.get("", response_model=list[ResumeOut])
def list_resumes(db: Session = Depends(get_db)):
    return db.query(models.Resume).order_by(models.Resume.created_at.desc()).all()


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: int, db: Session = Depends(get_db)):
    resume = db.get(models.Resume, resume_id)
    if not resume:
        raise HTTPException(404, "Resume not found")
    return resume


@router.put("/{resume_id}", response_model=ResumeOut)
def update_resume(resume_id: int, payload: ResumeUpdate, db: Session = Depends(get_db)):
    resume = db.get(models.Resume, resume_id)
    if not resume:
        raise HTTPException(404, "Resume not found")
    if payload.name is not None:
        resume.name = payload.name
    if payload.is_default is not None:
        if payload.is_default:
            _clear_default(db)
        resume.is_default = payload.is_default
    if payload.content is not None:
        resume.content = payload.content.model_dump()
    db.commit()
    db.refresh(resume)
    return resume


@router.delete("/{resume_id}", status_code=204)
def delete_resume(resume_id: int, db: Session = Depends(get_db)):
    resume = db.get(models.Resume, resume_id)
    if not resume:
        raise HTTPException(404, "Resume not found")
    db.delete(resume)
    db.commit()
