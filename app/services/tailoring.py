"""LLM-powered resume tailoring.

Given a base resume (structured JSON) and a job description, ask a model to
rewrite the resume so it foregrounds the most relevant experience, skills, and
keywords for that specific job — without inventing anything the candidate
didn't do — and to return a match analysis (fit score, matched/missing
keywords, recommendations).

Two backends are supported behind one interface, both using schema-constrained
structured outputs so the response is always valid against the resume schema:

- Claude, via the Anthropic SDK's ``messages.parse``
- Groq (OpenAI-compatible), via ``response_format`` with a strict JSON schema

``tailor_resume`` dispatches on the configured provider; everything above this
module is provider-agnostic.
"""

from typing import Any

import anthropic
import openai
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.schemas import MatchAnalysis, ResumeContent

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

SYSTEM_PROMPT = """\
You are an expert resume writer and recruiter. You tailor resumes to specific
job descriptions.

Rules:
- Never invent experience, employers, titles, dates, degrees, or metrics that
  are not in the base resume. You may rephrase, reorder, emphasize, and cut.
- Rewrite bullet points to lead with impact and mirror the vocabulary of the
  job description where it is truthful to do so.
- Reorder skills and experience bullets so the most job-relevant items come
  first. Drop bullets that are irrelevant to this job if the resume is long.
- Keep the summary to 2-3 sentences, targeted at this specific role.
- In the match analysis, matched_keywords are terms from the job description
  the candidate genuinely has; missing_keywords are important requirements the
  candidate lacks or hasn't demonstrated; recommendations are concrete actions
  (things to learn, projects to highlight, points to address in a cover
  letter). Score fit honestly on a 0-100 scale.
"""


class TailoringResult(BaseModel):
    tailored_resume: ResumeContent
    match_analysis: MatchAnalysis


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Render a Pydantic model as a JSON schema that satisfies strict mode.

    Strict structured outputs require every object to list all of its
    properties as ``required`` and to set ``additionalProperties: false``.
    Pydantic omits fields that have defaults from ``required``, and annotations
    like ``title``/``default`` are not accepted, so both are stripped here.
    """
    schema = model.model_json_schema()

    def clean(node: Any) -> None:
        """Normalize one schema node.

        Only annotations on the node itself are stripped — property *names* are
        left alone, since a resume entry legitimately has a field called
        "title".
        """
        if not isinstance(node, dict):
            return
        node.pop("title", None)
        node.pop("default", None)

        properties = node.get("properties")
        if isinstance(properties, dict):
            node["additionalProperties"] = False
            node["required"] = list(properties)
            for subschema in properties.values():
                clean(subschema)

        # Every other place a subschema can appear.
        for key in ("items", "not"):
            if key in node:
                clean(node[key])
        for key in ("anyOf", "allOf", "oneOf", "prefixItems"):
            for subschema in node.get(key, []):
                clean(subschema)
        for definitions in ("$defs", "definitions"):
            for subschema in node.get(definitions, {}).values():
                clean(subschema)

    clean(schema)
    return schema


def _user_prompt(base: ResumeContent, job_description: str, company: str, role: str) -> str:
    return (
        f"Tailor this resume for the role of {role} at {company}.\n\n"
        f"<base_resume>\n{base.model_dump_json(indent=2)}\n</base_resume>\n\n"
        f"<job_description>\n{job_description}\n</job_description>"
    )


def _tailor_with_claude(base: ResumeContent, user_prompt: str) -> TailoringResult:
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "Anthropic API key is not configured. Set ANTHROPIC_API_KEY in your .env file."
        )
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            output_format=TailoringResult,
        )
    except anthropic.AuthenticationError as exc:
        raise RuntimeError("Anthropic API key was rejected. Check ANTHROPIC_API_KEY.") from exc
    except anthropic.APIConnectionError as exc:
        raise RuntimeError("Could not reach the Anthropic API. Check your network.") from exc
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"Anthropic API error ({exc.status_code}): {exc.message}") from exc
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined to process this request.")
    result = response.parsed_output
    if result is None:
        raise RuntimeError("Model response did not match the expected schema.")
    return result


def _tailor_with_groq(base: ResumeContent, user_prompt: str) -> TailoringResult:
    if not settings.groq_api_key:
        raise RuntimeError(
            "Groq API key is not configured. Set GROQ_API_KEY in your .env file."
        )
    client = openai.OpenAI(api_key=settings.groq_api_key, base_url=GROQ_BASE_URL)
    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=8000,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "tailoring_result",
                    "strict": True,
                    "schema": strict_json_schema(TailoringResult),
                },
            },
        )
    except openai.AuthenticationError as exc:
        raise RuntimeError("Groq API key was rejected. Check GROQ_API_KEY.") from exc
    except openai.RateLimitError as exc:
        # Groq's free tier allows only 6k tokens/minute, which one tailoring
        # call can exhaust on its own — worth naming explicitly.
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
        raise RuntimeError(
            "The model ran out of output tokens before finishing the resume. "
            "Try a shorter job description."
        )
    content = choice.message.content
    if not content:
        raise RuntimeError("Model returned an empty response.")
    try:
        return TailoringResult.model_validate_json(content)
    except ValidationError as exc:
        raise RuntimeError("Model response did not match the expected schema.") from exc


def tailor_resume(
    resume_content: dict, job_description: str, company: str, role: str
) -> TailoringResult:
    """Tailor a resume to a job description using the configured provider."""
    base = ResumeContent.model_validate(resume_content)
    user_prompt = _user_prompt(base, job_description, company, role)

    provider = settings.resolve_provider()
    if provider == "groq":
        result = _tailor_with_groq(base, user_prompt)
    else:
        result = _tailor_with_claude(base, user_prompt)

    # Contact details are facts, not tailoring targets — always carry them over.
    result.tailored_resume.full_name = base.full_name
    result.tailored_resume.contact = base.contact
    return result


def render_markdown(content: ResumeContent) -> str:
    """Render structured resume content as a Markdown document."""
    lines: list[str] = []
    if content.full_name:
        lines.append(f"# {content.full_name}")
    if content.contact:
        lines.append(content.contact)
    if content.summary:
        lines += ["", "## Summary", content.summary]
    if content.skills:
        lines += ["", "## Skills", ", ".join(content.skills)]
    if content.experience:
        lines += ["", "## Experience"]
        for exp in content.experience:
            header = f"### {exp.title} — {exp.company}"
            if exp.dates:
                header += f" ({exp.dates})"
            lines.append(header)
            lines += [f"- {b}" for b in exp.bullets]
            lines.append("")
    if content.projects:
        lines += ["", "## Projects"]
        for proj in content.projects:
            lines.append(f"### {proj.name}")
            if proj.description:
                lines.append(proj.description)
            if proj.technologies:
                lines.append(f"*Technologies: {', '.join(proj.technologies)}*")
            lines += [f"- {b}" for b in proj.bullets]
            lines.append("")
    if content.education:
        lines += ["", "## Education"]
        for edu in content.education:
            header = f"### {edu.degree} — {edu.school}" if edu.degree else f"### {edu.school}"
            if edu.dates:
                header += f" ({edu.dates})"
            lines.append(header)
            lines += [f"- {d}" for d in edu.details]
    return "\n".join(lines).strip() + "\n"
