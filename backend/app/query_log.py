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

from . import config, db

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


# Grouping the refusal reasons.
#
# Two of the six carry detail in the text: layer 1 names the figures it
# could not trace, and the judge quotes the claim it could not back. So
# grouping on the raw column would give one bucket per refusal and tell
# nobody anything. These two patterns fold them back into their rule.
REASON_GROUP = """
    CASE
        WHEN abstain_reason LIKE 'layer 1 failed%%'
            THEN 'layer 1: a figure with no source behind it'
        WHEN abstain_reason LIKE 'judge rejected%%'
            THEN 'layer 2: the judge could not back a claim'
        ELSE abstain_reason
    END
"""


def ops_summary(days=14):
    """
    What the service has actually been doing, for the ops page.

    Everything here reads the query log, which has been written on every
    answer since the first day. None of it is new instrumentation; it is
    the instrumentation finally being looked at.

    The percentiles matter more than the mean. One cold start on a free
    instance that sleeps can drag a mean latency up by seconds and make
    a perfectly healthy service look broken, which is exactly the kind
    of false alarm that teaches people to ignore dashboards.
    """
    window = {"days": days}

    totals = db.fetch_one(
        """
        SELECT count(*)                                          AS queries,
               avg(CASE WHEN abstained THEN 1.0 ELSE 0 END)      AS abstain_rate,
               avg(CASE WHEN grounded THEN 1.0 ELSE 0 END)       AS grounded_rate,
               avg(top_retrieval_score)                          AS mean_top_score,
               sum(tokens)                                       AS tokens,
               avg(latency_ms)                                   AS mean_latency_ms,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms)  AS p50_latency_ms,
               PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms
        FROM query_log
        WHERE asked_at >= NOW() - (%(days)s || ' days')::interval
        """,
        window,
    )

    by_day = db.fetch_all(
        """
        SELECT asked_at::date                                    AS day,
               count(*)                                          AS queries,
               avg(CASE WHEN abstained THEN 1.0 ELSE 0 END)      AS abstain_rate,
               avg(top_retrieval_score)                          AS mean_top_score,
               sum(tokens)                                       AS tokens,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_latency_ms
        FROM query_log
        WHERE asked_at >= NOW() - (%(days)s || ' days')::interval
        GROUP BY 1
        ORDER BY 1
        """,
        window,
    )

    reasons = db.fetch_all(
        f"""
        SELECT {REASON_GROUP} AS reason, count(*) AS times
        FROM query_log
        WHERE abstained
          AND asked_at >= NOW() - (%(days)s || ' days')::interval
        GROUP BY 1
        ORDER BY count(*) DESC
        """,
        window,
    )

    today = db.fetch_one(
        """
        SELECT COALESCE(sum(tokens), 0) AS tokens, count(*) AS queries
        FROM query_log
        WHERE asked_at >= CURRENT_DATE
        """
    )

    def number(value, places=3):
        return round(float(value or 0), places)

    return {
        "days": days,
        "queries": totals["queries"] or 0,
        "abstain_rate": number(totals["abstain_rate"]),
        "grounded_rate": number(totals["grounded_rate"]),
        "mean_top_score": number(totals["mean_top_score"]),
        "tokens": int(totals["tokens"] or 0),
        "latency_ms": {
            "mean": int(totals["mean_latency_ms"] or 0),
            "p50": int(totals["p50_latency_ms"] or 0),
            "p95": int(totals["p95_latency_ms"] or 0),
        },
        "today": {
            "queries": today["queries"] or 0,
            "tokens": int(today["tokens"] or 0),
            "budget": config.DAILY_TOKEN_BUDGET,
        },
        "by_day": [
            {
                "day": row["day"].isoformat(),
                "queries": row["queries"],
                "abstain_rate": number(row["abstain_rate"]),
                "mean_top_score": number(row["mean_top_score"]),
                "tokens": int(row["tokens"] or 0),
                "p50_latency_ms": int(row["p50_latency_ms"] or 0),
            }
            for row in by_day
        ],
        "abstain_reasons": [dict(row) for row in reasons],
    }
