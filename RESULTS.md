# Results

Real measurements only. Each entry states the command, the machine and the
commit. Anything not measured is marked "not measured".

## Machine

- Apple M4, 16 GB RAM, macOS 27.0.1
- Python 3.11.15 (project venv)
- Database for tests: in-memory SQLite

## Milestone 1: baseline

**Test suite.** Run once on commit `ce5d48f`:

```bash
cd backend && ../.venv/bin/python -m pytest
```

Output: `55 passed in 0.38s`. That's a single run, so treat the time as
rough. It is not a benchmark.

**Live deployment.** No performance numbers exist. The app was never load
tested, and no latency or traffic was measured. Load testing is milestone 6
and will run **locally only**.
