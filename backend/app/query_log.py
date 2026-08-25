"""
Writing down what every live query did.

Nothing reads this table yet, and that is fine. It is here from day one
because it only becomes useful once it has history, and starting it a
month after launch means starting from zero.

The reason it exists is that evaluation and monitoring answer different
questions. My eval says the system worked on 40 questions I already knew
the answers to, against an index I had just built. It cannot tell me
that something broke last Tuesday. If the abstention rate jumps from 8%
to 40% overnight because half a corpus reload failed, this table is the
only place that would show it.

Logging never breaks a request. If the insert fails, the student still
gets their answer.
"""

from . import db

INSERT_SQL = """
INSERT INTO query_log
    (question, mode, eligible_count, top_retrieval_score,
     abstained, abstain_reason, grounded, latency_ms, tokens)
VALUES
    (%(question)s, %(mode)s, %(eligible_count)s, %(top_score)s,
     %(abstained)s, %(abstain_reason)s, %(grounded)s, %(latency_ms)s, %(tokens)s)
"""


def record(result):
    """Write one row from a finished answer."""
    try:
        db.execute(
            INSERT_SQL,
            {
                "question": result["question"],
                "mode": result["mode"],
                "eligible_count": result.get("eligible_count"),
                "top_score": result.get("top_score"),
                "abstained": result["abstained"],
                "abstain_reason": result.get("abstain_reason"),
                "grounded": result.get("grounded"),
                "latency_ms": result.get("latency_ms"),
                "tokens": result.get("tokens"),
            },
        )
    except Exception as error:
        # Deliberately swallowed. A monitoring write must never be the
        # reason a student does not get an answer.
        print(f"query_log write failed: {error}")


def recent(limit=100):
    """The last few queries, newest first. For the health endpoint."""
    return db.fetch_all(
        """
        SELECT asked_at, question, mode, eligible_count, top_retrieval_score,
               abstained, abstain_reason, grounded, latency_ms, tokens
        FROM query_log
        ORDER BY asked_at DESC
        LIMIT %(limit)s
        """,
        {"limit": limit},
    )


def health_summary(limit=200):
    """
    The numbers worth watching, over the last few hundred queries.

    An abstention rate that suddenly climbs, or a top score that drifts
    down, or an eligible_count stuck at zero, each mean something
    different has broken. Offline evals catch none of them.
    """
    row = db.fetch_one(
        """
        SELECT
            count(*)                                   AS queries,
            avg(CASE WHEN abstained THEN 1.0 ELSE 0 END) AS abstain_rate,
            avg(top_retrieval_score)                   AS mean_top_score,
            avg(latency_ms)                            AS mean_latency_ms,
            avg(CASE WHEN eligible_count = 0 THEN 1.0 ELSE 0 END) AS zero_eligible_rate
        FROM (
            SELECT * FROM query_log ORDER BY asked_at DESC LIMIT %(limit)s
        ) AS recent_queries
        """,
        {"limit": limit},
    )

    if not row or not row["queries"]:
        return {"queries": 0}

    return {
        "queries": row["queries"],
        "abstain_rate": round(float(row["abstain_rate"] or 0), 3),
        "mean_top_score": round(float(row["mean_top_score"] or 0), 3),
        "mean_latency_ms": int(row["mean_latency_ms"] or 0),
        "zero_eligible_rate": round(float(row["zero_eligible_rate"] or 0), 3),
    }
