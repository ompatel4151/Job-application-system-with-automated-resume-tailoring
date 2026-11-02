"""Create the agent's Pinecone index once (AGENT_EXPERIMENT.md 3.2).

  ../.venv/bin/python setup_pinecone.py

Serverless on AWS us-east-1 (the only Starter region), with integrated
embedding (llama-text-embed-v2) on the "text" field, so there's no separate
embedding call or key. Does nothing if the index already exists.
"""

import common  # noqa: F401  (loads backend/.env)
from app.config import settings


def main():
    from pinecone import Pinecone

    if not settings.pinecone_api_key:
        raise SystemExit("Set PINECONE_API_KEY in backend/.env first.")
    pc = Pinecone(api_key=settings.pinecone_api_key)
    if pc.has_index(settings.pinecone_index):
        print(f"{settings.pinecone_index} already exists.")
        return
    pc.create_index_for_model(
        name=settings.pinecone_index, cloud="aws", region="us-east-1",
        embed={"model": "llama-text-embed-v2", "field_map": {"text": "text"}},
    )
    print(f"Created {settings.pinecone_index}.")


if __name__ == "__main__":
    main()
