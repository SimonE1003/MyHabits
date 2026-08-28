"""RAG knowledge base for the Now-page planner.

Query-time contract (used by app.py /api/now_plan):
    from rag import retrieve_knowledge
    knowledge = retrieve_knowledge(habits, bedtime=..., lang=..., user_tz=...)

    knowledge -> list of {"title": str, "text": str} (possibly empty)

The returned list is passed straight into generate_plan(knowledge=...),
which renders it as the 'Reference knowledge' prompt section.

Offline build (pipeline, see DESIGN notes in build.py once implemented):
    python -m rag.build            # fetch -> chunk -> tag -> embed -> index
"""
from .retrieve import retrieve_knowledge, kb_status

__all__ = ["retrieve_knowledge", "kb_status"]
