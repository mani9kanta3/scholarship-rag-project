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

# How it is actually getting on, which is a different question from
# whether it is switched on.
#
# This exists because of a bug I only found by testing the failure path.
# The call below was written against a method name that does not exist
# in the pinned version of the library, so every trace raised, got
# swallowed by the "never break a request" rule, and printed a line into
# a log nobody reads. Tracing was on, configured, and recording nothing,
# and it would have stayed that way for as long as I did not look.
#
# So "I set the keys" is not evidence that it works. These two counters
# are, and /api/health reports them.
_sent = 0
_last_error = None


def is_enabled():
    return _enabled


def status():
    """
    What tracing is actually doing, for the health endpoint.

    "off" means no keys were given. "on" means the keys work. "failing"
    means it is configured and not working, which is the state worth
    shouting about, because it is the one that looks fine from outside.
    """
    if not config.LANGFUSE_PUBLIC_KEY or not config.LANGFUSE_SECRET_KEY:
        return {"state": "off"}

    # Asking for the client is what runs the credential check the first
    # time, so a health call made before anyone has asked a question
    # still gives a real answer rather than an optimistic one.
    get_client()

    if _last_error:
        return {"state": "failing", "sent": _sent, "last_error": _last_error}
    return {"state": "on", "sent": _sent}


def get_client():
    """Build the Langfuse client once, or return None if it will not build."""
    global _client, _enabled, _last_error

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
            # The library itself would not load or construct. Nothing
            # to report beyond that, so switch off and move on.
            print(f"Langfuse would not start, carrying on without it: {error}")
            _enabled = False
            return None

        # Check the credentials now, while something is watching.
        #
        # This is in its own try for a reason. Traces are sent in
        # batches on a background thread, so a wrong key does not raise
        # where the trace was written: it prints "401 Unauthorized" from
        # inside the exporter and the pipeline carries on believing it
        # is recording. Startup is the only moment a bad key can be
        # caught and reported honestly.
        #
        # It is also the mistake most likely to happen. Langfuse has a
        # European host and an American one, and a key pair from one is
        # rejected by the other with exactly this error.
        #
        # Note that a rejection leaves tracing enabled and marks it as
        # failing, rather than quietly switching it off. "Off" would be
        # a lie: somebody set these keys and believes they work.
        try:
            _client.auth_check()
            _last_error = None
        except Exception as error:
            _last_error = (
                "Langfuse rejected the keys. Check the pair, and check "
                f"LANGFUSE_HOST, currently {config.LANGFUSE_HOST}. "
                f"The server said: {error}"
            )
            print(_last_error)

    return _client


def record_answer(result, chunks=None, profile=None):
    """
    Write one finished question to Langfuse.

    The retrieved chunks go in as well as the answer, because "why did
    it say that" is nearly always answered by looking at what it was
    given, not at what it wrote.
    """
    global _sent, _last_error

    client = get_client()
    if client is None:
        return

    try:
        # start_as_current_observation, not start_as_current_span. The
        # second one reads better and does not exist in langfuse 4.x,
        # which is exactly the mistake described at the top of this file.
        with client.start_as_current_observation(
            name="ask",
            as_type="span",
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
                    # The stage by stage record the pipeline keeps. This
                    # is the most useful thing to have when opening a bad
                    # answer a week later, because it says which rule
                    # fired and what the numbers were, instead of leaving
                    # me to infer it from the output.
                    "trace": result.get("trace", []),
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
        _sent += 1
        _last_error = None
    except Exception as error:
        # Still swallowed, because a student's answer must not depend on
        # my observability working. But recorded, so that /api/health
        # can say it is broken instead of quietly claiming to be on.
        _last_error = str(error)
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
