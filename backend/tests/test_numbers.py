"""
Tests for reading numbers out of Indian scholarship text.

These look small, but every one of them is a way an income limit is
written in my actual corpus. The grounding check compares numbers as
floats rather than as strings precisely because of the spread here, and
if this file breaks, the check silently starts passing everything.
"""

from app.numbers import contains_number, find_dates, find_numbers, normalise


def test_plain_number_is_found():
    assert 250000 in find_numbers("income of 250000 rupees")


def test_indian_digit_grouping_is_read_correctly():
    """2,50,000 is two and a half lakh, not two hundred and fifty."""
    found = find_numbers("annual income of INR 2,50,000 from all sources")
    assert 250000 in found


def test_lakh_is_multiplied_out():
    """
    "2.5 lakhs" is two hundred and fifty thousand, and only that.

    The bare 2.5 is deliberately not returned. The word is part of the
    number, and returning both made the grounding check treat the "2.5"
    in a correct answer as a figure with no source behind it.
    """
    found = find_numbers("family income of less than INR 2.5 lakhs")
    assert 250000 in found
    assert 2.5 not in found


def test_crore_is_multiplied_out():
    assert 20000000 in find_numbers("a scholarship up to 2 crore")


def test_percentage_and_cgpa_survive_the_decimal():
    assert 7.5 in find_numbers("a minimum CGPA of 7.5")
    assert 60 in find_numbers("at least 60% marks in the previous exam")


def test_contains_number_matches_across_formats():
    """The whole point: one written form, a different stored form."""
    assert contains_number("income below INR 8,00,000 per annum", 800000)
    assert contains_number("income below 8 lakh per annum", 800000)


def test_contains_number_rejects_a_number_that_is_not_there():
    """
    This is the case that matters.

    If the model says the limit is 8,00,000 but the sentence it quoted
    says 2,50,000, the extraction has to be rejected.
    """
    assert not contains_number("income below INR 2,50,000 per annum", 800000)


def test_contains_number_handles_none():
    assert not contains_number("anything at all", None)


def test_dates_are_found_in_several_shapes():
    assert find_dates("the last date is 31 October 2026")
    assert find_dates("applications close on October 31, 2026")
    assert find_dates("closing 2026-10-31")


def test_normalise_squashes_spacing_and_punctuation():
    """Two versions of the same sentence have to come out identical."""
    first = normalise("Applicants  must   have 60% marks.")
    second = normalise("Applicants must have 60% marks")
    assert first == second
