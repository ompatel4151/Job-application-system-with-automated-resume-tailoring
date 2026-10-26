"""Shared pieces of the eval: loading the private inputs, the hold-out split,
and recording every LLM call's timing and token usage without touching app code."""

import hashlib
import json
import random
import sys
import time
from pathlib import Path

import yaml

EVAL = Path(__file__).resolve().parent
PRIVATE = EVAL / "private"
sys.path.insert(0, str(EVAL.parent / "backend"))

from dotenv import load_dotenv  # noqa: E402

# The app reads .env from the working directory; the eval runs from eval/.
load_dotenv(EVAL.parent / "backend" / ".env")

from checker import Fact  # noqa: E402

HOLDOUT_SEED = 20261025  # AGENT_EXPERIMENT.md, "Approved additions (D7)"
LABEL_SEED = 20261025    # AGENT_EXPERIMENT.md, section 7a
TAILOR_MODEL = "openai/gpt-oss-120b"
JUDGE_MODEL = "qwen/qwen3.8-27b"


def load_facts() -> list[Fact]:
    raw = yaml.safe_load((PRIVATE / "facts.yaml").read_text())
    unverified = [f["id"] for f in raw if not f.get("verified")]
    if unverified:
        raise SystemExit(f"Refusing to run: {len(unverified)} unverified facts, e.g. {unverified[:3]}")
    return [Fact(**{k: v for k, v in f.items() if k != "verified"}) for f in raw]


def load_jds() -> list[dict]:
    jds = yaml.safe_load((PRIVATE / "jds.yaml").read_text())
    ids = [j["id"] for j in jds]
    assert len(ids) == len(set(ids)), "duplicate JD ids"
    return jds


def holdout_ids(jds: list[dict]) -> set[str]:
    return set(random.Random(HOLDOUT_SEED).sample(sorted(j["id"] for j in jds), 10))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class CallRecorder:
    """Wraps the OpenAI-compatible client the app uses for Groq, so each call's
    model, tokens and wall time are recorded. The app code itself is unchanged."""

    def __init__(self):
        self.calls: list[dict] = []
        import openai.resources.chat.completions as completions

        self._original = completions.Completions.create
        recorder = self

        def create(this, *args, **kwargs):
            start = time.perf_counter()
            response = recorder._original(this, *args, **kwargs)
            usage = getattr(response, "usage", None)
            recorder.calls.append({
                "model": kwargs.get("model"),
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "seconds": round(time.perf_counter() - start, 3),
            })
            return response

        completions.Completions.create = create

    def take(self) -> list[dict]:
        calls, self.calls = self.calls, []
        return calls


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
