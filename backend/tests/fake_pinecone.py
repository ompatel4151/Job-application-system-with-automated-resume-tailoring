"""An in-memory stand-in for a Pinecone index with integrated embedding.

It records every call, so tests can check which namespace each one used.
Search scores records by shared words, which is enough to rank a fact about
"Redis" above one about "Flask" for the query "Redis".
"""

import re
from types import SimpleNamespace


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9#+]+", text.lower()))


class FakeIndex:
    def __init__(self):
        self.namespaces: dict[str, dict[str, dict]] = {}
        self.calls: list[tuple[str, str]] = []  # (method, namespace)

    def upsert_records(self, *, namespace, records, timeout=None):
        self.calls.append(("upsert_records", namespace))
        space = self.namespaces.setdefault(namespace, {})
        for record in records:
            space[record["_id"]] = {k: v for k, v in record.items() if k != "_id"}

    def delete(self, *, ids=None, namespace="", delete_all=False, filter=None, timeout=None):
        self.calls.append(("delete", namespace))
        space = self.namespaces.get(namespace, {})
        for i in ids or []:
            space.pop(i, None)

    def search(self, *, namespace, top_k=None, inputs=None, filter=None, fields=None, **_):
        self.calls.append(("search", namespace))
        query = _words(inputs["text"])
        hits = []
        for rid, record in self.namespaces.get(namespace, {}).items():
            if filter and any(record.get(k) != v["$eq"] for k, v in filter.items()):
                continue
            score = len(query & _words(record.get("text", "")))
            if score:
                hits.append(SimpleNamespace(id=rid, score=float(score), fields=dict(record)))
        hits.sort(key=lambda h: -h.score)
        return SimpleNamespace(result=SimpleNamespace(hits=hits[:top_k]))


class BrokenIndex:
    """Pinecone being down: every call raises."""

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise ConnectionError("pinecone unreachable")
        return fail
