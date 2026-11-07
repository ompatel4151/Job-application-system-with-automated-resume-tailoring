"""The harness's wait on Groq's daily limit: the tailoring waits and goes on,
instead of quitting and throwing away the calls it already made."""

import sys
from pathlib import Path

import httpx
import openai
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import run_eval  # noqa: E402

DAILY = ("Rate limit reached for model `openai/gpt-oss-120b` in organization `org_x` service tier `on_demand` "
         "on tokens per day (TPD): Limit 200000, Used 199946, Requested 1528. Please try again in 10m36.768s.")


def rate_limited(message):
    request = httpx.Request("POST", "https://api.groq.com")
    return openai.RateLimitError(message, response=httpx.Response(429, request=request), body=None)


@pytest.mark.parametrize("text, seconds", [
    ("Please try again in 10m36.768s.", 636.768),
    ("Please try again in 1h2m3s.", 3723),
    ("Please try again in 547ms.", 0.547),
    ("no hint here", 600),
])
def test_retry_after_reads_groqs_hint(text, seconds):
    assert run_eval.retry_after(rate_limited(text)) == pytest.approx(seconds)


def test_a_daily_limit_waits_and_the_same_call_goes_on(monkeypatch):
    import openai.resources.chat.completions as completions

    replies = [rate_limited(DAILY), "the reply"]

    def fake(this, *args, **kwargs):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    slept = []
    monkeypatch.setattr(completions.Completions, "create", fake)
    monkeypatch.setattr(run_eval.time, "sleep", slept.append)
    waits = run_eval.InnerWaits()

    assert completions.Completions.create(None) == "the reply"
    assert slept == [pytest.approx(641.768)]  # Groq's hint plus 5 s
    _, limited, _, daily = waits.take()
    assert (limited, daily) == (0, 1)
