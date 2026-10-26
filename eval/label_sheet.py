"""Hand labels for rule 6 (AGENT_EXPERIMENT.md, section 7a).

  ../.venv/bin/python label_sheet.py make --mode plain --version v0
      Draws a random 20% of run 1's bullets (fixed seed) into
      private/labels/<mode>-<version>.csv with an empty "label" column and no
      automatic labels, so you label blind. Fill in supported / unsupported.
  ../.venv/bin/python label_sheet.py agree --mode plain --version v0
      Agreement of the checker, the judge and their union with your labels.
"""

import argparse
import csv
import random

from checker import Checker, bullets_of
from common import LABEL_SEED, PRIVATE, load_facts, read_jsonl
from judge import Judge


def bullets(mode, version):
    rows = read_jsonl(PRIVATE / "runs" / f"{mode}-{version}-run1.jsonl")
    latest = {r["jd_id"]: r for r in rows}
    return [(jd, i, b) for jd, r in sorted(latest.items()) if r["ok"]
            for i, b in enumerate(bullets_of(r["result"]["tailored_resume"]))]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["make", "agree"])
    p.add_argument("--mode", required=True)
    p.add_argument("--version", required=True)
    a = p.parse_args()
    path = PRIVATE / "labels" / f"{a.mode}-{a.version}.csv"
    if a.action == "make":
        if path.exists():
            raise SystemExit(f"{path} exists; the sample is drawn once.")
        items = bullets(a.mode, a.version)
        sample = random.Random(LABEL_SEED).sample(items, round(0.2 * len(items)))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["jd_id", "index", "bullet", "label"])
            w.writerows([jd, i, b, ""] for jd, i, b in sample)
        print(f"{len(sample)} of {len(items)} bullets -> {path}")
        return
    facts = load_facts()
    checker, judge = Checker(facts), Judge(facts)
    rows = list(csv.DictReader(path.open()))
    if any(r["label"].strip() not in ("supported", "unsupported") for r in rows):
        raise SystemExit("Every row needs label = supported or unsupported.")
    agree = {"checker": 0, "judge": 0, "union": 0}
    for r in rows:
        human = r["label"].strip() == "unsupported"
        c, j = not checker.check(r["bullet"]).supported, not judge.verdict(r["bullet"]).supported
        agree["checker"] += c == human
        agree["judge"] += j == human
        agree["union"] += (c or j) == human
    for k, v in agree.items():
        print(f"{k}: {v}/{len(rows)} = {v / len(rows):.1%}")


if __name__ == "__main__":
    main()
