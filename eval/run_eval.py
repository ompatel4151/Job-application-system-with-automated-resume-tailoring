"""Run one mode over the eval set once, resumably (AGENT_EXPERIMENT.md, Steps 1 and 3).

Usage, from eval/ with GROQ_API_KEY set in backend/.env:
  ../.venv/bin/python run_eval.py --mode plain --version v0 --run 1

Output: private/runs/<mode>-<version>-run<n>.jsonl, one line per JD (private:
it holds resume text). Re-running the same command skips JDs already done, so a
run can span several days of free-tier quota.

Latency is the wall time of the successful attempt only. Pacing sleeps and
waits after 429s are excluded and counted separately.
"""

import argparse
import time
from collections import deque

import openai

from common import PRIVATE, TAILOR_MODEL, CallRecorder, append_jsonl, holdout_ids, load_facts, load_jds, read_jsonl


def tailor_plain(base: dict, jd: dict):
    from app.services import tailoring
    return tailoring.tailor_resume(base, jd["text"], jd["company"], jd["role"])


MODES = {"plain": tailor_plain}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=sorted(MODES), required=True)
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
    jds = load_jds()
    skip = holdout_ids(jds) if a.skip_holdout else set()
    out = PRIVATE / "runs" / f"{a.mode}-{a.version}-run{a.run}.jsonl"
    done = {r["jd_id"] for r in read_jsonl(out) if r["ok"]}
    recorder = CallRecorder()
    recent: deque = deque()  # (time, tokens) of the last minute's calls

    for jd in jds:
        if jd["id"] in done or jd["id"] in skip:
            continue
        rate_limit_waits = paced_seconds = 0.0
        attempts = 0
        while True:
            # Pace: keep the last minute's tokens plus a guess for this call under the limit.
            while recent and time.time() - recent[0][0] > 60:
                recent.popleft()
            if sum(t for _, t in recent) + 7000 > a.tpm and recent:
                wait = 61 - (time.time() - recent[0][0])
                paced_seconds += wait
                time.sleep(max(wait, 1))
                continue
            attempts += 1
            recorder.take()
            start = time.perf_counter()
            try:
                result = MODES[a.mode](base, jd)
                latency = time.perf_counter() - start
                calls = recorder.take()
                recent.extend((time.time(), c["prompt_tokens"] + c["completion_tokens"]) for c in calls)
                append_jsonl(out, {
                    "jd_id": jd["id"], "ok": True, "latency_s": round(latency, 3), "calls": calls,
                    "attempts": attempts, "rate_limit_wait_s": round(rate_limit_waits, 1),
                    "paced_s": round(paced_seconds, 1), "result": result.model_dump(),
                })
                print(f"{jd['id']}: ok in {latency:.1f}s, {len(calls)} call(s)")
                break
            except RuntimeError as exc:
                calls = recorder.take()
                cause = exc.__cause__
                if isinstance(cause, openai.RateLimitError):
                    if "per day" in str(cause).lower() or "tpd" in str(cause).lower():
                        raise SystemExit("Daily token quota reached. Re-run the same command tomorrow.") from exc
                    rate_limit_waits += 30
                    time.sleep(30)
                    continue
                append_jsonl(out, {"jd_id": jd["id"], "ok": False, "error": str(exc), "calls": calls, "attempts": attempts})
                print(f"{jd['id']}: FAILED: {exc}")
                break


if __name__ == "__main__":
    main()
