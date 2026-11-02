"""Run one mode over the eval set once, resumably (AGENT_EXPERIMENT.md, Steps 1 and 3).

Usage, from eval/ with GROQ_API_KEY set in backend/.env:
  ../.venv/bin/python run_eval.py --mode plain --version v0 --run 1

Output: private/runs/<mode>-<version>-run<n>.jsonl, one line per JD (private:
it holds resume text). Re-running the same command skips JDs already done, so a
run can span several days of free-tier quota.

Latency is the wall time of the successful attempt only. Pacing sleeps, waits
after 429s and transient-error retries (timeouts, 5xx) are excluded and counted
separately. The SDK's own retries are turned off, because they ran inside the
timed call and hid there (amendment A3).

A JD counts as done when its latest row is ok, so appending an ok=False row
with "contaminated": true makes the next run re-measure it.
"""

import argparse
import time
from collections import deque
from pathlib import Path

import openai

from common import PRIVATE, TAILOR_MODEL, CallRecorder, append_jsonl, holdout_ids, load_facts, load_jds, read_jsonl


def tailor_plain(base: dict, jd: dict, ctx=None):
    from app.services import tailoring
    return tailoring.tailor_resume(base, jd["text"], jd["company"], jd["role"]), None


def tailor_agent(base: dict, jd: dict, ctx):
    """The live code path, with the run's own namespace and the fact sheet."""
    from app import agent
    return agent.tailor_or_fallback(
        user_id=ctx["user"], facts=ctx["facts"], memories=[], resume_content=base,
        job_description=jd["text"], company=jd["company"], role=jd["role"],
        plain=lambda: tailor_plain(base, jd)[0], job_key=jd["id"],
    )


MODES = {"plain": tailor_plain, "agent": tailor_agent}


def daily(exc) -> bool:
    return "per day" in str(exc).lower() or "tpd" in str(exc).lower()


class InnerWaits:
    """Agent mode makes several calls per tailoring. A per-minute 429 or a
    transient error in the middle waits and retries here, timed and taken out
    of the latency (section 7d), instead of making the agent fall back."""

    def __init__(self):
        import openai.resources.chat.completions as completions

        self.seconds, self.rate_limited, self.transient = 0.0, 0, 0
        inner, waits = completions.Completions.create, self

        def create(this, *args, **kwargs):
            for _ in range(30):
                start = time.perf_counter()
                try:
                    return inner(this, *args, **kwargs)
                except openai.RateLimitError as exc:
                    if daily(exc):
                        raise SystemExit("Daily token quota reached. Re-run the same command tomorrow.") from exc
                    waits.rate_limited += 1
                    pause = 30
                except openai.APIError as exc:
                    if not transient(exc):
                        raise
                    waits.transient += 1
                    pause = 5
                time.sleep(pause)
                waits.seconds += time.perf_counter() - start
            raise SystemExit("Rate-limited 30 times in a row; re-run later.")

        completions.Completions.create = create

    def take(self) -> tuple[float, int, int]:
        taken = (self.seconds, self.rate_limited, self.transient)
        self.seconds, self.rate_limited, self.transient = 0.0, 0, 0
        return taken


def agent_context(version: str, run: int) -> dict:
    """A namespace per (version, run), so find_similar_jobs only sees this
    run's earlier JDs. The fact sheet is indexed into it before the first JD."""
    import uuid

    from app import vectorstore
    from app.schemas import Fact

    user = uuid.uuid5(uuid.NAMESPACE_URL, f"job-tracker-eval/{version}/run{run}")
    store = vectorstore.store_for(user)
    if store is None:
        raise SystemExit("Agent mode needs PINECONE_API_KEY in backend/.env.")
    facts = [Fact(id=f.id, text=f.text, numbers=f.numbers, tools=f.tools, context=f.context) for f in load_facts()]
    store.upsert("fact", {f.id: {"text": vectorstore.fact_text(f)} for f in facts})
    for _ in range(30):  # Pinecone is eventually consistent; wait until the facts are searchable
        if facts[-1].id in [i for i, _ in store.search("fact", facts[-1].text, 3)]:
            break
        time.sleep(2)
    else:
        raise SystemExit("Facts not searchable in Pinecone after 60 s.")
    return {"user": user, "facts": facts}


def transient(exc) -> bool:
    """The errors the SDK used to retry on its own, minus 429 (handled apart)."""
    return isinstance(exc, openai.APIConnectionError) or (
        isinstance(exc, openai.APIStatusError) and (exc.status_code in (408, 409) or exc.status_code >= 500)
    )


def disable_sdk_retries():
    init = openai.OpenAI.__init__

    def no_retries(self, *args, **kwargs):
        init(self, *args, **{**kwargs, "max_retries": 0})

    openai.OpenAI.__init__ = no_retries


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=sorted(MODES), required=True)
    p.add_argument("--jds", default=None, help="another JD file, e.g. injection_jds.yaml (reported apart)")
    p.add_argument("--version", required=True, help="v0 for the baseline; v1, v2... for agent iterations")
    p.add_argument("--run", type=int, choices=[1, 2, 3], required=True)
    p.add_argument("--tpm", type=int, default=8000, help="tokens per minute to stay under")
    p.add_argument("--skip-holdout", action="store_true", help="for agent iteration runs only")
    a = p.parse_args()

    from app.config import settings
    settings.llm_provider, settings.groq_model = "groq", TAILOR_MODEL
    load_facts()  # refuses to run on an unverified sheet
    import json
    base = json.loads((PRIVATE / "base_resume.json").read_text())
    jds = load_jds(a.jds) if a.jds else load_jds()
    skip = holdout_ids(load_jds()) if a.skip_holdout else set()
    tag = f"-{Path(a.jds).stem}" if a.jds else ""
    out = PRIVATE / "runs" / f"{a.mode}-{a.version}{tag}-run{a.run}.jsonl"
    latest = {r["jd_id"]: r for r in read_jsonl(out)}
    done = {i for i, r in latest.items() if r["ok"]}
    disable_sdk_retries()
    recorder = CallRecorder()
    inner = InnerWaits() if a.mode == "agent" else None
    ctx = agent_context(a.version + tag, a.run) if a.mode == "agent" and set(i["id"] for i in jds) - done else None
    recent: deque = deque()  # (time, tokens) of the last minute's calls

    for jd in jds:
        if jd["id"] in done or jd["id"] in skip:
            continue
        rate_limit_waits = paced_seconds = transient_seconds = 0.0
        attempts = transient_retries = 0
        while True:
            # Pace: keep the last minute's tokens plus a guess for this call under the limit.
            while recent and time.time() - recent[0][0] > 60:
                recent.popleft()
            if sum(t for _, t in recent) + 7000 > a.tpm and recent and a.mode == "plain":
                wait = 61 - (time.time() - recent[0][0])
                paced_seconds += wait
                time.sleep(max(wait, 1))
                continue
            attempts += 1
            recorder.take()
            if inner:
                inner.take()
            start = time.perf_counter()
            try:
                result, trace = MODES[a.mode](base, jd, ctx)
                latency = time.perf_counter() - start
                calls = recorder.take()
                waited, limited, flaky = inner.take() if inner else (0.0, 0, 0)
                latency -= waited
                transient_retries += flaky
                recent.extend((time.time(), c["prompt_tokens"] + c["completion_tokens"]) for c in calls)
                append_jsonl(out, {
                    "jd_id": jd["id"], "ok": True, "latency_s": round(latency, 3), "calls": calls,
                    "attempts": attempts, "rate_limit_wait_s": round(rate_limit_waits, 1),
                    "paced_s": round(paced_seconds, 1), "transient_retries": transient_retries,
                    "transient_s": round(transient_seconds, 1), "inner_wait_s": round(waited, 1),
                    "inner_429s": limited, "result": dump(result, trace),
                    "trace": trace.model_dump() if trace else None,
                })
                note = f", fell back: {trace.fallback}" if trace and trace.fallback else ""
                print(f"{jd['id']}: ok in {latency:.1f}s, {len(calls)} call(s){note}")
                break
            except RuntimeError as exc:
                calls = recorder.take()
                cause = exc.__cause__
                if isinstance(cause, openai.RateLimitError):
                    if daily(cause):
                        raise SystemExit("Daily token quota reached. Re-run the same command tomorrow.") from exc
                    rate_limit_waits += 30
                    time.sleep(30)
                    continue
                if transient(cause):
                    transient_retries += 1
                    transient_seconds += time.perf_counter() - start + 5
                    time.sleep(5)
                    continue
                append_jsonl(out, {"jd_id": jd["id"], "ok": False, "error": str(exc), "calls": calls, "attempts": attempts})
                print(f"{jd['id']}: FAILED: {exc}")
                break


def dump(result, trace) -> dict:
    """The result as scored: agent blockers go in match_analysis, where
    score.py reads them (plain mode has none)."""
    out = result.model_dump()
    out["match_analysis"]["blockers"] = trace.blockers if trace else []
    return out


if __name__ == "__main__":
    main()
