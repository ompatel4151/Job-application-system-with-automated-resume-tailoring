"""Parse an uploaded resume file into structured resume content.

Users arrive with a PDF or a photo of their resume, not JSON. This turns
either into a :class:`ResumeContent` so the rest of the app — tailoring,
export, matching — can treat an upload exactly like a hand-entered resume.

Two routes in, picked per file:

- **Text PDFs** are read locally with pypdf and the extracted text is sent to
  the model. No vision needed, so this works on every provider and is the
  cheapest path.
- **Images, and PDFs with no extractable text** (scans, exports that are just
  a picture of a page) need vision: Claude reads the file natively, Groq uses
  its multimodal model.

Nothing is invented here either — the prompt only restructures what is on the
page, and leaves fields empty when the resume does not have them.
"""

import base64
import io
from typing import Any

import anthropic
import openai
from pydantic import ValidationError

from app.config import settings
from app.schemas import ResumeContent
from app.services.tailoring import GROQ_BASE_URL, strict_json_schema

PDF_MEDIA_TYPE = "application/pdf"
IMAGE_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}
SUPPORTED_MEDIA_TYPES = {PDF_MEDIA_TYPE} | IMAGE_MEDIA_TYPES

# Groq caps uploads at 20MB; Claude's limit is lower in practice and a resume
# has no business being large. Keeping one modest limit for both.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Enough text to be a resume rather than a scanned page's stray header.
MIN_PDF_TEXT_CHARS = 200

EXTRACTION_PROMPT = """\
You are parsing a resume into structured data.

Rules:
- Transcribe only what is actually on the page. Never invent employers,
  titles, dates, degrees, metrics, or skills.
- Preserve the candidate's own wording for bullet points. Do not rewrite,
  improve, or summarize them.
- Put the name in full_name, and email/phone/links together in contact.
- If the resume has no summary, leave it empty rather than writing one.
- Leave any section the resume does not have as an empty list.
- Classify personal or side work as projects, and employment as experience.
"""


class UnsupportedFileType(ValueError):
    """The uploaded file is not a resume format we can read."""


class FileTooLarge(ValueError):
    """The uploaded file exceeds MAX_UPLOAD_BYTES."""


def _validate(data: bytes, media_type: str) -> None:
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise UnsupportedFileType(
            f"Unsupported file type '{media_type}'. Upload a PDF, JPEG, PNG, or WebP."
        )
    if not data:
        raise UnsupportedFileType("The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise FileTooLarge(
            f"File is {len(data) / 1_000_000:.1f}MB; the limit is "
            f"{MAX_UPLOAD_BYTES // 1_000_000}MB."
        )


def pdf_text(data: bytes) -> str:
    """Pull the text layer out of a PDF, or return "" if it has none."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception:
        # A malformed or encrypted PDF is not fatal — fall back to vision.
        return ""
    return "\n\n".join(pages).strip()


def _parse_with_claude(content_blocks: list[dict[str, Any]]) -> ResumeContent:
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "Anthropic API key is not configured. Set ANTHROPIC_API_KEY in your .env file."
        )
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=8000,
            system=EXTRACTION_PROMPT,
            messages=[{"role": "user", "content": content_blocks}],
            output_format=ResumeContent,
        )
    except anthropic.AuthenticationError as exc:
        raise RuntimeError("Anthropic API key was rejected. Check ANTHROPIC_API_KEY.") from exc
    except anthropic.APIConnectionError as exc:
        raise RuntimeError("Could not reach the Anthropic API. Check your network.") from exc
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"Anthropic API error ({exc.status_code}): {exc.message}") from exc
    result = response.parsed_output
    if result is None:
        raise RuntimeError("Could not read a resume from that file.")
    return result


def _parse_with_groq(content: Any, *, model: str, strict: bool) -> ResumeContent:
    """Call Groq. Vision models only do best-effort JSON, so `strict` varies."""
    if not settings.groq_api_key:
        raise RuntimeError("Groq API key is not configured. Set GROQ_API_KEY in your .env file.")
    client = openai.OpenAI(api_key=settings.groq_api_key, base_url=GROQ_BASE_URL)

    if strict:
        response_format: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": "resume_content",
                "strict": True,
                "schema": strict_json_schema(ResumeContent),
            },
        }
        system = EXTRACTION_PROMPT
    else:
        # Best-effort mode has no schema, so the shape goes in the prompt.
        response_format = {"type": "json_object"}
        system = (
            f"{EXTRACTION_PROMPT}\n"
            "Respond with JSON matching this schema:\n"
            f"{strict_json_schema(ResumeContent)}"
        )

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=8000,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            response_format=response_format,
        )
    except openai.AuthenticationError as exc:
        raise RuntimeError("Groq API key was rejected. Check GROQ_API_KEY.") from exc
    except openai.RateLimitError as exc:
        raise RuntimeError(
            "Groq rate limit reached. The free tier allows 6,000 tokens/minute; "
            "wait a minute or raise your tier."
        ) from exc
    except openai.APIConnectionError as exc:
        raise RuntimeError("Could not reach the Groq API. Check your network.") from exc
    except openai.APIStatusError as exc:
        raise RuntimeError(f"Groq API error ({exc.status_code}): {exc.message}") from exc

    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise RuntimeError("The resume was too long to finish reading. Try a shorter file.")
    if not choice.message.content:
        raise RuntimeError("Could not read a resume from that file.")
    try:
        return ResumeContent.model_validate_json(choice.message.content)
    except ValidationError as exc:
        raise RuntimeError("Could not read a resume from that file.") from exc


def extract_resume_content(data: bytes, media_type: str) -> ResumeContent:
    """Parse an uploaded PDF or image into structured resume content."""
    _validate(data, media_type)
    provider = settings.resolve_provider()
    encoded = base64.b64encode(data).decode()

    # Text PDF: cheapest and most accurate route, and provider-agnostic.
    if media_type == PDF_MEDIA_TYPE:
        text = pdf_text(data)
        if len(text) >= MIN_PDF_TEXT_CHARS:
            prompt = f"Parse this resume:\n\n{text}"
            if provider == "groq":
                return _parse_with_groq(prompt, model=settings.groq_model, strict=True)
            return _parse_with_claude([{"type": "text", "text": prompt}])

    # Otherwise it needs eyes: an image, or a PDF that is just a picture.
    if provider == "groq":
        if media_type == PDF_MEDIA_TYPE:
            raise RuntimeError(
                "That PDF has no readable text and Groq cannot read scanned PDFs. "
                "Upload it as an image, or set ANTHROPIC_API_KEY to use Claude."
            )
        return _parse_with_groq(
            [
                {"type": "text", "text": "Parse this resume."},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{encoded}"},
                },
            ],
            model=settings.groq_vision_model,
            strict=False,
        )

    block_type = "document" if media_type == PDF_MEDIA_TYPE else "image"
    return _parse_with_claude(
        [
            {"type": "text", "text": "Parse this resume."},
            {
                "type": block_type,
                "source": {"type": "base64", "media_type": media_type, "data": encoded},
            },
        ]
    )
