"""Score runs into the pre-registered metrics (AGENT_EXPERIMENT.md, section 7).

Usage: ../.venv/bin/python score.py --mode plain --version v0
Reads private/runs/<mode>-<version>-run{1,2,3}.jsonl and writes
results/<mode>-<version>.json: aggregate numbers only, no resume or JD text.
"""

import argparse
import json
import statistics

from checker import Checker, bullets_of
from common import EVAL, PRIVATE, holdout_ids, load_facts, load_jds, read_jsonl
from judge import Judge

PRICES = json.loads((EVAL / "prices.json").read_text())


def cost(calls):
    return sum(c["prompt_tokens"] * PRICES[c["model"]]["input_per_million"] / 1e6
               + c["completion_tokens"] * PRICES[c["model"]]["output_per_million"] / 1e6 for c in calls)


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, max(0, round(q * (len(values) - 1))))]


def score_run(rows, jds, checker, judge, keywords, ids):
    from app.schemas import ResumeContent
    from app.services.ats import ats_check

    latest = {}
    for r in rows:  # a JD may have a failed attempt before a later success
        latest[r["jd_id"]] = r
    ok = [latest[i] for i in ids if i in latest and latest[i]["ok"]]
    units = invented = check_flags = judge_flags = 0
    ats, caught = [], 0
    blocker_jds = {j["id"]: j["blocker"] for j in jds if j.get("blocker")}
    false_positives = 0
    for r in ok:
        resume, analysis = r["result"]["tailored_resume"], r["result"]["match_analysis"]
        units_here = bullets_of(resume)
        for bullet, verdict in zip(units_here, judge.verdicts(units_here)):
            c, j = not checker.check(bullet).supported, not verdict.supported
            units += 1
            check_flags += c
            judge_flags += j
            invented += c or j
        ats.append(ats_check(ResumeContent.model_validate(resume), keywords[r["jd_id"]]).score)
        found = [b.lower() for b in analysis.get("blockers", [])]
        if r["jd_id"] in blocker_jds:
            caught += any(blocker_jds[r["jd_id"]].lower() in b for b in found)
        elif found:
            false_positives += 1
    return {
        "jds_scored": len(ok), "jds_failed": len([i for i in ids if i in latest and not latest[i]["ok"]]),
        # Failures that a later re-run of the harness retried successfully.
        "first_attempt_failures": len({r["jd_id"] for r in rows if not r["ok"] and r["jd_id"] in ids}),
        "bullets": units,
        "invented_rate": invented / units if units else None,
        "checker_flag_rate": check_flags / units if units else None,
        "judge_flag_rate": judge_flags / units if units else None,
        "ats_mean": statistics.mean(ats) if ats else None,
        "blockers_caught": caught, "blocker_jds": len([i for i in blocker_jds if i in ids]),
        "blocker_false_positives": false_positives,
        "latencies": [r["latency_s"] for r in ok],
        "calls_mean": statistics.mean(len(r["calls"]) for r in ok) if ok else None,
        "tokens_mean": statistics.mean(sum(c["prompt_tokens"] + c["completion_tokens"] for c in r["calls"]) for r in ok) if ok else None,
        "cost_mean_usd": statistics.mean(cost(r["calls"]) for r in ok) if ok else None,
        "rate_limit_wait_s": sum(r.get("rate_limit_wait_s", 0) for r in ok),
    }


def summarize(runs):
    def med_range(key):
        values = [r[key] for r in runs if r[key] is not None]
        return {"median": statistics.median(values), "min": min(values), "max": max(values)} if values else None

    pooled = [x for r in runs for x in r["latencies"]]
    return {
        "invented_rate": med_range("invented_rate"), "checker_flag_rate": med_range("checker_flag_rate"),
        "judge_flag_rate": med_range("judge_flag_rate"), "ats_mean": med_range("ats_mean"),
        "ats_mean_pooled": statistics.mean(r["ats_mean"] for r in runs if r["ats_mean"] is not None),
        "blockers_caught": med_range("blockers_caught"),
        "latency_p50_pooled_s": pct(pooled, 0.5) if pooled else None,
        "latency_p95_pooled_s": pct(pooled, 0.95) if pooled else None,
        "calls_mean": med_range("calls_mean"), "tokens_mean": med_range("tokens_mean"),
        "cost_mean_usd": med_range("cost_mean_usd"),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True)
    p.add_argument("--version", required=True)
    a = p.parse_args()
    facts, jds = load_facts(), load_jds()
    checker, judge = Checker(facts), Judge(facts)
    keywords = json.loads((PRIVATE / "keywords.json").read_text())
    all_ids, held = [j["id"] for j in jds], holdout_ids(jds)
    report = {"mode": a.mode, "version": a.version, "eval_set": len(jds), "runs": {}}
    for subset, ids in (("all", all_ids), ("holdout", [i for i in all_ids if i in held])):
        runs = []
        for n in (1, 2, 3):
            rows = read_jsonl(PRIVATE / "runs" / f"{a.mode}-{a.version}-run{n}.jsonl")
            if rows:
                runs.append(score_run(rows, jds, checker, judge, keywords, ids))
        report["runs"][subset] = [{k: v for k, v in r.items() if k != "latencies"} for r in runs]
        report[subset] = summarize(runs) if runs else None
    report["judge_calls"] = len(judge.calls)
    out = EVAL / "results" / f"{a.mode}-{a.version}.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report["all"], indent=2))


if __name__ == "__main__":
    main()
