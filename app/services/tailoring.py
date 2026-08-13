"""Claude-powered resume tailoring.

Given a base resume (structured JSON) and a job description, ask Claude to
rewrite the resume so it foregrounds the most relevant experience, skills, and
keywords for that specific job — without inventing anything the candidate
didn't do — and to return a match analysis (fit score, matched/missing
keywords, recommendations).
"""

import anthropic
from pydantic import BaseModel

from app.config import settings
from app.schemas import MatchAnalysis, ResumeContent

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


def tailor_resume(
    resume_content: dict, job_description: str, company: str, role: str
) -> TailoringResult:
    """Call Claude to tailor a resume to a job description."""
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "Anthropic API key is not configured. Set ANTHROPIC_API_KEY in your .env file."
        )
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    base = ResumeContent.model_validate(resume_content)

    user_prompt = (
        f"Tailor this resume for the role of {role} at {company}.\n\n"
        f"<base_resume>\n{base.model_dump_json(indent=2)}\n</base_resume>\n\n"
        f"<job_description>\n{job_description}\n</job_description>"
    )

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
