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

## Milestone 2: tests first

Suite run once on commit `a256d21`, same machine and command:

Output: `70 passed, 1 xfailed in 0.71s`

- 55 existing tests, plus 15 new contract tests (one of them runs 9 times,
  once per endpoint).
- The 1 xfailed test is audit #4 (`PATCH null` returns 500). It is expected
  to fail until milestone 4.
- Times are single runs and not benchmarks.

## Milestone 3: idempotency

On commit `9117019`, same machine:

- Backend, `cd backend && ../.venv/bin/python -m pytest`:
  `77 passed, 1 xfailed in 0.81s`. That's 7 new idempotency tests; the
  xfail is still audit #4.
- Frontend, `cd frontend && npm test`: `10 passed`. One new test checks the
  `Idempotency-Key` header is sent.
- Before the fix, the same tests ran red: 5 failed, 2 passed. The retried
  create returned a new id (2 instead of 1), and the retried tailor called
  the model twice.

**Live deployment.** No performance numbers exist. The app was never load
tested, and no latency or traffic was measured. Load testing is milestone 6
and will run **locally only**.
