---
title: Scholarship Eligibility Assistant
emoji: 🎓
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: 6.26.0
app_file: space_app.py
pinned: false
short_description: Hybrid RAG over 44 Indian scholarship schemes, with citations
---

# Scholarship Eligibility Assistant

The API behind a hybrid RAG system over 44 Indian scholarship schemes. It
answers two things: what am I eligible for, and how do I apply for this one.

Eligibility rules are extracted from the scheme documents into typed database
columns and compared in SQL, because comparing two numbers is arithmetic and
not similarity. Semantic search runs only inside the schemes that survive that
filter. Nothing is asserted unless the number behind it can be traced back to a
source.

Interactive API docs are at `/docs`.

## Why a Gradio Space and not a Docker one

This backend needs about 700 MB of memory with PyTorch, the embedding model and
the cross-encoder loaded. Every 512 MB free tier would kill it on the first
request, and the Docker runtime here needs a paid plan. The Gradio runtime is
free and gives 16 GB, so the FastAPI app is mounted inside a small Gradio page.
Every `/api` route works exactly as it does locally.

That choice keeps the cross-encoder switched on, which matters: it means the
deployed system is the same one the evaluation measured.

## Notes

The Chroma index is not stored anywhere. PostgreSQL holds the durable copy of
every embedding and the app rebuilds the index from it at startup, in a few
seconds and with no re-embedding. So a restart that wipes the disk costs
nothing, because the vector store is derived data and Postgres is the truth.

Full project, the evaluation, and an honest write up of what it gets wrong:
<https://github.com/mani9kanta3/scholarship-rag-project>
