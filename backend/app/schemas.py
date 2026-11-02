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
    # Exact terms from the posting that an ATS would search for (skills, tools,
    # short phrases), used by the word-for-word ATS check. Empty on resumes
    # tailored before this existed.
    ats_keywords: list[str] = Field(
        default=[],
        description="8-20 short terms copied word for word from the job description",
    )


class TailorRequest(BaseModel):
    resume_id: int | None = None


class Citation(BaseModel):
    text: str
    fact_ids: list[str]


class AgentTrace(BaseModel):
    """What agent mode did (AGENT_EXPERIMENT.md 3.3). Plain mode has none."""

    # Job requirements the candidate may not meet, e.g. no visa sponsorship.
    blockers: list[str] = []
    # Each agent-written bullet and the fact ids it cites.
    citations: list[Citation] = []
    steps: int = 0
    tool_calls: int = 0
    llm_calls: int = 0
    # Bullets the post-check rejected (each gets one retry), and those dropped.
    rejected: int = 0
    dropped: int = 0
    # Set when agent mode gave up and plain mode wrote the resume instead.
    fallback: str | None = None



class TailoredResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    resume_id: int
    content: ResumeContent
    match_analysis: MatchAnalysis
    markdown: str
    agent_trace: AgentTrace | None = None
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
    # What's present, for the keyword check.
    found: list[str] = []


class AtsReport(BaseModel):
    """A rule-based readiness check, not a prediction of any real ATS."""

    score: int
    checks: list[AtsCheck]


# ---------- Agent data: fact sheet and memories ----------

FactId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,40}$")]
FactText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Term = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class Fact(BaseModel):
    """One verified fact. Every number and tool a bullet built from it may use
    must be in `numbers` / `tools` or in the text itself."""

    model_config = ConfigDict(from_attributes=True)

    id: FactId
    text: FactText
    numbers: list[Term] = Field(default=[], max_length=30)
    tools: list[Term] = Field(default=[], max_length=60)
    context: Annotated[str, StringConstraints(max_length=500)] = ""


class FactSheet(BaseModel):
    facts: list[Fact] = Field(max_length=200)

    @field_validator("facts")
    @classmethod
    def _unique_ids(cls, facts: list[Fact]) -> list[Fact]:
        ids = [f.id for f in facts]
        if len(ids) != len(set(ids)):
            raise ValueError("fact ids must be unique")
        return facts


class FactsSaved(BaseModel):
    saved: int
    # False when Pinecone isn't configured or couldn't be reached; the facts are
    # still saved, and agent mode falls back to plain mode until they're indexed.
    indexed: bool


class MemoryCreate(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    created_at: datetime
