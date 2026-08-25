"""
Tests for layer 1 of the grounding check.

This is the cheap deterministic guard that runs before any judge. Every
number and date in a generated answer has to be findable in the
retrieved context. A fabricated deadline or income limit is the worst
thing this system can produce, because it reads exactly like a correct
answer and a student may act on it.

The false positive tests matter just as much. If citation markers or
numbered list items counted as claims, good answers would be blocked
constantly and I would end up loosening the check until it caught
nothing.
"""

from app.grounding import check_dates, check_layer_one, check_numbers, strip_non_claims

CHUNKS = [
    {
        "chunk_text": (
            "A Test Scholarship\nEligibility\n"
            "Applicants must have an annual family income of less than INR 2,50,000. "
            "Applicants must have secured at least 60% marks."
        )
    },
    {
        "chunk_text": "A Test Scholarship\nDeadline\nThe last date is 31 October 2026.",
    },
]


def test_an_answer_using_only_real_numbers_passes():
    answer = "You need at least 60% marks and a family income below INR 2,50,000."
    assert check_numbers(answer, [chunk["chunk_text"] for chunk in CHUNKS]) == []


def test_an_invented_income_limit_is_caught():
    """The context says 2,50,000. The answer says 8,00,000."""
    answer = "The family income limit for this scheme is INR 8,00,000."
    unsupported = check_numbers(answer, [chunk["chunk_text"] for chunk in CHUNKS])
    assert 800000 in unsupported


def test_the_same_amount_written_differently_still_passes():
    """
    The context says "INR 2,50,000" and the answer says "2.5 lakh".
    Same number, different words. Comparing strings would block this.
    """
    answer = "Your family income must be under 2.5 lakh."
    assert check_numbers(answer, [chunk["chunk_text"] for chunk in CHUNKS]) == []


def test_citation_markers_are_not_treated_as_claims():
    """
    [1] and [2] point at sources. They are not facts about scholarships,
    and counting them would block almost every well cited answer.
    """
    answer = "You need at least 60% marks [1] and an income below 2,50,000 [2]."
    assert check_numbers(answer, [chunk["chunk_text"] for chunk in CHUNKS]) == []


def test_full_width_citation_brackets_are_also_stripped():
    """
    The prompt asks for [1] and the model sometimes writes the full
    width 【1】 instead. That got read as a claim about the number one,
    and a correct answer was blocked for citing its source properly.
    """
    answer = "You need at least 60% marks【1】 and an income below 2,50,000【2】."
    assert check_numbers(answer, [chunk["chunk_text"] for chunk in CHUNKS]) == []


def test_numbered_list_markers_are_not_treated_as_claims():
    answer = "1. Get your income certificate.\n2. Register on the portal.\n3. Upload it."
    assert check_numbers(answer, [chunk["chunk_text"] for chunk in CHUNKS]) == []


def test_strip_non_claims_removes_both():
    cleaned = strip_non_claims("1. First step [3] here.")
    assert "[3]" not in cleaned


def test_a_real_deadline_passes():
    answer = "Applications close on 31 October 2026."
    assert check_dates(answer, [chunk["chunk_text"] for chunk in CHUNKS]) == []


def test_a_swapped_month_is_caught():
    """
    31 October 2026 and 31 November 2026 contain exactly the same
    numbers, so the number check cannot tell them apart. This is the
    only reason dates get their own check.
    """
    answer = "Applications close on 31 November 2026."
    assert check_dates(answer, [chunk["chunk_text"] for chunk in CHUNKS]) != []


def test_layer_one_puts_it_all_together():
    good = check_layer_one("You need 60% marks.", CHUNKS)
    assert good["grounded"] is True

    bad = check_layer_one("You need 95% marks by 1 January 2030.", CHUNKS)
    assert bad["grounded"] is False
    assert bad["unsupported_numbers"] or bad["unsupported_dates"]


def test_the_students_own_numbers_count_as_a_source():
    """
    An answer that repeats "your income of 3,00,000" is quoting the
    question, not inventing. The question and profile are passed in as
    extra sources for exactly this.
    """
    answer = "Your income of 3,00,000 is above the limit of 2,50,000."
    result = check_layer_one(answer, CHUNKS, extra_texts=["my family income is 300000"])
    assert result["grounded"] is True
