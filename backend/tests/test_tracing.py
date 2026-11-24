"""
Tests for the Langfuse tracing, and for it staying out of the way.

These exist because of a bug that was live for weeks without anyone
noticing. The trace was written against a method name that does not
exist in the pinned version of the library, so every single trace raised
an exception, which the "never break a request" rule caught and turned
into a printed line in a log nobody reads. Tracing was configured,
switched on, and recording nothing at all.

The lesson was not "be more careful". It was that a failure which is
designed to be silent will be silent for a very long time. So there are
two kinds of test here: one kind proves tracing can never break an
answer, and the other kind proves that when tracing itself is broken it
says so out loud, through /api/health, instead of looking healthy.

Nothing here touches the network. The clients are stand ins.
"""

import pytest

from app import config, tracing


@pytest.fixture(autouse=True)
def clean_tracing():
    """
    Reset the module between tests.

    All of this state lives at module level, because the client is built
    once and kept. That is right for the application and awkward for
    tests, so each one starts from nothing.
    """
    tracing._client = None
    tracing._enabled = True
    tracing._sent = 0
    tracing._last_error = None
    yield
    tracing._client = None
    tracing._sent = 0
    tracing._last_error = None


class GoodClient:
    """A Langfuse that works."""

    def auth_check(self):
        return True

    def start_as_current_observation(self, **kwargs):
        return Span()

    def flush(self):
        pass


class Span:
    def __enter__(self):
        return self

    def __exit__(self, *details):
        return False

    def update(self, **kwargs):
        pass


class RejectingClient(GoodClient):
    """A Langfuse that does not like the keys."""

    def auth_check(self):
        raise RuntimeError("401 Unauthorized")


class BrokenClient(GoodClient):
    """
    A Langfuse whose keys check out but whose span call does not exist.

    This is the real bug, kept as a test. auth_check passed, so
    everything looked configured, and then every trace raised.
    """

    def start_as_current_observation(self, **kwargs):
        raise AttributeError("'Langfuse' object has no attribute 'whatever'")


ANSWER = {
    "question": "what is the income limit",
    "mode": "hybrid",
    "answer": "Two lakh fifty thousand rupees.",
    "abstained": False,
    "grounded": True,
    "latency_ms": 1200,
    "tokens": 900,
    "trace": [{"step": "route", "outcome": "ok", "detail": "..."}],
}


# ------------------------------------------------- staying out of the way


def test_nothing_happens_at_all_without_keys(monkeypatch):
    """Nobody should need a Langfuse account to run this project."""
    monkeypatch.setattr(config, "LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setattr(config, "LANGFUSE_SECRET_KEY", "")
    tracing._enabled = False

    assert tracing.status() == {"state": "off"}
    # The important part: this returns rather than raising.
    tracing.record_answer(ANSWER, chunks=[], profile=None)


def test_a_broken_trace_does_not_break_the_answer():
    """
    The rule that hid the original bug, which is still the right rule.

    A student's answer must not depend on my observability working. So
    this stays swallowed, and the test below is what stops it being
    swallowed silently.
    """
    tracing._client = BrokenClient()

    tracing.record_answer(ANSWER, chunks=[], profile=None)  # must not raise


# ------------------------------------------------------- saying so out loud


def test_a_broken_trace_is_reported_as_failing(monkeypatch):
    """Swallowed, but not hidden. This is the test the old code failed."""
    # The keys have to look set, because "off" is the right answer when
    # nobody configured anything and there is nothing to warn about.
    monkeypatch.setattr(config, "LANGFUSE_PUBLIC_KEY", "pk-lf-fine")
    monkeypatch.setattr(config, "LANGFUSE_SECRET_KEY", "sk-lf-fine")
    tracing._client = BrokenClient()

    tracing.record_answer(ANSWER, chunks=[], profile=None)

    state = tracing.status()
    assert state["state"] == "failing"
    assert state["sent"] == 0
    assert "whatever" in state["last_error"]


def test_rejected_keys_are_reported_as_failing_not_off(monkeypatch):
    """
    "Off" would be a lie here.

    Somebody set these keys and believes they are working. Reporting
    "off" reads as "you did not configure it", which sends them looking
    in the wrong place.
    """
    monkeypatch.setattr(config, "LANGFUSE_PUBLIC_KEY", "pk-lf-wrong")
    monkeypatch.setattr(config, "LANGFUSE_SECRET_KEY", "sk-lf-wrong")
    monkeypatch.setattr(tracing, "_build_client", lambda: RejectingClient(), raising=False)

    # Stand in for the import and construction, leaving the credential
    # check to run for real against the fake client.
    tracing._client = None

    class FakeModule:
        Langfuse = staticmethod(lambda **kwargs: RejectingClient())

    monkeypatch.setitem(__import__("sys").modules, "langfuse", FakeModule)

    state = tracing.status()
    assert state["state"] == "failing"
    # The message has to name the variable the SDK actually reads, so
    # that somebody chasing a 401 edits the right one.
    assert "LANGFUSE_BASE_URL" in state["last_error"]


def test_a_working_trace_counts(monkeypatch):
    monkeypatch.setattr(config, "LANGFUSE_PUBLIC_KEY", "pk-lf-fine")
    monkeypatch.setattr(config, "LANGFUSE_SECRET_KEY", "sk-lf-fine")
    tracing._client = GoodClient()

    tracing.record_answer(ANSWER, chunks=[], profile=None)
    tracing.record_answer(ANSWER, chunks=[], profile=None)

    assert tracing.status() == {"state": "on", "sent": 2}
