"""
Tests for reading the provider's own advice out of a refusal.

These exist because an evaluation run died at question nineteen of
thirty, and the reason was not the rate limit. It was that the retry
loop ignored what the rate limit told it.

The judge model allows three requests a minute. When it refuses, Groq
replies "Please try again in 20s". The backoff started at two seconds
and doubled, so it came back at 2, 4, 8 and 16 seconds, every one of
them too early, and then gave up having never once waited long enough.
The provider had written the answer in the error message the whole time.

So the rule now is: if the provider says how long to wait, wait that
long. Guessing is for when it does not say.
"""

from app.llm import suggested_wait


def test_seconds_are_read_with_a_second_of_slack():
    """
    The exact message that killed the run.

    A second is added because the provider's clock and mine are not the
    same clock, and coming back a hair early wastes the entire wait.
    """
    message = (
        "Error code: 429 - Rate limit reached for model "
        "`openai/gpt-oss-safeguard-20b` on requests per minute (RPM): "
        "Limit 3, Used 3, Requested 1. Please try again in 20s."
    )
    assert suggested_wait(message) == 21.0


def test_minutes_are_turned_into_seconds():
    """Groq uses minutes once the wait gets long, and 1.5m is not 1.5s."""
    assert suggested_wait("Please try again in 1.5m.") == 91.0


def test_a_fractional_second_is_read():
    assert suggested_wait("Please try again in 7.5s") == 8.5


def test_no_advice_means_no_answer():
    """
    None is the signal to fall back to doubling, so it has to be None
    and not zero. Zero would read as "retry immediately", which is the
    one thing a rate limit is asking you not to do.
    """
    assert suggested_wait("Service temporarily unavailable") is None
    assert suggested_wait("") is None
