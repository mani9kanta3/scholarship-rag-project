"""
Sending each answered question to Langfuse.

The query_log table next door records the numbers I want to plot: how
often the system refused, how the retrieval scores are drifting, how
long things took. Langfuse records the other half, the shape of one
particular request, so that a week later I can open a bad answer and see
what was retrieved and what went to the model.

Two rules for this file.

**It is optional.** With no keys in the .env, every function here does
nothing. Nobody should need a Langfuse account to run this project.

**It never breaks a request.** Tracing is something I do for my own
benefit. If it fails, the student still gets their answer, so everything
is wrapped and failures are printed rather than raised.

The trace is written once, at the end, with the whole finished result.
The pipeline in answering.py refuses at six different points, and
threading a live span through all of them would tangle the part of the
code I most want to stay readable.
"""

from . import config

_enabled = bool(config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY)
_client = None


def is_enabled():
    return _enabled


def get_client():
    """Build the Langfuse client once, or return None if it will not build."""
    global _client, _enabled

    if not _enabled:
        return None

    if _client is None:
        try:
            from langfuse import Langfuse

            _client = Langfuse(
                public_key=config.LANGFUSE_PUBLIC_KEY,
                secret_key=config.LANGFUSE_SECRET_KEY,
                host=config.LANGFUSE_HOST,
            )
        except Exception as error:
            print(f"Langfuse would not start, carrying on without it: {error}")
            _enabled = False
            return None

    return _client


def record_answer(result, chunks=None, profile=None):
    """
    Write one finished question to Langfuse.

    The retrieved chunks go in as well as the answer, because "why did
    it say that" is nearly always answered by looking at what it was
    given, not at what it wrote.
    """
    client = get_client()
    if client is None:
        return

    try:
        with client.start_as_current_span(
            name="ask",
            input={
                "question": result.get("question"),
                "mode": result.get("mode"),
                "profile": profile,
            },
        ) as span:
            span.update(
                output={
                    "answer": result.get("answer"),
                    "abstained": result.get("abstained"),
                    "abstain_reason": result.get("abstain_reason"),
                    "grounded": result.get("grounded"),
                },
                metadata={
                    "eligible_count": result.get("eligible_count"),
                    "top_score": result.get("top_score"),
                    "latency_ms": result.get("latency_ms"),
                    "tokens": result.get("tokens"),
                    "retrieved": [
                        {
                            "scheme_id": chunk["scheme_id"],
                            "section": chunk["section"],
                            "similarity": chunk.get("vector_similarity", chunk.get("similarity")),
                            "rerank_score": chunk.get("rerank_score"),
                        }
                        for chunk in (chunks or [])
                    ],
                },
            )
    except Exception as error:
        print(f"Langfuse trace failed, carrying on without it: {error}")


def flush():
    """
    Push anything still queued.

    Langfuse batches in the background, so a script that finishes and
    exits can lose its last few traces without this.
    """
    client = get_client()
    if client is not None:
        try:
            client.flush()
        except Exception:
            pass
