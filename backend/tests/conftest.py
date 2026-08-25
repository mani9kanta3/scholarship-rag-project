"""
Shared setup for the tests.

The eligibility tests need schemes with thresholds I chose, not the
forty four real ones, because a test that says "a student with 74.9%
does not match" has to know the cutoff is 75 and the real corpus may
change under it.

So this fixture writes three small schemes into the database, hands back
their ids, and deletes them afterwards. They are given names starting
with "TEST " so that if a run is ever killed halfway, the leftovers are
obvious and easy to clear out by hand.
"""

import json

import pytest

from app import db

MARKER = "TEST SCHEME "


def _insert(name, criteria):
    scheme_id = db.insert_returning_id(
        """
        INSERT INTO scheme (name, provider, description, source_url, source_file, last_updated)
        VALUES (%(name)s, 'Test provider', 'A scheme that only exists for the tests.',
                'https://example.com', 'test.md', CURRENT_DATE)
        RETURNING id
        """,
        {"name": MARKER + name},
    )

    db.execute(
        """
        INSERT INTO eligibility_criteria
            (scheme_id, min_percentage, min_cgpa, max_family_income,
             categories, genders, course_levels, states, min_age, max_age,
             field_sources, unknown_fields, extraction_confidence)
        VALUES
            (%(scheme_id)s, %(min_percentage)s, %(min_cgpa)s, %(max_family_income)s,
             %(categories)s, %(genders)s, %(course_levels)s, %(states)s,
             %(min_age)s, %(max_age)s, %(field_sources)s, %(unknown_fields)s, 1.0)
        """,
        {
            "scheme_id": scheme_id,
            "min_percentage": criteria.get("min_percentage"),
            "min_cgpa": criteria.get("min_cgpa"),
            "max_family_income": criteria.get("max_family_income"),
            "categories": criteria.get("categories"),
            "genders": criteria.get("genders"),
            "course_levels": criteria.get("course_levels"),
            "states": criteria.get("states"),
            "min_age": criteria.get("min_age"),
            "max_age": criteria.get("max_age"),
            "field_sources": json.dumps({}),
            "unknown_fields": criteria.get("unknown_fields", []),
        },
    )

    return scheme_id


@pytest.fixture
def test_schemes():
    """
    Three schemes with thresholds the tests can rely on.

    strict   75% and income up to 2,50,000, SC only, Telangana only
    open     no limits at all, so it must match everybody
    cgpa     CGPA 7.5, to test a threshold on the other scale
    """
    ids = {
        "strict": _insert(
            "strict",
            {
                "min_percentage": 75,
                "max_family_income": 250000,
                "categories": ["SC"],
                "course_levels": ["UG"],
                "states": ["Telangana"],
            },
        ),
        "open": _insert("open", {}),
        "cgpa": _insert("cgpa", {"min_cgpa": 7.5}),
    }

    yield ids

    # CASCADE on the foreign key takes the criteria rows with it.
    db.execute(
        "DELETE FROM scheme WHERE name LIKE %(marker)s",
        {"marker": MARKER + "%"},
    )
