# Architecture notes

This file is the map of the code. The README says what the project does and why;
this one says which file does what, and what calls what. Nothing here is meant
for GitHub's front page. It is for me six months from now, and for anyone who
opens the repo and wants to know where a change belongs.

---

## 1. The shape of the whole thing

There are two halves and they never run at the same time.

**Offline (ingestion).** Runs on my machine, by hand, when the corpus changes.
Reads 44 markdown files, asks an LLM to pull eligibility rules out of each one,
checks that work, chunks the text, embeds it, and writes everything to Postgres.

**Online (serving).** FastAPI. Never calls the extractor, never embeds a
document. It only reads what ingestion wrote, plus one embedding per question.

The thing joining them is Postgres. Both the structured criteria and the raw
chunk embeddings live there, which is why the vector index can be thrown away
and rebuilt at any time.

```
data/raw/*.md
     |
     |  scripts/run_ingestion.py          (offline, run by hand)
     v
ingestion/load_documents.py    parse the markdown into header + sections
ingestion/extract_criteria.py  LLM fills the criteria columns
ingestion/criteria_schema.py     the shape it must return
ingestion/verify.py              check every quote against the document
ingestion/chunker.py           one chunk per section
ingestion/injection_scan.py    flag prompt-injection phrases
app/embeddings.py              384-dim vectors
     |
     v
  Postgres  (scheme, eligibility_criteria, document_chunk)
     |
     |  app/vector_store.py load_from_postgres()   at every app startup
     v
  Chroma index  (derived, disposable)


browser  ->  frontend/src/api.js  ->  app/main.py
                                          |
                                    app/answering.py      the pipeline
                                      |    |      |
                       app/eligibility.py  |   app/generation.py -> app/llm.py
                       app/retrieval.py ---+   app/grounding.py  -> app/llm.py
                         app/vector_store.py
                         app/reranker.py
                                          |
                              app/query_log.py + app/tracing.py
```

---

## 2. The request path, in order

This is the sequence for `POST /api/ask`. Reading these seven files in this
order explains the system.

1. **`app/main.py`** takes the request. Pydantic has already validated it
   (`app/models.py`), so the body is known good before any of my code runs.
2. **`app/answering.py`** — `answer_question()`. The controller. Every
   abstention rule lives in this one function on purpose, so refusal can be read
   top to bottom in one place.
3. **`app/eligibility.py`** — `find_matches()`. One SQL query, run **first**.
   Arithmetic comparison of real columns, no embeddings. Returns the scheme ids
   the vector search is then allowed to look inside.
4. **`app/retrieval.py`** — `route()` picks naive or hybrid, then searches.
   Hybrid passes the scheme ids from step 3 down into the vector search as a
   filter.
5. **`app/reranker.py`** re-scores the ~20 survivors with a cross encoder.
   Off in the Render deployment (no torch), on in the Space and locally.
6. **`app/generation.py`** builds the prompt, fencing every chunk in a
   `<source>` block, and calls **`app/llm.py`**.
7. **`app/grounding.py`** checks the answer. Layer 1 (regex, free) first, then
   Layer 2 (LLM judge) only if needed. Back in `answering.py`, a failure here
   turns the answer into a refusal.

Then `app/query_log.py` writes a row and `app/tracing.py` sends a trace. Neither
can break the request.

---

## 3. Backend, file by file

### `backend/app/` — the serving application

| File | What it does | Who calls it |
|---|---|---|
| `main.py` | The FastAPI app. Six endpoints. Rebuilds the Chroma index from Postgres in the startup lifespan hook. | uvicorn / `space_app.py` |
| `models.py` | Pydantic request and response shapes. Every profile field optional. | `main.py` |
| `answering.py` | The query pipeline and all six abstention rules. | `main.py`, `scripts/ask.py`, `eval/run_eval.py` |
| `eligibility.py` | The SQL filter, the per-scheme explanation, failed rules, near misses. | `answering.py`, `main.py`, `retrieval.py` |
| `retrieval.py` | naive vs hybrid, question routing, named-scheme detection. | `answering.py` |
| `vector_store.py` | Chroma behind `upsert()` / `search()`. Plus `load_from_postgres()`. | `retrieval.py`, `main.py`, `run_ingestion.py` |
| `embeddings.py` | bge-small-en-v1.5, through sentence-transformers **or** fastembed/ONNX depending on `EMBEDDING_BACKEND`. | `retrieval.py`, `run_ingestion.py` |
| `reranker.py` | Cross encoder over the retrieved chunks. Switchable. | `retrieval.py` |
| `generation.py` | System prompt, `<source>` fencing, profile description. | `answering.py` |
| `grounding.py` | Layer 1 number/date check, Layer 2 judge. | `answering.py` |
| `numbers.py` | Parses Indian number formats (2,50,000 / 2.5 lakh / INR Rs.) into floats, and dates. | `grounding.py`, `ingestion/verify.py` |
| `llm.py` | The only file that talks to Groq or Gemini. Retries, JSON validation, token counting. | `generation.py`, `grounding.py`, `extract_criteria.py`, `eval/judge.py` |
| `db.py` | psycopg2 helpers. Every call opens and closes its own connection. | everything that touches Postgres |
| `config.py` | All settings read once from `.env`. Fails loudly at startup if a required one is missing. | everything |
| `query_log.py` | Writes one row per live query. Nothing reads it yet, by design. | `answering.py` |
| `tracing.py` | Langfuse, optional, never raises. | `answering.py` |
| `schema.sql` | Six tables. See section 5. | `scripts/create_tables.py` |

Two files are deliberately thin wrappers around a swappable thing:
`vector_store.py` hides Chroma, `llm.py` hides the provider. Changing either is
a config change, not a refactor. `embeddings.py` is the same idea applied to the
runtime rather than the vendor.

### `backend/ingestion/` — the offline pipeline

| File | What it does |
|---|---|
| `load_documents.py` | Parses `data/raw/*.md` into `{header fields, sections}`. Has a PDF path too. |
| `criteria_schema.py` | The Pydantic shape the model must return. Every value field is paired with a `*_quote` field. |
| `extract_criteria.py` | The extraction prompt and the call. Caches results to `data/extractions/*.json` so a re-run costs nothing. |
| `verify.py` | The check on the model. Is the quote really in the document, and does that quote really contain the value? Failures go to `unknown_fields`, they are not dropped. |
| `chunker.py` | One chunk per section. Splits only when a section is too long. |
| `injection_scan.py` | Phrase-list scan for prompt injection, run once at ingestion rather than per query. |

`criteria_schema.py` -> `extract_criteria.py` -> `verify.py` is the three-layer
defence: force the shape, demand a quote, check the quote.

### `backend/scripts/` — things I run by hand

| Command | What it does |
|---|---|
| `python -m scripts.create_tables [--reset]` | Creates the database and tables. Run first. |
| `python -m scripts.run_ingestion` | The whole offline pipeline. Truncates and restarts ids, so scheme 17 is always the same scheme. Writes `data/review/extraction_review.md`. |
| `python -m scripts.ask "..." [--naive]` | Ask from the terminal and see the parts the API hides: filtered schemes, retrieval scores, refusal reasons. |
| `python -m scripts.compare_retrieval` | Shows what the SQL filter changes. No LLM involved, so it is free to run. |
| `python -m scripts.load_eval_results` | Copies `data/eval/metrics.json` into `eval_run` so a fresh deployment can serve `/api/eval/latest`. |

### `backend/eval/` — the measurement

| File | What it does |
|---|---|
| `questions.py` | The 40 hand-written questions. 12 eligibility, 12 threshold, detail, trap. Each carries a `why_it_exists` line. |
| `load_questions.py` | Writes them into `eval_question`. Replaces the lot each time. |
| `run_eval.py` | Runs three configs — `naive`, `hybrid_no_reranker`, `hybrid` — and writes `data/eval/results_*.json` and `metrics.json`. Resumable. |
| `judge.py` | The LLM that decides correctness, because string matching cannot. |
| `calibrate_judge.py` | Checks the judge against 20 of my own hand labels. `--prepare`, grade by hand into `data/eval/hand_labels.md`, then run again for the agreement rate. |
| `ragas_eval.py` | Faithfulness, answer relevancy, context precision, context recall. Standard names from a library instead of four metrics I invented. `--runs 3` reports the spread. |
| `regrade_traps.py` | Re-grades trap questions from answers already on disk, instead of re-running the whole eval. |

The three configs exist so the comparison table has a real before-number, and so
"did the reranker help" has a measurement instead of an opinion.

### `backend/tests/` — pytest

`conftest.py` writes three synthetic schemes (names prefixed `TEST `) with
thresholds I chose, and deletes them after. Real corpus values could move under
a test that asserts 74.9% fails a 75% cutoff.

- `test_eligibility.py` (13) — boundary cases on the SQL filter.
- `test_grounding.py` (13) — Layer 1 catching invented numbers and dates.
- `test_numbers.py` (10) — the Indian number formats.
- `test_verify.py` (12) — quote-in-document and value-in-quote.

---

## 4. Frontend, file by file

React 19 + Vite + React Router 7 + Bootstrap 5. `axios` for calls.

| File | What it is |
|---|---|
| `main.jsx` | Mount point. Pulls in the Bootstrap CSS. |
| `App.jsx` | The routes. Everything nests inside `Layout`. |
| `Layout.jsx` | Navbar on top, `<Outlet />` below. |
| `Navbar.jsx` | Top bar. `NavLink` for the four page links so the active one is known. |
| `Home.jsx` | Landing page. States what the tool will not do, on purpose. |
| `Eligibility.jsx` | Profile in, matched schemes and near misses out. Calls `/api/eligibility`. |
| `Ask.jsx` | The question page. Calls `/api/ask`, renders citations and refusals. |
| `Schemes.jsx` | Browse and search, with debounced input and paging. |
| `SchemeDetail.jsx` | One scheme, from `/api/schemes/{id}`. |
| `Evaluation.jsx` | Shows the system's own eval numbers from `/api/eval/latest`, bad ones included. |
| `NotFound.jsx` | Anything else. |
| `ProfileForm.jsx` | The shared profile form. Used by both `Eligibility` and `Ask`. |
| `PageHeader.jsx` | The title strip all five pages were repeating. |
| `api.js` | One axios instance. Longer timeout, because a question goes through retrieval, a reranker and an LLM. |
| `errorMessage.js` | Turns FastAPI's several error shapes into one plain sentence. |
| `money.js` | `toLocaleString("en-IN")`, so 2,50,000 and not 250,000. Plus `inWords`. |
| `options.js` | The fixed dropdown lists. Values match what the database stores exactly. |
| `useDebounce.js` | Stops the browse page firing a request per keystroke. |

Shared-component chain: `Eligibility.jsx` and `Ask.jsx` both render
`ProfileForm.jsx`, which reads its lists from `options.js` and formats rupees
with `money.js`. `Schemes.jsx` and `SchemeDetail.jsx` both use `money.js`. Every
page that calls the API uses `api.js` and `errorMessage.js`.

---

## 5. The database

Six tables in `backend/app/schema.sql`.

- **`scheme`** — one row per document. Name, provider, description, amount text
  (free text, amounts are messy), deadline, source URL, local file, last updated.
- **`eligibility_criteria`** — one row per scheme, `UNIQUE` on `scheme_id`. The
  real columns the SQL filter compares: `min_cgpa`, `min_percentage`,
  `max_family_income`, `categories[]`, `genders[]`, `course_levels[]`,
  `states[]`, `min_age`, `max_age`. Plus the honesty columns: `field_sources`
  (JSONB, the quote per field), `unknown_fields[]`, `extraction_confidence`,
  `hand_checked`. **NULL means the scheme sets no limit, so NULL always passes.**
  A value we could not read is not NULL — it is in `unknown_fields`.
- **`document_chunk`** — chunk text, section label, page, the 384-float
  `embedding` as JSONB, and the injection flag. This is the durable copy of the
  vectors; Chroma is built from it.
- **`eval_question`** — the 40 questions, with `why_it_exists`.
- **`eval_run`** — config + metrics per run. Read by `/api/eval/latest`.
- **`query_log`** — one row per live query, indexed on `asked_at`.

---

## 6. The API surface

| Endpoint | Handler | Notes |
|---|---|---|
| `POST /api/eligibility` | `main.check_eligibility` | Pure SQL. No LLM, no embeddings. |
| `POST /api/ask` | `main.ask` | The full pipeline. |
| `GET /api/schemes` | `main.list_schemes` | search / provider / state / limit / offset. |
| `GET /api/schemes/{id}` | `main.get_scheme` | |
| `GET /api/eval/latest` | `main.latest_eval` | Serves the project's own marks. |
| `GET /api/health` | `main.health` | Render's health check path. |

---

## 7. Deployment and the config that changes with it

| File | What it configures |
|---|---|
| `render.yaml` | The Render web service. Installs `requirements-serve.txt`, sets `EMBEDDING_BACKEND=onnx` and `RERANKER_ENABLED=false`. Secrets are `sync: false` — set in the dashboard, never in git. |
| `backend/space_app.py` | The Hugging Face Space entry point. Mounts a small Gradio page at `/` on top of the real FastAPI app; everything under `/api` still reaches FastAPI. Not named `app.py` because the `app` package sits next to it. |
| `backend/Dockerfile`, `.dockerignore` | Container build. |
| `backend/SPACE_README.md` | The Space's own card. |
| `frontend/vercel.json` | SPA rewrite — every path to `index.html`, so React Router owns the routing. |
| `.env.example`, `frontend/.env.example` | The keys each side needs. |
| `backend/pytest.ini` | Test config. |

Three requirements files, and the split is the whole deployment story:

- `requirements.txt` — development. torch, sentence-transformers, the cross
  encoder. Around 700 MB in memory.
- `requirements-serve.txt` — production on a 512 MB tier. fastembed/ONNX instead
  of torch. Around 300 MB. Same weights, so the embeddings already in Postgres
  stay valid.
- `requirements-eval.txt` — RAGAS and its LangChain bits, only needed to run the
  evaluation.

---

## 8. Data directories

| Path | What lives there |
|---|---|
| `data/raw/` | The 44 scheme documents. The input to everything. |
| `data/extractions/` | Cached LLM extractions, one JSON per document. Committed on purpose — re-running ingestion costs no tokens, and a fresh clone reproduces the same database. |
| `data/review/` | `extraction_review.md` is generated by ingestion; `extraction_review_checked.md` is the copy I went through by hand. |
| `data/eval/` | `results_*.json` per config, `metrics.json` (what the API serves), `ragas_hybrid.json`, `judge_calibration.json`, `hand_labels.md`. |

---

## 9. Where to make a change

- **New scheme document** — drop the markdown in `data/raw/`, re-run
  `scripts.run_ingestion`, check the generated review file.
- **New eligibility field** — `criteria_schema.py`, `schema.sql`, `verify.py`,
  then the SQL in `eligibility.py`, then `options.js` and `ProfileForm.jsx` on
  the frontend.
- **Swap the vector store** — `vector_store.py` only.
- **Swap the LLM provider** — `llm.py` only, plus `LLM_PROVIDER` in `.env`.
- **Change a refusal rule** — `answering.py`, one function.
- **Change what is checked in an answer** — `grounding.py`.
- **New API endpoint** — `models.py` for the shapes, `main.py` for the route.
- **New page** — a component in `frontend/src/`, a route in `App.jsx`, a link in
  `Navbar.jsx`.
