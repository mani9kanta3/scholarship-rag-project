"""
The FastAPI app.

Six endpoints. Five of them are the obvious ones, and /api/eval/latest
is not: it hands out the system's own evaluation numbers, including the
ones where it does badly. Publishing your own marks in the product is a
small thing to build and it says something no README claim can.

The startup hook is the other piece worth reading. Chroma is rebuilt
from Postgres every time the app boots. Postgres holds the durable copy
of every embedding, so the index is derived data. That means a wiped
disk on a free tier restart costs a few seconds of rebuild instead of a
silently empty vector store answering every question with nothing.
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import (
    answering,
    config,
    corpus,
    db,
    eligibility,
    query_log,
    rate_limit,
    tracing,
    vector_store,
)
from .models import (
    AskRequest,
    AskResponse,
    EligibilityRequest,
    EligibilityResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the search index before the first request arrives."""
    print("Starting up. Building the Chroma index from Postgres ...")
    try:
        count = vector_store.load_from_postgres()
        if count == 0:
            print("WARNING: no chunks in Postgres. Run scripts.run_ingestion first.")
    except Exception as error:
        # Say so loudly. A vector store that failed to build looks
        # exactly like a corpus with nothing relevant in it, and that
        # is the worst kind of bug because nothing appears broken.
        print(f"WARNING: could not build the index: {error}")

    if tracing.is_enabled():
        print("Langfuse tracing is on.")

    yield

    # Langfuse sends in batches on a background thread, so whatever is
    # still queued when the process ends is lost unless it is pushed out
    # here. That matters more than it sounds: this runs on an instance
    # that sleeps after fifteen minutes idle, so without this the last
    # few traces before every single sleep would go missing, and the
    # ones just before a shutdown are often the interesting ones.
    tracing.flush()


app = FastAPI(
    title="Scholarship Eligibility Assistant",
    description=(
        "Hybrid RAG over Indian scholarship schemes. Eligibility rules are "
        "filtered in SQL, semantic search runs only inside the schemes that "
        "survive, and nothing is asserted that cannot be traced to a source."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Sentry is optional. With no DSN in the .env this does nothing at all,
# which is what I want on my laptop.
if config.SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=config.SENTRY_DSN, traces_sample_rate=0.1)


def _as_text(value):
    """Dates out of Postgres are date objects. JSON wants a string."""
    return value.isoformat() if value else None


@app.post("/api/eligibility", response_model=EligibilityResponse, dependencies=[Depends(rate_limit.limit_cheap)])
def check_eligibility(request: EligibilityRequest):
    """
    What is this student eligible for?

    No embeddings are involved. This is the SQL filter and nothing else,
    because comparing an income to a limit is arithmetic and semantic
    search has no business anywhere near it.

    Near misses come back too. "You miss this one by 0.2 CGPA" is only
    possible because the thresholds are real numbers in real columns.
    """
    profile = request.profile.model_dump()

    matches = eligibility.find_matches(profile)
    near_misses = eligibility.find_near_misses(profile)

    total = db.fetch_one("SELECT count(*) AS n FROM scheme")["n"]

    return {
        "matches": [
            {
                "id": match["id"],
                "name": match["name"],
                "provider": match["provider"],
                "description": match["description"],
                "amount_text": match["amount_text"],
                "deadline": _as_text(match["deadline"]),
                "source_url": match["source_url"],
                "match_reasons": match["match_reasons"],
                "unchecked_rules": match["unchecked_rules"],
                "unverified_fields": match["unverified_fields"],
                "extraction_confidence": float(match["extraction_confidence"]),
            }
            for match in matches
        ],
        "near_misses": near_misses,
        "total_schemes": total,
    }


@app.post(
    "/api/ask",
    response_model=AskResponse,
    dependencies=[Depends(rate_limit.limit_ask)],
)
def ask(request: AskRequest):
    """
    A free text question, answered with citations or refused honestly.

    A refusal is a normal 200 response, not an error. The frontend shows
    it as an answer, because "I cannot confirm that, here is the source
    page" is a useful thing to tell a student and hiding it would defeat
    the point of having it.
    """
    profile = request.profile.model_dump() if request.profile else None

    result = answering.answer_question(
        request.question,
        profile=profile,
        mode=request.mode,
        use_reranker=request.use_reranker,
    )

    rate_limit.spend(result.get("tokens", 0))

    return {
        "answer": result["answer"],
        "abstained": result["abstained"],
        "abstain_reason": result.get("abstain_reason"),
        "citations": result.get("citations", []),
        "warnings": result.get("warnings", []),
        "grounded": result.get("grounded"),
        "near_misses": result.get("near_misses", []),
        "eligible_count": result.get("eligible_count"),
        "top_score": float(result.get("top_score") or 0),
        "latency_ms": result["latency_ms"],
        "tokens": result.get("tokens", 0),
        "trace": result.get("trace", []),
    }


@app.get("/api/schemes", dependencies=[Depends(rate_limit.limit_cheap)])
def list_schemes(
    search: str = "",
    provider: str = "",
    state: str = "",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    Browse the corpus.

    The search runs in Postgres, not in the browser. It is only 44
    schemes today, but sending all of them to React just so React can
    filter them is the habit I do not want to build.
    """
    rows = db.fetch_all(
        """
        SELECT s.id, s.name, s.provider, s.description, s.amount_text,
               s.deadline, s.source_url, s.last_updated,
               c.categories, c.course_levels, c.states,
               c.max_family_income, c.min_percentage, c.min_cgpa,
               c.extraction_confidence
        FROM scheme s
        JOIN eligibility_criteria c ON c.scheme_id = s.id
        WHERE (%(search)s = '' OR s.name ILIKE %(like)s OR s.description ILIKE %(like)s)
          AND (%(provider)s = '' OR s.provider ILIKE %(provider_like)s)
          AND (%(state)s = '' OR c.states IS NULL OR %(state)s = ANY(c.states))
        ORDER BY s.name
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {
            "search": search,
            "like": f"%{search}%",
            "provider": provider,
            "provider_like": f"%{provider}%",
            "state": state.title() if state else "",
            "limit": limit,
            "offset": offset,
        },
    )

    for row in rows:
        row["deadline"] = _as_text(row["deadline"])
        row["last_updated"] = _as_text(row["last_updated"])
        row["extraction_confidence"] = float(row["extraction_confidence"])
        row["max_family_income"] = (
            float(row["max_family_income"]) if row["max_family_income"] is not None else None
        )
        row["min_percentage"] = (
            float(row["min_percentage"]) if row["min_percentage"] is not None else None
        )
        row["min_cgpa"] = float(row["min_cgpa"]) if row["min_cgpa"] is not None else None

    total = db.fetch_one("SELECT count(*) AS n FROM scheme")["n"]
    return {"results": rows, "count": total}


@app.get("/api/schemes/{scheme_id}", dependencies=[Depends(rate_limit.limit_cheap)])
def get_scheme(scheme_id: int):
    """One scheme, with its rules, its sections and its source link."""
    scheme = db.fetch_one(
        """
        SELECT s.*, c.min_cgpa, c.min_percentage, c.max_family_income,
               c.categories, c.genders, c.course_levels, c.states,
               c.min_age, c.max_age, c.unknown_fields,
               c.extraction_confidence, c.field_sources
        FROM scheme s
        JOIN eligibility_criteria c ON c.scheme_id = s.id
        WHERE s.id = %(id)s
        """,
        {"id": scheme_id},
    )

    if not scheme:
        raise HTTPException(status_code=404, detail="No scheme with that id.")

    scheme["deadline"] = _as_text(scheme["deadline"])
    scheme["last_updated"] = _as_text(scheme["last_updated"])
    scheme["created_at"] = str(scheme["created_at"])
    scheme["extraction_confidence"] = float(scheme["extraction_confidence"])
    for field in ["min_cgpa", "min_percentage", "max_family_income"]:
        scheme[field] = float(scheme[field]) if scheme[field] is not None else None

    scheme["sections"] = db.fetch_all(
        """
        SELECT section, chunk_text, source_page
        FROM document_chunk
        WHERE scheme_id = %(id)s
        ORDER BY id
        """,
        {"id": scheme_id},
    )

    return scheme


@app.get("/api/eval/latest", dependencies=[Depends(rate_limit.limit_cheap)])
def latest_eval():
    """
    The metrics from the most recent evaluation run.

    An unusual thing to expose in a product, and worth doing. It shows
    the naive baseline next to the hybrid system, including the places
    where the system still gets things wrong.
    """
    runs = db.fetch_all(
        """
        SELECT id, run_at, config, metrics
        FROM eval_run
        ORDER BY run_at DESC
        LIMIT 10
        """
    )

    if not runs:
        return {"runs": [], "message": "No evaluation has been run yet."}

    for run in runs:
        run["run_at"] = str(run["run_at"])

    return {"runs": runs}


@app.get("/api/corpus/stats", dependencies=[Depends(rate_limit.limit_cheap)])
def corpus_stats():
    """
    What the corpus is made of, and what chunking did to it.

    Chunking normally happens once, offline, and then every retrieval
    number in the project rests on it while nobody can see what was
    done. This endpoint exists so that it can be looked at instead of
    taken on trust.
    """
    return corpus.stats()


@app.get("/api/corpus/chunks", dependencies=[Depends(rate_limit.limit_cheap)])
def corpus_chunks(
    section: str = "",
    scheme_id: int = Query(default=None),
    search: str = "",
    split_only: bool = False,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    The chunks themselves, exactly as the retriever sees them.

    split_only narrows to chunks whose section was too long to keep
    whole, which are the only places in the corpus where one rule could
    have been cut across two chunks.
    """
    return corpus.chunks(
        section=section,
        scheme_id=scheme_id,
        search=search,
        split_only=split_only,
        limit=limit,
        offset=offset,
    )


@app.get("/api/ops/summary", dependencies=[Depends(rate_limit.limit_cheap)])
def ops_summary(days: int = Query(default=14, ge=1, le=90)):
    """
    What the service has actually been doing.

    Every answer since the first day has written a row to query_log with
    its retrieval score, its abstention reason, its latency and its
    token cost. None of this is new instrumentation. It is the
    instrumentation finally being read.
    """
    return query_log.ops_summary(days=days)


@app.get("/api/health")
def health():
    """
    Is it alive, and has it been behaving?

    The uptime ping hits this, which has the useful side effect of
    keeping a free tier instance awake so a recruiter clicking the demo
    does not wait fifty seconds for a cold start.

    The query log summary is here too. An abstention rate that suddenly
    jumps, or an eligible count stuck at zero, is something no offline
    eval would ever catch.

    It answers 200 even when the database is unreachable, and says so in
    the body instead. A container host reads this endpoint to decide
    whether a deployment succeeded, and a 500 here means the deployment
    is rolled back before anyone can read the logs that would explain
    why. "I am running and here is what is wrong" is far more useful
    during a deploy than a failure with no explanation.
    """
    try:
        return {
            "status": "ok",
            "schemes": db.fetch_one("SELECT count(*) AS n FROM scheme")["n"],
            "chunks": db.fetch_one("SELECT count(*) AS n FROM document_chunk")["n"],
            "chunks_indexed": vector_store.count(),
            # Say out loud whether tracing is actually on. Setting two
            # secrets and assuming they took is how you find out a week
            # later that nothing was ever recorded.
            "tracing": tracing.status(),
            "recent_queries": query_log.health_summary(),
        }
    except Exception as error:
        return {
            "status": "degraded",
            "problem": "the database could not be reached",
            "detail": str(error)[:200],
        }
