# Agent experiment: eval tooling

The pre-registered experiment is in [AGENT_EXPERIMENT.md](../AGENT_EXPERIMENT.md).
Everything in this folder was committed before any measurement ran.

## Private inputs (gitignored, in `eval/private/`)

- `facts.yaml`: the fact sheet. Every fact needs `verified: true`, or nothing
  runs.
- `base_resume.json`: what plain mode tailors from. It must score 0
  unsupported bullets against the facts (the calibration step).
The 30 job descriptions are **synthetic** and public: `eval/jds.yaml`
(amendment A2). They use this format:

```yaml
- id: swe-01            # unique; prefix swe-, aiml- or data-
  category: swe         # swe | ai_ml | data
  company: Example Co
  role: Backend Engineer
  blocker: null         # or a short key phrase written BEFORE any run,
                        # e.g. "sponsorship", "clearance", "C#".
                        # It counts as caught if the mode's blockers
                        # output contains that phrase (any case).
  text: |
    The full job description, pasted as is.
```

  5 of the 30 must have a blocker. Paste real postings; nothing is scraped.

## Order

All commands run from `eval/` with `../.venv/bin/python`, and need
`GROQ_API_KEY` in `backend/.env`.

1. `freeze_keywords.py`: once, before any run. It writes `keywords.json`,
   which both modes are scored against.
2. `run_eval.py --mode plain --version v0 --run 1`, then runs 2 and 3. It's
   resumable: re-run the same command after a free-tier daily limit.
3. `score.py --mode plain --version v0` writes `results/plain-v0.json`
   (aggregate numbers only).
4. `label_sheet.py make ...`, then you label the rows blind, then
   `label_sheet.py agree ...`.

Failed tailorings are kept in the run files and counted in the results.
They're never silently dropped.
