"""
The eligibility engine. One SQL query, and it is exact.

This is the part of the project worth defending in an interview.

"CGPA above 7.5" and "CGPA above 8.5" produce almost the same embedding,
so a vector search cannot tell them apart and will happily return the
wrong one. Comparing two numbers is not a similarity problem, it is
arithmetic, so no embedding is involved here at all. The criteria were
pulled into real columns at ingestion time and this compares them with
<= and >=, in the database, where that comparison is exact.

The order matters as much as the method. This runs **first**, and the
scheme ids it returns are what the vector search is then allowed to look
inside. Retrieving semantically and filtering afterwards fails, because
the scheme the student actually qualifies for was often never in the
retrieved set to begin with.

NULL in a criteria column means "this scheme sets no limit here", so
NULL always passes. A value we could not read is not NULL, it is listed
in unknown_fields, and it is reported rather than asserted.
"""

from . import config, db

# Read as: the scheme passes if it sets no limit, or the student meets
# the limit. The %(field)s IS NULL part is for a student who did not
# tell us that field. Then the rule cannot be checked, so the scheme is
# kept as a candidate and the unchecked rule is reported on the way out.
FILTER_SQL = """
SELECT
    s.id, s.name, s.provider, s.description, s.amount_text,
    s.deadline, s.source_url, s.last_updated,
    c.min_cgpa, c.min_percentage, c.max_family_income,
    c.categories, c.genders, c.course_levels, c.states,
    c.min_age, c.max_age,
    c.unknown_fields, c.extraction_confidence
FROM scheme s
JOIN eligibility_criteria c ON c.scheme_id = s.id
WHERE (c.min_cgpa          IS NULL OR %(cgpa)s       IS NULL OR c.min_cgpa          <= %(cgpa)s)
  AND (c.min_percentage    IS NULL OR %(percentage)s IS NULL OR c.min_percentage    <= %(percentage)s)
  AND (c.max_family_income IS NULL OR %(income)s     IS NULL OR c.max_family_income >= %(income)s)
  AND (c.categories        IS NULL OR %(category)s   IS NULL OR %(category)s = ANY(c.categories))
  AND (c.genders           IS NULL OR %(gender)s     IS NULL OR %(gender)s   = ANY(c.genders))
  AND (c.course_levels     IS NULL OR %(course)s     IS NULL OR %(course)s   = ANY(c.course_levels))
  AND (c.states            IS NULL OR %(state)s      IS NULL OR %(state)s    = ANY(c.states))
  AND (c.min_age           IS NULL OR %(age)s        IS NULL OR c.min_age    <= %(age)s)
  AND (c.max_age           IS NULL OR %(age)s        IS NULL OR c.max_age    >= %(age)s)
ORDER BY s.id
"""

# The same query with the four numeric rules taken out. Whatever appears
# here but not above failed on a number, and by how much is worked out
# in Python afterwards.
NEAR_MISS_SQL = """
SELECT
    s.id, s.name, s.provider, s.amount_text, s.deadline, s.source_url,
    c.min_cgpa, c.min_percentage, c.max_family_income, c.min_age, c.max_age,
    c.unknown_fields, c.extraction_confidence
FROM scheme s
JOIN eligibility_criteria c ON c.scheme_id = s.id
WHERE (c.categories    IS NULL OR %(category)s IS NULL OR %(category)s = ANY(c.categories))
  AND (c.genders       IS NULL OR %(gender)s   IS NULL OR %(gender)s   = ANY(c.genders))
  AND (c.course_levels IS NULL OR %(course)s   IS NULL OR %(course)s   = ANY(c.course_levels))
  AND (c.states        IS NULL OR %(state)s    IS NULL OR %(state)s    = ANY(c.states))
ORDER BY s.id
"""


def clean_profile(profile):
    """
    Put the profile into the shape the query expects.

    Text fields are upper cased because the criteria columns hold
    "SC" and "FEMALE". A student typing "sc" should not silently match
    nothing at all.
    """
    def upper(value):
        return value.strip().upper() if isinstance(value, str) and value.strip() else None

    return {
        "cgpa": profile.get("cgpa"),
        "percentage": profile.get("percentage"),
        "income": profile.get("income"),
        "age": profile.get("age"),
        "category": upper(profile.get("category")),
        "gender": upper(profile.get("gender")),
        "course": upper(profile.get("course_level")),
        # States are stored with their normal capitals, "Telangana", so
        # this one is title cased instead of upper cased.
        "state": (
            profile.get("state").strip().title()
            if isinstance(profile.get("state"), str) and profile.get("state").strip()
            else None
        ),
    }


def explain_match(scheme, values):
    """
    Say in plain words why this scheme matched.

    A list of schemes with no reasons is not much of an answer. This is
    what the results page shows under each scheme.
    """
    reasons = []

    if scheme["max_family_income"] is not None and values["income"] is not None:
        reasons.append(
            f"Income limit is {int(scheme['max_family_income']):,} and yours is {int(values['income']):,}."
        )
    if scheme["min_percentage"] is not None and values["percentage"] is not None:
        reasons.append(
            f"Needs {scheme['min_percentage']}% and you have {values['percentage']}%."
        )
    if scheme["min_cgpa"] is not None and values["cgpa"] is not None:
        reasons.append(f"Needs CGPA {scheme['min_cgpa']} and you have {values['cgpa']}.")
    if scheme["categories"] and values["category"]:
        reasons.append(f"Open to {', '.join(scheme['categories'])}.")
    if scheme["genders"] and values["gender"]:
        reasons.append(f"Open to {', '.join(scheme['genders'])}.")
    if scheme["course_levels"] and values["course"]:
        reasons.append(f"Covers {', '.join(scheme['course_levels'])}.")
    if scheme["states"] and values["state"]:
        reasons.append(f"For students of {', '.join(scheme['states'])}.")

    if not reasons:
        reasons.append("This scheme sets no limits that your profile conflicts with.")

    return reasons


def unchecked_rules(scheme, values):
    """
    Rules this scheme has that the student's profile could not answer.

    A scheme wanting 60% marks is not a match for someone who did not
    give their marks. It is a maybe, and saying so is more useful than
    quietly counting it as a yes.
    """
    unchecked = []

    pairs = [
        ("min_cgpa", "cgpa", "a minimum CGPA"),
        ("min_percentage", "percentage", "a minimum percentage"),
        ("max_family_income", "income", "a family income limit"),
        ("min_age", "age", "a minimum age"),
        ("max_age", "age", "a maximum age"),
    ]
    for column, profile_field, description in pairs:
        if scheme.get(column) is not None and values.get(profile_field) is None:
            unchecked.append(f"This scheme has {description}, which your profile did not give.")

    for column, profile_field, description in [
        ("categories", "category", "a category rule"),
        ("genders", "gender", "a gender rule"),
        ("course_levels", "course", "a course level rule"),
        ("states", "state", "a state rule"),
    ]:
        if scheme.get(column) and values.get(profile_field) is None:
            unchecked.append(f"This scheme has {description}, which your profile did not give.")

    return unchecked


def find_matches(profile):
    """
    Every scheme this student qualifies for.

    Each result carries the reasons it matched, the rules that could not
    be checked, and any field that failed the extraction check, so
    nothing is presented as more certain than it really is.
    """
    values = clean_profile(profile)
    rows = db.fetch_all(FILTER_SQL, values)

    matches = []
    for row in rows:
        scheme = dict(row)
        scheme["match_reasons"] = explain_match(row, values)
        scheme["unchecked_rules"] = unchecked_rules(row, values)
        scheme["unverified_fields"] = list(row["unknown_fields"] or [])
        matches.append(scheme)

    return matches


def check_one(profile, scheme_id):
    """
    Does this student meet the rules of this one scheme?

    "Am I eligible for the Central Sector Scheme with 79.5%?" names a
    scheme, so semantic search can find the right page easily. The hard
    part is the last step, comparing 79.5 with 80, and that is exactly
    the step a language model reading a paragraph gets wrong.

    So the verdict is decided here, by the same SQL filter, with the
    scheme id pinned. The answering layer is then told the result and
    told not to work it out again. The model writes the sentence; the
    database decides the fact.

    Returns None if there is no such scheme, otherwise a dict with the
    verdict and, when it failed, the rules that failed and by how much.
    """
    values = clean_profile(profile)
    values["scheme_id"] = scheme_id

    passed = db.fetch_all(FILTER_SQL.replace("ORDER BY s.id", "AND s.id = %(scheme_id)s"), values)

    scheme = db.fetch_one(
        """
        SELECT s.id, s.name, c.min_cgpa, c.min_percentage, c.max_family_income,
               c.categories, c.genders, c.course_levels, c.states,
               c.min_age, c.max_age, c.unknown_fields
        FROM scheme s
        JOIN eligibility_criteria c ON c.scheme_id = s.id
        WHERE s.id = %(scheme_id)s
        """,
        {"scheme_id": scheme_id},
    )

    if not scheme:
        return None

    if passed:
        row = passed[0]
        return {
            "scheme_id": scheme_id,
            "name": scheme["name"],
            "eligible": True,
            "reasons": explain_match(row, values),
            "unchecked": unchecked_rules(row, values),
            "unverified_fields": list(scheme["unknown_fields"] or []),
        }

    return {
        "scheme_id": scheme_id,
        "name": scheme["name"],
        "eligible": False,
        "reasons": _failed_rules(scheme, values),
        "unchecked": unchecked_rules(scheme, values),
        "unverified_fields": list(scheme["unknown_fields"] or []),
    }


def _failed_rules(scheme, values):
    """
    Which rules this student failed, in plain words with both numbers.

    Both numbers, always. "You need 80% and you have 79.5%" is the whole
    answer to a threshold question, and leaving either side out turns it
    back into something the reader has to take on trust.
    """
    failed = []

    if (
        scheme["min_percentage"] is not None
        and values["percentage"] is not None
        and values["percentage"] < float(scheme["min_percentage"])
    ):
        failed.append(
            f"It needs at least {scheme['min_percentage']}% and this student has "
            f"{values['percentage']}%."
        )

    if (
        scheme["min_cgpa"] is not None
        and values["cgpa"] is not None
        and values["cgpa"] < float(scheme["min_cgpa"])
    ):
        failed.append(
            f"It needs a CGPA of at least {scheme['min_cgpa']} and this student has "
            f"{values['cgpa']}."
        )

    if (
        scheme["max_family_income"] is not None
        and values["income"] is not None
        and values["income"] > float(scheme["max_family_income"])
    ):
        failed.append(
            f"The family income limit is {int(scheme['max_family_income'])} and this "
            f"student's income is {int(values['income'])}."
        )

    if scheme["categories"] and values["category"] and values["category"] not in scheme["categories"]:
        failed.append(
            f"It is only for {', '.join(scheme['categories'])} and this student is "
            f"{values['category']}."
        )

    if scheme["genders"] and values["gender"] and values["gender"] not in scheme["genders"]:
        failed.append(f"It is only for {', '.join(scheme['genders'])} students.")

    if scheme["course_levels"] and values["course"] and values["course"] not in scheme["course_levels"]:
        failed.append(
            f"It covers {', '.join(scheme['course_levels'])} and this student is at "
            f"{values['course']} level."
        )

    if scheme["states"] and values["state"] and values["state"] not in scheme["states"]:
        failed.append(
            f"It is only for students of {', '.join(scheme['states'])} and this student "
            f"is from {values['state']}."
        )

    if scheme["max_age"] is not None and values["age"] is not None and values["age"] > scheme["max_age"]:
        failed.append(
            f"The age limit is {scheme['max_age']} and this student is {values['age']}."
        )

    if scheme["min_age"] is not None and values["age"] is not None and values["age"] < scheme["min_age"]:
        failed.append(
            f"The minimum age is {scheme['min_age']} and this student is {values['age']}."
        )

    if not failed:
        # The SQL said no but nothing above explains it. Almost always a
        # deadline that has passed. Better to say something vague and
        # true than to invent a reason.
        failed.append("This student does not meet one of the recorded rules for this scheme.")

    return failed


def find_near_misses(profile, limit=None):
    """
    Schemes missed on one number, and by how much.

    "You miss this one by 0.2 CGPA" is genuinely useful to a student,
    and it is only possible because the thresholds are real numbers in
    real columns. A vector search cannot tell you how far off you were.

    Only schemes failing exactly one rule are shown. Failing three is
    not a near miss, it is just not your scheme.
    """
    limit = limit or config.NEAR_MISS_LIMIT
    values = clean_profile(profile)

    matched_ids = {scheme["id"] for scheme in find_matches(profile)}
    rows = db.fetch_all(NEAR_MISS_SQL, values)

    near = []

    for row in rows:
        if row["id"] in matched_ids:
            continue

        gaps = []

        if (
            row["min_percentage"] is not None
            and values["percentage"] is not None
            and values["percentage"] < row["min_percentage"]
        ):
            short = float(row["min_percentage"]) - float(values["percentage"])
            gaps.append((short, f"You are {short:.1f}% short of the {row['min_percentage']}% needed."))

        if (
            row["min_cgpa"] is not None
            and values["cgpa"] is not None
            and values["cgpa"] < row["min_cgpa"]
        ):
            short = float(row["min_cgpa"]) - float(values["cgpa"])
            gaps.append((short, f"You are {short:.2f} CGPA short of the {row['min_cgpa']} needed."))

        if (
            row["max_family_income"] is not None
            and values["income"] is not None
            and values["income"] > row["max_family_income"]
        ):
            over = float(values["income"]) - float(row["max_family_income"])
            gaps.append(
                (over, f"Your income is {int(over):,} over the {int(row['max_family_income']):,} limit.")
            )

        if row["max_age"] is not None and values["age"] is not None and values["age"] > row["max_age"]:
            over = values["age"] - row["max_age"]
            gaps.append((over, f"You are {over} years over the age limit of {row['max_age']}."))

        if row["min_age"] is not None and values["age"] is not None and values["age"] < row["min_age"]:
            under = row["min_age"] - values["age"]
            gaps.append((under, f"You are {under} years under the minimum age of {row['min_age']}."))

        # Exactly one rule missed, or it is not a near miss.
        if len(gaps) == 1:
            near.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "provider": row["provider"],
                    "amount_text": row["amount_text"],
                    "source_url": row["source_url"],
                    "missed_by": gaps[0][1],
                    "_size": gaps[0][0],
                }
            )

    # Closest first. A student cares most about the one they nearly got.
    near.sort(key=lambda item: item["_size"])
    for item in near:
        del item["_size"]

    return near[:limit]
