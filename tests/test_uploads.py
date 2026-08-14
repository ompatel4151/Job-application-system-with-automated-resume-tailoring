"""Uploading a resume as a PDF or image."""

import io

import pytest

from app.config import settings
from app.schemas import ResumeContent
from app.services import extraction

PARSED = ResumeContent(
    full_name="Om Patel",
    contact="om@example.com",
    summary="Backend engineer.",
    skills=["Python", "FastAPI"],
)

# Smallest thing pypdf will read back as a one-page document.
MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def fake_parse(monkeypatch):
    """Record how extraction was routed, without calling a model."""
    calls = {}

    def claude(blocks):
        calls["provider"] = "claude"
        calls["blocks"] = blocks
        return PARSED.model_copy(deep=True)

    def groq(content, *, model, strict):
        calls["provider"] = "groq"
        calls["content"] = content
        calls["model"] = model
        calls["strict"] = strict
        return PARSED.model_copy(deep=True)

    monkeypatch.setattr(extraction, "_parse_with_claude", claude)
    monkeypatch.setattr(extraction, "_parse_with_groq", groq)
    monkeypatch.setattr(settings, "llm_provider", "claude")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    return calls


# ---------- validation ----------

def test_rejects_unsupported_type():
    with pytest.raises(extraction.UnsupportedFileType, match="Unsupported file type"):
        extraction.extract_resume_content(b"Doc", "application/msword")


def test_rejects_empty_file():
    with pytest.raises(extraction.UnsupportedFileType, match="empty"):
        extraction.extract_resume_content(b"", "application/pdf")


def test_rejects_oversized_file():
    oversized = b"x" * (extraction.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(extraction.FileTooLarge, match="limit is 10MB"):
        extraction.extract_resume_content(oversized, "image/jpeg")


# ---------- routing ----------

def test_text_pdf_is_read_locally_and_sent_as_text(monkeypatch, fake_parse):
    """A PDF with a text layer should not burn vision tokens."""
    monkeypatch.setattr(extraction, "pdf_text", lambda data: "RESUME TEXT " * 40)

    result = extraction.extract_resume_content(MINIMAL_PDF, "application/pdf")

    assert result.full_name == "Om Patel"
    assert fake_parse["provider"] == "claude"
    assert [b["type"] for b in fake_parse["blocks"]] == ["text"]
    assert "RESUME TEXT" in fake_parse["blocks"][0]["text"]


def test_scanned_pdf_falls_back_to_document_block(monkeypatch, fake_parse):
    monkeypatch.setattr(extraction, "pdf_text", lambda data: "")

    extraction.extract_resume_content(MINIMAL_PDF, "application/pdf")

    types = [b["type"] for b in fake_parse["blocks"]]
    assert "document" in types


def test_image_is_sent_as_image_block(fake_parse):
    extraction.extract_resume_content(PNG_BYTES, "image/png")

    image_block = [b for b in fake_parse["blocks"] if b["type"] == "image"][0]
    assert image_block["source"]["media_type"] == "image/png"


def test_groq_text_pdf_uses_strict_schema(monkeypatch, fake_parse):
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test")
    monkeypatch.setattr(extraction, "pdf_text", lambda data: "RESUME TEXT " * 40)

    extraction.extract_resume_content(MINIMAL_PDF, "application/pdf")

    assert fake_parse["provider"] == "groq"
    assert fake_parse["strict"] is True
    assert fake_parse["model"] == settings.groq_model


def test_groq_image_uses_vision_model_without_strict_schema(monkeypatch, fake_parse):
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test")

    extraction.extract_resume_content(PNG_BYTES, "image/png")

    assert fake_parse["model"] == settings.groq_vision_model
    assert fake_parse["strict"] is False


def test_groq_cannot_read_scanned_pdfs(monkeypatch, fake_parse):
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test")
    monkeypatch.setattr(extraction, "pdf_text", lambda data: "")

    with pytest.raises(RuntimeError, match="no readable text"):
        extraction.extract_resume_content(MINIMAL_PDF, "application/pdf")


def test_pdf_text_survives_a_corrupt_file():
    """A broken PDF should route to vision, not raise."""
    assert extraction.pdf_text(b"not really a pdf") == ""


# ---------- endpoint ----------

def test_upload_returns_parsed_content(client, fake_parse):
    response = client.post(
        "/api/resumes/parse",
        files={"file": ("resume.png", io.BytesIO(PNG_BYTES), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Om Patel"
    # Parsing must not persist anything; the user reviews it first.
    assert client.get("/api/resumes").json() == []


def test_upload_falls_back_to_extension_when_type_is_generic(client, fake_parse):
    """Browsers sometimes send application/octet-stream for dropped files."""
    response = client.post(
        "/api/resumes/parse",
        files={"file": ("resume.png", io.BytesIO(PNG_BYTES), "application/octet-stream")},
    )
    assert response.status_code == 200
    assert [b["type"] for b in fake_parse["blocks"]] == ["text", "image"]


def test_upload_rejects_unsupported_type(client, fake_parse):
    response = client.post(
        "/api/resumes/parse",
        files={"file": ("resume.docx", io.BytesIO(b"PK\x03\x04"), "application/msword")},
    )
    assert response.status_code == 415


def test_upload_rejects_oversized_file(client, fake_parse):
    oversized = io.BytesIO(b"x" * (extraction.MAX_UPLOAD_BYTES + 1024))
    response = client.post(
        "/api/resumes/parse",
        files={"file": ("big.png", oversized, "image/png")},
    )
    assert response.status_code == 413


def test_upload_surfaces_provider_errors(client, monkeypatch, fake_parse):
    def boom(*args, **kwargs):
        raise RuntimeError("Groq rate limit reached.")

    monkeypatch.setattr(extraction, "_parse_with_claude", boom)
    response = client.post(
        "/api/resumes/parse",
        files={"file": ("resume.png", io.BytesIO(PNG_BYTES), "image/png")},
    )
    assert response.status_code == 502
    assert "rate limit" in response.json()["detail"]
