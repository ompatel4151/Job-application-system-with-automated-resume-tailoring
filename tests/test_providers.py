"""Provider selection and the Groq structured-output path."""

import json

import pytest

from app.config import Settings, settings
from app.schemas import MatchAnalysis, ResumeContent
from app.services.tailoring import TailoringResult, strict_json_schema, tailor_resume


# ---------- provider resolution ----------

def test_auto_prefers_claude_when_anthropic_key_present():
    s = Settings(anthropic_api_key="sk-ant-x", groq_api_key="gsk_x")
    assert s.resolve_provider() == "claude"


def test_auto_falls_back_to_groq_when_only_groq_key_present():
    s = Settings(anthropic_api_key=None, groq_api_key="gsk_x")
    assert s.resolve_provider() == "groq"


def test_explicit_provider_overrides_available_keys():
    s = Settings(llm_provider="groq", anthropic_api_key="sk-ant-x", groq_api_key="gsk_x")
    assert s.resolve_provider() == "groq"

    s = Settings(llm_provider="claude", anthropic_api_key=None, groq_api_key="gsk_x")
    assert s.resolve_provider() == "claude"


def test_missing_groq_key_raises_friendly_error(monkeypatch, sample_resume_content):
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", None)
    with pytest.raises(RuntimeError, match="Groq API key is not configured"):
        tailor_resume(
            resume_content=sample_resume_content,
            job_description="Python role",
            company="Globex",
            role="Backend Engineer",
        )


# ---------- strict schema ----------

def test_strict_schema_marks_every_field_required():
    schema = strict_json_schema(TailoringResult)

    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)

    check(schema)


def test_strict_schema_strips_unsupported_annotations():
    """`title`/`default` annotations are rejected by strict mode."""
    schema = strict_json_schema(TailoringResult)

    def check(node):
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                for subschema in properties.values():
                    assert "title" not in subschema
                    assert "default" not in subschema
                    check(subschema)
            for subschema in node.get("$defs", {}).values():
                assert "title" not in subschema
                check(subschema)
            if "items" in node:
                check(node["items"])

    assert "title" not in schema
    check(schema)


def test_strict_schema_keeps_a_property_named_title():
    """Resume entries have a "title" field — it must survive the cleanup."""
    entry = strict_json_schema(TailoringResult)["$defs"]["ExperienceEntry"]
    assert "title" in entry["properties"]
    assert entry["properties"]["title"] == {"type": "string"}
    assert "title" in entry["required"]


def test_strict_schema_covers_nested_models():
    schema = strict_json_schema(TailoringResult)
    defs = schema["$defs"]
    for name in ("ResumeContent", "ExperienceEntry", "ProjectEntry", "EducationEntry"):
        assert name in defs, name
        assert defs[name]["additionalProperties"] is False


# ---------- groq call path ----------

class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content, finish_reason="stop"):
        self.message = _FakeMessage(content)
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, content, finish_reason="stop"):
        self.choices = [_FakeChoice(content, finish_reason)]


def _install_fake_groq(monkeypatch, response):
    """Point the Groq client at a stub that returns `response`."""
    captured = {}

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return response

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, *args, **kwargs):
            captured["init"] = kwargs
            self.chat = _Chat()

    monkeypatch.setattr("app.services.tailoring.openai.OpenAI", _Client)
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test")
    return captured


def test_groq_path_parses_structured_response(monkeypatch, sample_resume_content):
    content = ResumeContent.model_validate(sample_resume_content)
    content.summary = "Targeted summary."
    content.full_name = "Overwritten By Model"
    payload = TailoringResult(
        tailored_resume=content,
        match_analysis=MatchAnalysis(match_score=77, matched_keywords=["Python"]),
    ).model_dump_json()

    captured = _install_fake_groq(monkeypatch, _FakeResponse(payload))

    result = tailor_resume(
        resume_content=sample_resume_content,
        job_description="We need Python.",
        company="Globex",
        role="Backend Engineer",
    )

    assert result.match_analysis.match_score == 77
    assert result.tailored_resume.summary == "Targeted summary."
    # Contact details come from the base resume, never the model.
    assert result.tailored_resume.full_name == "Om Patel"

    assert captured["init"]["base_url"] == "https://api.groq.com/openai/v1"
    assert captured["response_format"]["json_schema"]["strict"] is True


def test_groq_truncated_response_raises(monkeypatch, sample_resume_content):
    _install_fake_groq(monkeypatch, _FakeResponse('{"partial":', finish_reason="length"))
    with pytest.raises(RuntimeError, match="ran out of output tokens"):
        tailor_resume(
            resume_content=sample_resume_content,
            job_description="We need Python.",
            company="Globex",
            role="Backend Engineer",
        )


def test_groq_schema_mismatch_raises(monkeypatch, sample_resume_content):
    _install_fake_groq(monkeypatch, _FakeResponse('{"unexpected": true}'))
    with pytest.raises(RuntimeError, match="did not match the expected schema"):
        tailor_resume(
            resume_content=sample_resume_content,
            job_description="We need Python.",
            company="Globex",
            role="Backend Engineer",
        )
