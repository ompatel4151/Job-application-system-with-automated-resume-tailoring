import re
from datetime import datetime
from typing import Annotated, Generic, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from app.models import ApplicationStatus

# Limits match the database columns, so bad input is a 422 here instead of a
# database error later. The text caps are a judgment call: real job postings
# are a few thousand characters, and every character of a job description is
# sent to the LLM (and paid for) when tailoring.
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


def _http_url(value: str) -> str:
    # Only web links: blocks javascript: and data: URLs (audit #5). A validator
    # instead of a regex pattern, so the user-facing message is readable.
    if not re.fullmatch(r"https?://\S+", value):
        raise ValueError("must be a web address starting with http:// or https://")
    return value


HttpUrl = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=500), AfterValidator(_http_url)
]
JobDescription = Annotated[str, StringConstraints(max_length=20_000)]
Notes = Annotated[str, StringConstraints(max_length=10_000)]


# ---------- Resume content (shared shape for base and tailored resumes) ----------

class ExperienceEntry(BaseModel):
    company: str
    title: str
    dates: str = ""
    bullets: list[str] = []


class ProjectEntry(BaseModel):
    name: str
    description: str = ""
    technologies: list[str] = []
    bullets: list[str] = []


class EducationEntry(BaseModel):
    school: str
    degree: str = ""
    dates: str = ""
    details: list[str] = []


class ResumeContent(BaseModel):
    full_name: str = ""
    contact: str = ""
    summary: str = ""
    skills: list[str] = []
    experience: list[ExperienceEntry] = []
    projects: list[ProjectEntry] = []
    education: list[EducationEntry] = []


# ---------- Resumes ----------

class ResumeCreate(BaseModel):
    name: ShortText
    is_default: bool = False
    content: ResumeContent


class ResumeUpdate(BaseModel):
    name: ShortText | None = None
    is_default: bool | None = None
    content: ResumeContent | None = None


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_default: bool
    content: ResumeContent
    created_at: datetime
    updated_at: datetime


# ---------- Applications ----------

class ApplicationCreate(BaseModel):
    company: ShortText
    role: ShortText
    status: ApplicationStatus = ApplicationStatus.saved
    job_description: JobDescription | None = None
    job_url: HttpUrl | None = None
    notes: Notes | None = None


class ApplicationUpdate(BaseModel):
    company: ShortText | None = None
    role: ShortText | None = None
    status: ApplicationStatus | None = None
    job_description: JobDescription | None = None
    job_url: HttpUrl | None = None
    notes: Notes | None = None

    # "| None" here means "may be omitted". For these three, an explicit null
    # would write NULL into a NOT NULL column (audit #4), so reject it.
    # Validators only run on fields the client actually sent.
    @field_validator("company", "role", "status")
    @classmethod
    def _not_null(cls, value):
        if value is None:
            raise ValueError("cannot be null; omit the field to leave it unchanged")
        return value


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company: str
    role: str
    status: ApplicationStatus
    job_description: str | None
    job_url: str | None
    notes: str | None
    applied_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tailored_count: int = 0


# ---------- Tailoring ----------

class MatchAnalysis(BaseModel):
    match_score: int = Field(description="0-100 fit score for the job")
    matched_keywords: list[str] = []
    missing_keywords: list[str] = []
    recommendations: list[str] = []


class TailorRequest(BaseModel):
    resume_id: int | None = None


class TailoredResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    resume_id: int
    content: ResumeContent
    match_analysis: MatchAnalysis
    markdown: str
    created_at: datetime


class PipelineStats(BaseModel):
    total: int
    by_status: dict[str, int]


# ---------- Pages ----------

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    # Pass back as ?cursor= for the next page; null on the last page.
    next_cursor: str | None


class ApplicationPage(Page[ApplicationOut]):
    pass


class ResumePage(Page[ResumeOut]):
    pass


class TailoredResumePage(Page[TailoredResumeOut]):
    pass


# ---------- ATS check ----------

class AtsCheck(BaseModel):
    name: str  # stable id: parse, headings, contact, keywords, numbers, length
    label: str
    passed: bool
    points: int
    max_points: int
    detail: str
    # What's absent, for the checks where that's a list (keywords, headings).
    missing: list[str] = []


class AtsReport(BaseModel):
    """A rule-based readiness check, not a prediction of any real ATS."""

    score: int
    checks: list[AtsCheck]
