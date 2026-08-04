from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import ApplicationStatus


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
    name: str
    is_default: bool = False
    content: ResumeContent


class ResumeUpdate(BaseModel):
    name: str | None = None
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
    company: str
    role: str
    status: ApplicationStatus = ApplicationStatus.saved
    job_description: str | None = None
    job_url: str | None = None
    notes: str | None = None


class ApplicationUpdate(BaseModel):
    company: str | None = None
    role: str | None = None
    status: ApplicationStatus | None = None
    job_description: str | None = None
    job_url: str | None = None
    notes: str | None = None


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
