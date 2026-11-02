"""The fact sheet and agent memories: per-user data the agent may use
(AGENT_EXPERIMENT.md 3.1 and 3.3). RLS on Postgres is in test_rls.py."""

from tests.tokens import USER_A, USER_B, auth_header

FACTS = [
    {"id": "jt-redis", "text": "Shared rate limits with a Redis Lua token bucket.",
     "numbers": [], "tools": ["Redis", "Lua"], "context": "local"},
    {"id": "jt-index", "text": "Cut a query from 10.8 ms to 0.35 ms with an index.",
     "numbers": ["10.8 ms", "0.35 ms"], "tools": ["PostgreSQL"]},
]


def test_post_replaces_the_whole_sheet_and_get_lists_it(client):
    assert client.post("/api/facts", json={"facts": FACTS}).status_code == 201
    resp = client.post("/api/facts", json={"facts": FACTS[:1]})

    assert resp.status_code == 201
    assert [f["id"] for f in client.get("/api/facts").json()] == ["jt-redis"]


def test_facts_keep_their_fields(client):
    client.post("/api/facts", json={"facts": FACTS})
    fact = {f["id"]: f for f in client.get("/api/facts").json()}["jt-index"]

    assert fact == {**FACTS[1], "context": ""}


def test_delete_removes_one_fact(client):
    client.post("/api/facts", json={"facts": FACTS})

    assert client.delete("/api/facts/jt-redis").status_code == 204
    assert [f["id"] for f in client.get("/api/facts").json()] == ["jt-index"]
    assert client.delete("/api/facts/jt-redis").status_code == 404


def test_bad_sheets_are_rejected(client):
    dup = client.post("/api/facts", json={"facts": [FACTS[0], FACTS[0]]})
    bad_id = client.post("/api/facts", json={"facts": [{**FACTS[0], "id": "Has Spaces"}]})
    empty_text = client.post("/api/facts", json={"facts": [{**FACTS[0], "text": ""}]})

    assert dup.status_code == 422
    assert bad_id.status_code == 422
    assert empty_text.status_code == 422


def test_users_never_see_or_delete_each_others_facts(client):
    client.post("/api/facts", json={"facts": FACTS})
    as_b = auth_header(USER_B)

    assert client.get("/api/facts", headers=as_b).json() == []
    assert client.delete("/api/facts/jt-redis", headers=as_b).status_code == 404
    client.post("/api/facts", json={"facts": FACTS[:1]}, headers=as_b)  # B's own sheet
    assert len(client.get("/api/facts").json()) == 2  # A's sheet is untouched


def test_saving_facts_indexes_them_in_the_callers_namespace_only(client, fake_index):
    client.post("/api/facts", json={"facts": FACTS})
    client.post("/api/facts", json={"facts": FACTS[:1]})  # jt-index removed

    assert set(fake_index.namespaces) == {USER_A}
    assert set(fake_index.namespaces[USER_A]) == {"fact:jt-redis"}
    assert all(r["user_id"] == USER_A for r in fake_index.namespaces[USER_A].values())
    assert {ns for _, ns in fake_index.calls} == {USER_A}


def test_deleting_a_fact_removes_it_from_the_index(client, fake_index):
    client.post("/api/facts", json={"facts": FACTS})
    client.delete("/api/facts/jt-redis")

    assert set(fake_index.namespaces[USER_A]) == {"fact:jt-index"}


def test_facts_are_saved_even_when_pinecone_is_down(client, broken_index):
    """Postgres is the source of truth; the agent falls back to plain mode
    when it can't search."""
    resp = client.post("/api/facts", json={"facts": FACTS})

    assert resp.status_code == 201
    assert resp.json() == {"saved": 2, "indexed": False}


# ---------- memories ----------

def test_memories_create_list_delete(client):
    created = client.post("/api/memories", json={"text": "Keep bullets under 2 lines."})
    assert created.status_code == 201
    memory_id = created.json()["id"]

    assert [m["text"] for m in client.get("/api/memories").json()] == ["Keep bullets under 2 lines."]
    assert client.delete(f"/api/memories/{memory_id}").status_code == 204
    assert client.get("/api/memories").json() == []


def test_users_never_see_or_delete_each_others_memories(client):
    memory_id = client.post("/api/memories", json={"text": "mine"}).json()["id"]
    as_b = auth_header(USER_B)

    assert client.get("/api/memories", headers=as_b).json() == []
    assert client.delete(f"/api/memories/{memory_id}", headers=as_b).status_code == 404
    assert len(client.get("/api/memories", headers=auth_header(USER_A)).json()) == 1


def test_memory_text_is_bounded(client):
    assert client.post("/api/memories", json={"text": ""}).status_code == 422
    assert client.post("/api/memories", json={"text": "x" * 501}).status_code == 422


def test_the_store_drops_a_hit_owned_by_another_user():
    """Checked in the store itself, not only by the agent's own fact list."""
    from app import vectorstore
    from tests.fake_pinecone import FakeIndex

    index = FakeIndex()
    store = vectorstore.UserStore(index, USER_A)
    store.upsert("fact", {"mine": {"text": "Redis rate limits"}})
    index.namespaces[USER_A]["fact:planted"] = {"text": "Redis rate limits", "type": "fact", "user_id": USER_B}

    assert [i for i, _ in store.search("fact", "Redis rate limits", 8)] == ["mine"]
