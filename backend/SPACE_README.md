---
title: Scholarship Eligibility Assistant API
emoji: 🎓
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 8000
pinned: false
---

# Scholarship Eligibility Assistant — API

The FastAPI backend for a hybrid RAG system over 44 Indian scholarship schemes.
Eligibility rules are filtered in SQL, semantic search runs only inside the
schemes that survive, and nothing is asserted that cannot be traced to a source.

Full project, including the evaluation and the write up:
<https://github.com/mani9kanta3/scholarship-rag-project>

## Endpoints

| Endpoint | What it does |
|---|---|
| `POST /api/eligibility` | Profile in, matching schemes with reasons and near misses out. No model involved. |
| `POST /api/ask` | Free text question. Answer with citations, or an honest refusal. |
| `GET /api/schemes` | Browse and filter the corpus. |
| `GET /api/schemes/{id}` | One scheme, its rules, and the sentence each rule was read from. |
| `GET /api/eval/latest` | This system's own evaluation numbers, including the bad ones. |
| `GET /api/health` | Uptime ping plus the live query log summary. |

Interactive docs are at `/docs`.

## Notes on this deployment

The Chroma index is not stored anywhere. Postgres holds the durable copy of
every embedding, and the app rebuilds the index from it at startup, which takes
a few seconds and costs nothing because no re-embedding happens. That is the
answer to "what happens when your vector store dies": nothing is lost, because
the vector store is derived data.

This Space is a copy of the `backend/` folder from the GitHub repository above.
The repository is the source of truth.
