"""Pinecone, with the namespace fixed to one user (AGENT_EXPERIMENT.md 3.2).

Pinecone has no row-level security: one API key can read every namespace. So
a UserStore is only ever built from the verified token's user id, nothing the
model or the request body says can choose another namespace, and every record
also carries user_id, which is checked again on the way out.
"""

import functools
import logging
import uuid

from app import observability
from app.config import settings

log = logging.getLogger(__name__)

# Integrated-embedding indexes accept at most 96 records per upsert.
_BATCH = 96


@functools.cache
def _pinecone_index():
    from pinecone import Pinecone

    pc = Pinecone(api_key=settings.pinecone_api_key)
    return pc.Index(host=pc.describe_index(settings.pinecone_index).host)


def _index():
    return _pinecone_index() if settings.pinecone_api_key else None


class UserStore:
    def __init__(self, index, user_id: uuid.UUID):
        self._index = index
        self.namespace = str(user_id)

    def upsert(self, kind: str, records: dict[str, dict]) -> None:
        """records: id -> fields, including the "text" that gets embedded."""
        rows = [
            {**fields, "_id": f"{kind}:{rid}", "type": kind, "user_id": self.namespace}
            for rid, fields in records.items()
        ]
        for start in range(0, len(rows), _BATCH):
            self._index.upsert_records(namespace=self.namespace, records=rows[start:start + _BATCH])

    def delete(self, kind: str, ids) -> None:
        ids = [f"{kind}:{i}" for i in ids]
        if ids:
            self._index.delete(ids=ids, namespace=self.namespace)

    def search(self, kind: str, text: str, k: int) -> list[tuple[str, dict]]:
        """(id, fields) of the k closest records of this kind, best first."""
        response = self._index.search(
            namespace=self.namespace, top_k=k, inputs={"text": text},
            filter={"type": {"$eq": kind}},
        )
        found = []
        for hit in response.result.hits:
            if hit.fields.get("user_id") != self.namespace:
                # Shouldn't be possible; if it happens, drop it and make noise.
                observability.VECTOR_FOREIGN_HITS.inc()
                log.error("dropped a search hit owned by another user", extra={"record": hit.id})
                continue
            found.append((hit.id.split(":", 1)[1], hit.fields))
        return found


def store_for(user_id: uuid.UUID) -> UserStore | None:
    """The caller's store, or None when Pinecone isn't configured."""
    index = _index()
    return UserStore(index, user_id) if index is not None else None


def index_facts(user_id: uuid.UUID, facts, removed=()) -> bool:
    """Best effort: True if the index now matches the sheet."""
    store = store_for(user_id)
    if store is None:
        return False
    try:
        store.delete("fact", removed)
        store.upsert("fact", {f.fact_id: {"text": fact_text(f)} for f in facts})
        return True
    except Exception:
        observability.VECTOR_ERRORS.inc()
        log.warning("couldn't index facts", exc_info=True)
        return False


def fact_text(fact) -> str:
    """What gets embedded: the fact plus its tools, so a search for "Redis"
    finds a fact that only lists Redis as a tool."""
    tools = ", ".join(fact.tools)
    return f"{fact.text} Tools: {tools}" if tools else fact.text
