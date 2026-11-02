"""Namespace isolation on real Pinecone (AGENT_EXPERIMENT.md section 5, test 1).

Opt-in, so ordinary test runs never touch the network or the free-tier
quota: PINECONE_LIVE_TEST=1 plus PINECONE_API_KEY in backend/.env. Uses two
throwaway namespaces and deletes them afterwards.
"""

import os
import time
import uuid

import pytest

from app import vectorstore

pytestmark = pytest.mark.skipif(os.environ.get("PINECONE_LIVE_TEST") != "1", reason="PINECONE_LIVE_TEST not set")


def test_two_namespaces_never_see_each_other():
    index = vectorstore._pinecone_index()
    a = vectorstore.UserStore(index, uuid.uuid4())
    b = vectorstore.UserStore(index, uuid.uuid4())
    try:
        a.upsert("fact", {"a-redis": {"text": "Built a Redis token bucket in a Lua script."}})
        b.upsert("fact", {"b-docs": {"text": "Wrote documentation for an internal tool."}})
        for _ in range(30):  # eventually consistent
            if a.search("fact", "Redis token bucket", 3) and b.search("fact", "documentation", 3):
                break
            time.sleep(2)

        assert [i for i, _ in a.search("fact", "Redis token bucket", 3)] == ["a-redis"]
        assert [i for i, _ in b.search("fact", "Redis token bucket Lua", 3)] == ["b-docs"]  # never a-redis
        assert "a-redis" not in [i for i, _ in b.search("fact", "Built a Redis token bucket in a Lua script.", 10)]
    finally:
        for store in (a, b):
            index.delete(delete_all=True, namespace=store.namespace)
