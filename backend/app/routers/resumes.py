from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app import idempotency, models, observability
from app.auth import CurrentUser
from app.config import settings
from app.database import get_db, get_owned
from app.idempotency import IdempotencyKeyHeader
from app.models import utcnow
from app.pagination import DEFAULT_LIMIT, Cursor, Limit, paginate
from app.schemas import ResumeContent, ResumeCreate, ResumeOut, ResumePage, ResumeUpdate
from app.services import extraction

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


def _clear_default(db: Session, user) -> None:
    # A bulk UPDATE bypasses the ORM's onupdate hook, so bump updated_at by hand.
    # Without this, a demoted resume keeps a stale timestamp.
    db.query(models.Resume).filter(
        models.Resume.user_id == user, models.Resume.is_default.is_(True)
    ).update(
        {"is_default": False, "updated_at": utcnow()}, synchronize_session=False
    )


@router.post("", response_model=ResumeOut, status_code=201)
def create_resume(
    payload: ResumeCreate,
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

    if payload.is_default:
        _clear_default(db, user)
    resume = models.Resume(
        user_id=user,
        name=payload.name,
        is_default=payload.is_default,
        content=payload.content.model_dump(),
    )
    db.add(resume)
    db.flush()
    out = ResumeOut.model_validate(resume)
    idempotency.save(row, 201, out.model_dump(mode="json"))
    db.commit()
    return out


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
        # Includes local PDF text extraction, which may skip the LLM entirely.
        with observability.llm_timer(settings.resolve_provider(), "parse"):
            return extraction.extract_resume_content(data, _media_type(file))
    except extraction.UnsupportedFileType as exc:
        raise HTTPException(415, str(exc)) from exc
    except extraction.FileTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("", response_model=ResumePage)
def list_resumes(
    user: CurrentUser,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    db: Session = Depends(get_db),
):
    """Newest first."""
    query = db.query(models.Resume).filter(models.Resume.user_id == user)
    resumes, next_cursor = paginate(query, models.Resume.created_at, models.Resume.id, limit, cursor)
    return ResumePage(
        items=[ResumeOut.model_validate(r) for r in resumes], next_cursor=next_cursor
    )


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: int, user: CurrentUser, db: Session = Depends(get_db)):
    return get_owned(db, models.Resume, resume_id, user, "Resume")


@router.put("/{resume_id}", response_model=ResumeOut)
def update_resume(
    resume_id: int, payload: ResumeUpdate, user: CurrentUser, db: Session = Depends(get_db)
):
    resume = get_owned(db, models.Resume, resume_id, user, "Resume")
    if payload.name is not None:
        resume.name = payload.name
    if payload.is_default is not None:
        if payload.is_default:
            _clear_default(db, user)
        resume.is_default = payload.is_default
    if payload.content is not None:
        resume.content = payload.content.model_dump()
    db.commit()
    db.refresh(resume)
    return resume


@router.delete("/{resume_id}", status_code=204)
def delete_resume(resume_id: int, user: CurrentUser, db: Session = Depends(get_db)):
    resume = get_owned(db, models.Resume, resume_id, user, "Resume")
    db.delete(resume)
    db.commit()
