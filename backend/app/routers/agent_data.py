"""The fact sheet and the agent's memories (AGENT_EXPERIMENT.md 3.1, 3.3)."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import models, vectorstore
from app.auth import CurrentUser
from app.database import get_db, get_owned
from app.schemas import Fact, FactSheet, FactsSaved, MemoryCreate, MemoryOut

router = APIRouter(prefix="/api", tags=["agent"])


def user_facts(db: Session, user) -> list[models.ResumeFact]:
    return (
        db.query(models.ResumeFact)
        .filter(models.ResumeFact.user_id == user)
        .order_by(models.ResumeFact.id)
        .all()
    )


def fact_out(row: models.ResumeFact) -> Fact:
    return Fact(id=row.fact_id, text=row.text, numbers=row.numbers, tools=row.tools, context=row.context)


@router.get("/facts", response_model=list[Fact])
def list_facts(user: CurrentUser, db: Session = Depends(get_db)):
    return [fact_out(r) for r in user_facts(db, user)]


@router.post("/facts", response_model=FactsSaved, status_code=201)
def replace_facts(payload: FactSheet, user: CurrentUser, db: Session = Depends(get_db)):
    """Replaces the caller's whole sheet. Postgres is the source of truth;
    Pinecone indexing is best effort and reported as `indexed`."""
    old = {r.fact_id for r in user_facts(db, user)}
    db.query(models.ResumeFact).filter(models.ResumeFact.user_id == user).delete()
    rows = [
        models.ResumeFact(user_id=user, fact_id=f.id, text=f.text, numbers=f.numbers,
                          tools=f.tools, context=f.context)
        for f in payload.facts
    ]
    db.add_all(rows)
    db.commit()
    indexed = vectorstore.index_facts(user, rows, removed=old - {r.fact_id for r in rows})
    return FactsSaved(saved=len(rows), indexed=indexed)


@router.delete("/facts/{fact_id}", status_code=204)
def delete_fact(fact_id: str, user: CurrentUser, db: Session = Depends(get_db)):
    deleted = (
        db.query(models.ResumeFact)
        .filter(models.ResumeFact.user_id == user, models.ResumeFact.fact_id == fact_id)
        .delete()
    )
    if not deleted:
        raise HTTPException(404, "Fact not found")
    db.commit()
    vectorstore.index_facts(user, [], removed=[fact_id])
    return Response(status_code=204)


@router.get("/memories", response_model=list[MemoryOut])
def list_memories(user: CurrentUser, db: Session = Depends(get_db)):
    # ponytail: no pagination; memories are a short list of preferences.
    return (
        db.query(models.AgentMemory)
        .filter(models.AgentMemory.user_id == user)
        .order_by(models.AgentMemory.created_at.desc(), models.AgentMemory.id.desc())
        .limit(100)
        .all()
    )


@router.post("/memories", response_model=MemoryOut, status_code=201)
def create_memory(payload: MemoryCreate, user: CurrentUser, db: Session = Depends(get_db)):
    memory = models.AgentMemory(user_id=user, text=payload.text)
    db.add(memory)
    db.commit()
    return memory


@router.delete("/memories/{memory_id}", status_code=204)
def delete_memory(memory_id: int, user: CurrentUser, db: Session = Depends(get_db)):
    db.delete(get_owned(db, models.AgentMemory, memory_id, user, "Memory"))
    db.commit()
    return Response(status_code=204)
