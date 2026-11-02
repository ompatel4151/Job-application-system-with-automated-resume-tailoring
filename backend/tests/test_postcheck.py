"""The citation post-check (AGENT_EXPERIMENT.md 3.3): a bullet may only use
numbers and tools that appear in the facts it cites."""

from app.agent.postcheck import problems
from app.schemas import Fact

INDEX = Fact(id="jt-index", text="Cut a query from 10.8 ms to 0.35 ms with an index.",
             numbers=["10.8 ms", "0.35 ms"], tools=["PostgreSQL", "EXPLAIN ANALYZE"])
REDIS = Fact(id="jt-redis", text="Token bucket in one atomic Lua script; 50 of 50 got through without it.",
             numbers=["50"], tools=["Redis", "Lua"])
SHEET_TOOLS = ["PostgreSQL", "EXPLAIN ANALYZE", "Redis", "Lua"]


def check(bullet, cited):
    return problems(bullet, cited, SHEET_TOOLS)


def test_a_bullet_using_only_its_cited_facts_passes():
    assert check("Cut a PostgreSQL query from 10.8 ms to 0.35 ms with an index.", [INDEX]) == []


def test_a_number_not_in_the_cited_facts_is_rejected():
    assert check("Cut query latency by 40% in PostgreSQL.", [INDEX]) == ["number 40% is not in the cited facts"]


def test_a_number_from_an_uncited_fact_is_still_rejected():
    """50 is on the sheet (jt-redis), but this bullet only cites jt-index."""
    assert check("Indexed 50 tables in PostgreSQL.", [INDEX]) == ["number 50 is not in the cited facts"]


def test_a_tool_not_in_the_cited_facts_is_rejected():
    assert check("Cut a query from 10.8 ms to 0.35 ms on Kubernetes.", [INDEX]) == [
        "Kubernetes is not in the cited facts"
    ]


def test_a_tool_from_the_users_sheet_but_another_fact_is_rejected():
    assert check("Cut a Redis query from 10.8 ms to 0.35 ms.", [INDEX]) == ["Redis is not in the cited facts"]


def test_unit_and_dash_variants_still_match():
    assert check("Cut a query from 10.8ms to 0.35 ms.", [INDEX]) == []
    assert check("Stopped 50‑of‑50 requests with Redis and Lua.", [REDIS]) == []


def test_a_bullet_citing_nothing_may_not_use_numbers_or_tools():
    assert check("Worked on PostgreSQL performance.", []) == ["PostgreSQL is not in the cited facts"]
    assert check("Led a team of 4.", []) == ["number 4 is not in the cited facts"]
