"""Agent mode behind the existing tailor endpoint (AGENT_EXPERIMENT.md 3.3,
3.4 and tests 4 and 7 of section 5)."""

import pytest

from app.config import settings
from tests.test_agent import ScriptedLLM, call, draft

FACTS = [{"id": "py-api", "text": "Built a FastAPI backend in Python with 18 REST endpoints.",
          "numbers": ["18"], "tools": ["FastAPI", "Python"]}]


@pytest.fixture()
def agent_mode(monkeypatch, client, fake_index, fake_tailoring):
    """TAILOR_MODE=agent with a scripted model; returns the list of models used."""
    monkeypatch.setattr(settings, "tailor_mode", "agent")
    monkeypatch.setattr(settings, "llm_provider", "groq")
    used = []

    def scripted():
        llm = ScriptedLLM(
            [call("search_resume_facts", query="Python FastAPI"),
             call("draft_bullets", section="project:0", fact_ids=["py-api"])],
            drafts=[draft(("Built a FastAPI backend in Python with 18 REST endpoints.", ["py-api"]))],
        )
        used.append(llm)
        return llm

    monkeypatch.setattr("app.agent.llm.GroqLLM", scripted)
    return used


def tailor(client, app_id, **headers):
    return client.post(f"/api/applications/{app_id}/tailor", json={}, headers=headers)


def test_agent_mode_returns_cited_bullets_and_a_trace(client, agent_mode, make_application, make_resume):
    client.post("/api/facts", json={"facts": FACTS})
    make_resume()
    resp = tailor(client, make_application()["id"])

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["content"]["projects"][0]["bullets"] == ["Built a FastAPI backend in Python with 18 REST endpoints."]
    assert body["agent_trace"]["fallback"] is None
    assert body["agent_trace"]["citations"] == [
        {"text": "Built a FastAPI backend in Python with 18 REST endpoints.", "fact_ids": ["py-api"]}]
    assert client.get(f"/api/tailored/{body['id']}").json()["agent_trace"] == body["agent_trace"]


def test_a_finished_job_is_saved_for_find_similar_jobs(client, agent_mode, fake_index, make_application,
                                                       make_resume):
    client.post("/api/facts", json={"facts": FACTS})
    make_resume()
    app_id = make_application()["id"]
    tailor(client, app_id)

    saved = [r for r in next(iter(fake_index.namespaces.values())).values() if r["type"] == "jd"]
    assert [(r["title"], r["fact_ids"]) for r in saved] == [("Backend Engineer at Globex", ["py-api"])]


def test_plain_mode_has_no_trace(client, fake_tailoring, make_application, make_resume):
    make_resume()
    resp = tailor(client, make_application()["id"])

    assert resp.status_code == 201
    assert resp.json()["agent_trace"] is None


def test_no_facts_falls_back_to_plain_mode(client, agent_mode, make_application, make_resume):
    make_resume()
    resp = tailor(client, make_application()["id"])

    assert resp.status_code == 201
    assert resp.json()["agent_trace"]["fallback"] == "no_facts"
    assert resp.json()["content"]["summary"] == "Engineer targeting Backend Engineer at Globex."  # plain's


def test_pinecone_down_falls_back_to_plain_mode(client, agent_mode, make_application, make_resume, monkeypatch):
    client.post("/api/facts", json={"facts": FACTS})
    make_resume()
    from tests.fake_pinecone import BrokenIndex
    monkeypatch.setattr("app.vectorstore._index", lambda: BrokenIndex())
    resp = tailor(client, make_application()["id"])

    assert resp.status_code == 201
    assert resp.json()["agent_trace"]["fallback"] == "vector_store"


def test_a_claude_provider_falls_back_to_plain_mode(client, agent_mode, make_application, make_resume,
                                                    monkeypatch):
    client.post("/api/facts", json={"facts": FACTS})
    make_resume()
    monkeypatch.setattr(settings, "llm_provider", "claude")

    assert tailor(client, make_application()["id"]).json()["agent_trace"]["fallback"] == "provider"


def test_agent_mode_keeps_the_per_user_rate_limit(client, agent_mode, make_application, make_resume):
    client.post("/api/facts", json={"facts": FACTS})
    make_resume()
    app_id = make_application()["id"]
    codes = [tailor(client, app_id).status_code for _ in range(6)]

    assert codes == [201] * 5 + [429]


def test_a_repeated_idempotency_key_replays_without_calling_the_model(client, agent_mode, make_application,
                                                                     make_resume):
    client.post("/api/facts", json={"facts": FACTS})
    make_resume()
    app_id = make_application()["id"]
    first = tailor(client, app_id, **{"Idempotency-Key": "agent-1"})
    second = tailor(client, app_id, **{"Idempotency-Key": "agent-1"})

    assert second.status_code == 201
    assert second.json() == first.json()
    assert len(agent_mode) == 1  # one model, one run
