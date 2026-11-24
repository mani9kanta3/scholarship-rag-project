"""
Rate limiting, written by hand instead of installed.

The API is public now, and /api/ask spends money on every call. Nothing
stops one person, or one script, from emptying the day's model quota
before anybody else gets to try the demo.

**Two different things are being protected, so there are two kinds of
limit.**

The first is the service. Somebody hammering the endpoint should be
slowed down, so there is a per address limit on how many questions can
be asked per minute and per hour. That is counted in memory.

The second is the quota, and this is the one worth reading. The Groq
free tier is counted in *tokens per day*, not requests per day, so a
request limit is the wrong shape for it: twenty long questions can cost
more than a hundred short ones. query_log already records the tokens
every answer used, so the daily spend is a single SUM over a table I am
already writing to, against an index that already exists. The budget is
therefore in the same unit as the real limit.

When the token budget runs out, /api/ask stops and says so plainly.
/api/eligibility keeps working, because it is pure SQL and never calls a
model at all. A visitor who arrives after the budget is gone can still
get a real eligibility answer, which is most of the product.

**What this is not.** The counters live in this process, so they reset
when the service restarts and they would not be shared between workers.
That is correct here, because the free instance runs a single worker and
sleeps when idle anyway. With more than one worker these counts belong
in Redis, and the token budget would already be right since it reads
from Postgres.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from . import config, db

# address -> the times it was last seen, newest at the right
_hits = defaultdict(deque)

# The token spend for today, and when it was last read. Reading it on
# every request would add a query to the slowest endpoint, so it is
# refreshed at most once a minute and treated as good enough. Going a
# little over the budget between refreshes does not matter; going over
# it by thousands would, and cannot happen at these request limits.
_tokens_today = 0
_tokens_read_at = 0.0
TOKEN_RECHECK_SECONDS = 60


def client_key(request: Request):
    """
    Work out who is asking.

    Render puts a proxy in front of the app, so request.client.host is
    the proxy for every visitor and would rate limit the whole world as
    one person. The real address is the first entry in X-Forwarded-For.

    A header can be forged, so this is not a security control. It is
    enough to stop ordinary hammering, and the token budget below is the
    part that actually protects the quota no matter who is asking.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _too_many(key, limit, window_seconds):
    """
    A sliding window count.

    Returns how many seconds to wait, or 0 when the request is fine.
    Old timestamps are dropped on the way past, which keeps the memory
    in proportion to recent traffic instead of total traffic.
    """
    now = time.time()
    seen = _hits[key]

    while seen and now - seen[0] > window_seconds:
        seen.popleft()

    if len(seen) >= limit:
        return int(window_seconds - (now - seen[0])) + 1

    seen.append(now)
    return 0


def tokens_used_today():
    """
    Today's model spend, in tokens, from the query log.

    Cached for a minute. If the query fails the answer is 0, which lets
    requests through: a monitoring query breaking is not a good reason
    to take the service down.
    """
    global _tokens_today, _tokens_read_at

    now = time.time()
    if now - _tokens_read_at < TOKEN_RECHECK_SECONDS:
        return _tokens_today

    try:
        row = db.fetch_one(
            """
            SELECT COALESCE(SUM(tokens), 0) AS total
            FROM query_log
            WHERE asked_at >= CURRENT_DATE
            """
        )
        _tokens_today = int(row["total"]) if row else 0
    except Exception:
        _tokens_today = 0

    _tokens_read_at = now
    return _tokens_today


def spend(tokens):
    """
    Add what an answer just cost, without waiting for the next refresh.

    Without this the budget would lag by up to a minute, which is long
    enough for a burst to overshoot it.
    """
    global _tokens_today
    _tokens_today += int(tokens or 0)


def limit_ask(request: Request):
    """
    The limit for the endpoint that calls a model.

    A FastAPI dependency, so it runs before the handler and raises 429
    with Retry-After, which is the header a well behaved client reads
    before trying again.
    """
    if not config.RATE_LIMIT_ENABLED:
        return

    if tokens_used_today() >= config.DAILY_TOKEN_BUDGET:
        raise HTTPException(
            status_code=429,
            detail=(
                "This demo has used its model budget for today. Eligibility "
                "checking still works, because it runs in SQL and does not "
                "call a model. Questions will work again tomorrow."
            ),
        )

    key = client_key(request)

    wait = _too_many(f"ask-minute:{key}", config.ASK_PER_MINUTE, 60)
    if not wait:
        wait = _too_many(f"ask-hour:{key}", config.ASK_PER_HOUR, 3600)

    if wait:
        raise HTTPException(
            status_code=429,
            detail="Too many questions in a short time. Please wait a moment.",
            headers={"Retry-After": str(wait)},
        )


def limit_cheap(request: Request):
    """
    The limit for the endpoints that only read Postgres.

    Much looser, because these cost a few milliseconds of database time
    and nothing else. This is here to stop a loop, not to ration.
    """
    if not config.RATE_LIMIT_ENABLED:
        return

    wait = _too_many(f"cheap:{client_key(request)}", config.CHEAP_PER_MINUTE, 60)
    if wait:
        raise HTTPException(
            status_code=429,
            detail="Too many requests in a short time. Please wait a moment.",
            headers={"Retry-After": str(wait)},
        )
