from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.database import Base, engine
from app.routers import applications, resumes, tailoring

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Job Application Tracker",
    description="Track job applications and generate resumes tailored to each "
    "job description with Claude.",
    version="0.1.0",
)

app.include_router(resumes.router)
app.include_router(applications.router)
app.include_router(tailoring.router)

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
