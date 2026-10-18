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

## Milestone 4: validation and errors

On commit `5bfe82b`, same machine:

- Backend: `93 passed in 0.43s`, 0 xfailed. That's 16 new validation tests;
  the audit #4 known-issue test was removed once it started passing.
- Frontend: `10 passed`, lint clean, build OK.
- Before the fix the new tests ran red: 14 failed, 2 passed. Every bad input
  returned 201, `PATCH null` raised the database error again, errors had no
  `code`, and a score of 150 passed through.

## Milestone 5: rate limiting

On commit `b6dd38d`, same machine:

- Backend: `103 passed in 0.51s`. That's 10 new rate-limit tests; the tests
  use a fake clock, so no timing is involved.
- Frontend: `10 passed`, lint clean, build OK.
- Before the code existed, the test file failed to import (`cannot import
  name 'ratelimit'`).
- Check that the security test can fail: I removed the "trust X-Forwarded-For
  only with the API key" condition, and
  `test_spoofed_forwarded_ip_is_ignored_without_the_key` failed (1 failed,
  9 passed). Then I restored the code.
- The limits (5/min for LLM endpoints, 60/min otherwise) are design choices,
  not measurements.

**Live deployment.** No performance numbers exist. The app was never load
tested, and no latency or traffic was measured. Load testing is milestone 6
and will run **locally only**.
