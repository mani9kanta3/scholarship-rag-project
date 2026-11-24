"""
Tests for the rate limiter.

Two of these are about the counting, which is easy to get subtly wrong
in a sliding window, and two are about the design decision I actually
care about: when the day's model budget is gone, questions stop but
eligibility checking does not. Eligibility runs in SQL and never calls a
model, so there is no reason for it to go down with the quota, and a
visitor who arrives late still gets most of the product.

That rule is the kind of thing that is obvious while writing it and
quietly broken six months later by someone tidying the decorators. So it
is a test rather than a comment.
"""

import time

import pytest
from fastapi.testclient import TestClient

from app import config, rate_limit


@pytest.fixture(autouse=True)
def clean_counters():
    """Every test starts with nothing counted against it."""
    rate_limit._hits.clear()
    rate_limit._tokens_today = 0
    rate_limit._tokens_read_at = time.time()  # stop it re-reading the database
    yield
    rate_limit._hits.clear()


@pytest.fixture
def limits_on(monkeypatch):
    """Turn limiting on, with small numbers so a test can reach them."""
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(config, "ASK_PER_MINUTE", 3)
    monkeypatch.setattr(config, "ASK_PER_HOUR", 10)
    monkeypatch.setattr(config, "CHEAP_PER_MINUTE", 5)


# ------------------------------------------------------------ counting


def test_requests_under_the_limit_are_allowed():
    for _ in range(5):
        assert rate_limit._too_many("someone", limit=5, window_seconds=60) == 0


def test_the_request_over_the_limit_is_told_how_long_to_wait():
    for _ in range(5):
        rate_limit._too_many("someone", limit=5, window_seconds=60)

    wait = rate_limit._too_many("someone", limit=5, window_seconds=60)
    assert wait > 0
    assert wait <= 61


def test_the_window_slides_so_old_requests_stop_counting():
    """
    A fixed window would let somebody send double the limit across a
    boundary. This one drops timestamps as they age out instead.
    """
    rate_limit._too_many("someone", limit=2, window_seconds=1)
    rate_limit._too_many("someone", limit=2, window_seconds=1)
    assert rate_limit._too_many("someone", limit=2, window_seconds=1) > 0

    time.sleep(1.1)
    assert rate_limit._too_many("someone", limit=2, window_seconds=1) == 0


def test_two_addresses_are_counted_separately():
    for _ in range(3):
        rate_limit._too_many("first", limit=3, window_seconds=60)

    assert rate_limit._too_many("first", limit=3, window_seconds=60) > 0
    assert rate_limit._too_many("second", limit=3, window_seconds=60) == 0


# ------------------------------------------------------- who is asking


def test_the_forwarded_address_is_used_when_there_is_a_proxy():
    """
    Render sits behind a proxy. Without this, request.client.host is the
    proxy for every visitor and the whole world shares one limit.
    """

    class FakeRequest:
        headers = {"x-forwarded-for": "203.0.113.7, 10.0.0.1"}
        client = None

    assert rate_limit.client_key(FakeRequest()) == "203.0.113.7"


# ------------------------------------------------------- the API itself


def test_asking_too_often_gets_429_with_retry_after(limits_on, monkeypatch):
    from app import answering
    from app.main import app

    # The first three questions are under the limit, so they reach the
    # handler and would call a real model. This test is about counting,
    # not answering, so a stand in keeps it fast, free and runnable in
    # CI with no key. Without this the suite would quietly spend tokens
    # every time it ran.
    def fake_answer(question, **kwargs):
        return {"answer": "A stand in answer.", "abstained": False,
                "latency_ms": 1, "tokens": 10}

    monkeypatch.setattr(answering, "answer_question", fake_answer)

    with TestClient(app) as client:
        body = {"question": "What is the income limit for this scheme?"}

        for _ in range(3):
            assert client.post("/api/ask", json=body).status_code == 200

        response = client.post("/api/ask", json=body)

    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_eligibility_still_works_when_the_token_budget_is_gone(limits_on, monkeypatch):
    """
    The point of the whole design. Eligibility is pure SQL, so it has no
    reason to stop when the model quota does.
    """
    monkeypatch.setattr(config, "DAILY_TOKEN_BUDGET", 1000)
    monkeypatch.setattr(rate_limit, "_tokens_today", 5000)

    from app.main import app

    with TestClient(app) as client:
        asked = client.post("/api/ask", json={"question": "Am I eligible for anything?"})
        checked = client.post(
            "/api/eligibility",
            json={"profile": {"percentage": 80, "income": 100000, "category": "SC"}},
        )

    assert asked.status_code == 429
    assert "budget" in asked.json()["detail"].lower()
    assert checked.status_code == 200
    assert "matches" in checked.json()


def test_spending_tokens_counts_towards_the_budget():
    rate_limit.spend(1200)
    rate_limit.spend(800)
    assert rate_limit.tokens_used_today() == 2000
