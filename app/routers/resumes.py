from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.models import utcnow
from app.schemas import ResumeContent, ResumeCreate, ResumeOut, ResumeUpdate
from app.services import extraction

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


_EXTENSION_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _media_type(upload: UploadFile) -> str:
    """Trust the browser's content type, falling back to the extension.

    Some browsers send application/octet-stream for a drag-and-dropped file.
    """
    declared = (upload.content_type or "").split(";")[0].strip().lower()
    if declared in extraction.SUPPORTED_MEDIA_TYPES:
        return declared
    filename = (upload.filename or "").lower()
    for suffix, media_type in _EXTENSION_TYPES.items():
        if filename.endswith(suffix):
            return media_type
    return declared or "application/octet-stream"


async def _read_capped(upload: UploadFile) -> bytes:
    """Read the upload, stopping one byte past the limit.

    Reading in chunks means an oversized upload is rejected without pulling the
    whole thing into memory first.
    """
    limit = extraction.MAX_UPLOAD_BYTES
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(64 * 1024):
        total += len(chunk)
        chunks.append(chunk)
        if total > limit:
            raise HTTPException(
                413, f"File is larger than the {limit // 1_000_000}MB limit."
            )
    return b"".join(chunks)


@router.post("/parse", response_model=ResumeContent)
async def parse_resume_file(file: UploadFile = File(...)):
    """Read an uploaded PDF or image into structured resume content.

    Deliberately does not save: extraction can misread a layout, so the
    dashboard shows the result for review and the user saves it themselves
    through the normal create endpoint.
    """
    data = await _read_capped(file)
    try:
        return extraction.extract_resume_content(data, _media_type(file))
    except extraction.UnsupportedFileType as exc:
        raise HTTPException(415, str(exc)) from exc
    except extraction.FileTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


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
