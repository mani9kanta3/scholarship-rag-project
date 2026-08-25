"""
Tests for the eligibility filter.

The threshold tests are the important ones. 74.9 and 75.1 against a 75%
cutoff are two sentences that embed almost identically, and a pure
vector system gets them close to right half the time. The whole design
of this project is that these are decided by a comparison in SQL, so if
these tests ever fail, the argument the project is built on has stopped
being true.

The NULL tests are the other half. NULL in a criteria column means "this
scheme sets no limit here", so a scheme with no limits must match
everybody. Get that backwards and the filter quietly excludes every
scheme that happens to be simple.
"""

from app import eligibility

BASE = {
    "percentage": 80,
    "cgpa": None,
    "income": 200000,
    "age": 19,
    "category": "SC",
    "gender": "FEMALE",
    "course_level": "UG",
    "state": "Telangana",
}


def matched_ids(profile):
    return {scheme["id"] for scheme in eligibility.find_matches(profile)}


def test_a_profile_that_meets_everything_matches(test_schemes):
    assert test_schemes["strict"] in matched_ids(BASE)


def test_just_above_the_cutoff_matches(test_schemes):
    """75.1 against a 75 cutoff. One tenth of a percent above."""
    profile = {**BASE, "percentage": 75.1}
    assert test_schemes["strict"] in matched_ids(profile)


def test_exactly_on_the_cutoff_matches(test_schemes):
    """
    75 against "minimum 75%". Minimum includes the number itself, so
    this has to match. It is the boundary a careless <= or < gets wrong.
    """
    profile = {**BASE, "percentage": 75}
    assert test_schemes["strict"] in matched_ids(profile)


def test_just_below_the_cutoff_does_not_match(test_schemes):
    """74.9 against a 75 cutoff. This is the one embeddings cannot do."""
    profile = {**BASE, "percentage": 74.9}
    assert test_schemes["strict"] not in matched_ids(profile)


def test_income_one_rupee_over_the_limit_does_not_match(test_schemes):
    profile = {**BASE, "income": 250001}
    assert test_schemes["strict"] not in matched_ids(profile)


def test_income_exactly_on_the_limit_matches(test_schemes):
    profile = {**BASE, "income": 250000}
    assert test_schemes["strict"] in matched_ids(profile)


def test_wrong_category_does_not_match(test_schemes):
    profile = {**BASE, "category": "OBC"}
    assert test_schemes["strict"] not in matched_ids(profile)


def test_wrong_state_does_not_match(test_schemes):
    profile = {**BASE, "state": "Kerala"}
    assert test_schemes["strict"] not in matched_ids(profile)


def test_a_scheme_with_no_limits_matches_everyone(test_schemes):
    """NULL means no constraint, so this one can never rule anybody out."""
    poor_profile = {
        "percentage": 35,
        "cgpa": None,
        "income": 5000000,
        "age": 44,
        "category": "GEN",
        "gender": "MALE",
        "course_level": "PHD",
        "state": "Kerala",
    }
    assert test_schemes["open"] in matched_ids(poor_profile)


def test_a_missing_profile_field_does_not_silently_exclude(test_schemes):
    """
    A student who did not give their marks should still see the scheme,
    with the unchecked rule reported. Treating "did not say" as a fail
    would hide schemes they may well qualify for.
    """
    profile = {**BASE, "percentage": None}
    matches = eligibility.find_matches(profile)
    strict = [m for m in matches if m["id"] == test_schemes["strict"]]

    assert strict, "the scheme should still be offered as a candidate"
    assert any("minimum percentage" in rule for rule in strict[0]["unchecked_rules"])


def test_cgpa_threshold_works_on_its_own_scale(test_schemes):
    above = {**BASE, "cgpa": 7.6, "percentage": None}
    below = {**BASE, "cgpa": 7.4, "percentage": None}

    assert test_schemes["cgpa"] in matched_ids(above)
    assert test_schemes["cgpa"] not in matched_ids(below)


def test_near_miss_reports_how_far_short(test_schemes):
    """
    "You are 0.6% short" is only possible because the cutoff is a real
    number in a real column. A vector search cannot tell you a distance.
    """
    profile = {**BASE, "percentage": 74.4}
    near = eligibility.find_near_misses(profile)

    strict = [item for item in near if item["id"] == test_schemes["strict"]]
    assert strict, "the scheme should show up as a near miss"
    assert "short" in strict[0]["missed_by"]
    assert "75" in strict[0]["missed_by"]


def test_a_scheme_missed_on_two_rules_is_not_a_near_miss(test_schemes):
    """Missing on marks and on income is not a near miss, it is a no."""
    profile = {**BASE, "percentage": 40, "income": 900000}
    near_ids = {item["id"] for item in eligibility.find_near_misses(profile)}
    assert test_schemes["strict"] not in near_ids
