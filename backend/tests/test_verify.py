"""
Tests for the source sentence check.

This is the guard on the step where a language model writes my database.
The guide is blunt that if a threshold is hallucinated here, every
answer downstream is confidently wrong while every retrieval metric
still looks fine. So these tests are about one thing: does a value with
no real sentence behind it get rejected.

The two directions both matter. A check that rejects nothing is
decoration. A check that rejects good extractions costs real data and
tempts me to switch it off, which is worse than never having it.
"""

from ingestion.verify import quote_is_in_document, verify_extraction

DOCUMENT = """
Scheme name: A Test Scholarship

## Eligibility
Applicants must belong to the Scheduled Caste category.
Applicants must have secured at least 60% marks in the previous final examination.
Applicants must have an annual family income of less than INR 2,50,000 from all sources.
Applicants must not be more than 30 years of age.

## Deadline
31 October 2026.
"""


def test_a_real_quote_is_accepted():
    quote = "Applicants must have secured at least 60% marks in the previous final examination."
    assert quote_is_in_document(quote, DOCUMENT)


def test_a_slightly_retyped_quote_is_still_accepted():
    """
    Models re-type a sentence with small changes. Rejecting those would
    throw away good extractions for no safety gain, because an invented
    sentence shares almost none of its uncommon words with the source.
    """
    quote = "Applicants must have secured at least 60% marks in the previous final exam"
    assert quote_is_in_document(quote, DOCUMENT)


def test_an_invented_quote_is_rejected():
    quote = "Applicants must own a laptop and live within ten kilometres of the college."
    assert not quote_is_in_document(quote, DOCUMENT)


def test_good_extraction_is_fully_verified():
    extracted = {
        "min_percentage": 60,
        "min_percentage_quote": "Applicants must have secured at least 60% marks in the previous final examination.",
        "max_family_income": 250000,
        "max_family_income_quote": "Applicants must have an annual family income of less than INR 2,50,000 from all sources.",
        "categories": ["SC"],
        "categories_quote": "Applicants must belong to the Scheduled Caste category.",
    }

    values, sources, unknown, confidence = verify_extraction(extracted, DOCUMENT)

    assert values["min_percentage"] == 60
    assert values["max_family_income"] == 250000
    assert values["categories"] == ["SC"]
    assert unknown == []
    assert confidence == 1.0


def test_a_hallucinated_threshold_is_rejected_not_stored():
    """
    The whole reason this file exists.

    The quoted sentence is real and says 60%, but the model claims the
    cutoff is 80%. The column must end up empty and the field must be
    named as unknown, because a wrong threshold that looks confident is
    the worst thing this project can produce.
    """
    extracted = {
        "min_percentage": 80,
        "min_percentage_quote": "Applicants must have secured at least 60% marks in the previous final examination.",
    }

    values, sources, unknown, confidence = verify_extraction(extracted, DOCUMENT)

    assert values["min_percentage"] is None
    assert "min_percentage" in unknown
    assert confidence == 0.0
    assert sources["min_percentage"]["verified"] is False


def test_a_value_with_no_quote_at_all_is_rejected():
    extracted = {"max_family_income": 800000, "max_family_income_quote": None}

    values, sources, unknown, confidence = verify_extraction(extracted, DOCUMENT)

    assert values["max_family_income"] is None
    assert "max_family_income" in unknown


def test_a_null_field_is_not_counted_as_a_failure():
    """
    Null means "this scheme sets no limit here". It is an answer, not a
    miss, so it must not drag the confidence down. Getting this wrong
    would punish every simple scheme for being simple.
    """
    extracted = {
        "min_percentage": 60,
        "min_percentage_quote": "Applicants must have secured at least 60% marks in the previous final examination.",
        "min_cgpa": None,
        "min_cgpa_quote": None,
        "max_age": None,
        "max_age_quote": None,
    }

    values, sources, unknown, confidence = verify_extraction(extracted, DOCUMENT)

    assert confidence == 1.0
    assert values["min_cgpa"] is None
    assert "min_cgpa" not in sources


def test_a_category_written_out_in_words_is_accepted():
    """The document says "Scheduled Caste". The column stores "SC"."""
    extracted = {
        "categories": ["SC"],
        "categories_quote": "Applicants must belong to the Scheduled Caste category.",
    }

    values, _, unknown, _ = verify_extraction(extracted, DOCUMENT)

    assert values["categories"] == ["SC"]
    assert unknown == []


def test_a_category_the_sentence_does_not_mention_is_rejected():
    extracted = {
        "categories": ["SC", "ST"],
        "categories_quote": "Applicants must belong to the Scheduled Caste category.",
    }

    values, _, unknown, _ = verify_extraction(extracted, DOCUMENT)

    assert values["categories"] is None
    assert "categories" in unknown


def test_a_deadline_with_the_wrong_year_is_rejected():
    extracted = {
        "deadline": "2027-10-31",
        "deadline_quote": "31 October 2026.",
    }

    values, _, unknown, _ = verify_extraction(extracted, DOCUMENT)

    assert values["deadline"] is None
    assert "deadline" in unknown


def test_an_attendance_percentage_is_not_a_marks_requirement():
    """
    Found by reading the extractions by hand, not by any check.

    The Delhi OBC scheme says "an attendance of at least 75%". The model
    put 75 into min_percentage and every check passed, because the
    sentence is real and it does contain 75. The scheme has no marks
    requirement at all, so the filter was turning away eligible students
    who had less than 75% marks.
    """
    document = "Applicants must have secured an attendance of at least 75% in the previous year."
    extracted = {
        "min_percentage": 75,
        "min_percentage_quote": "Applicants must have secured an attendance of at least 75% in the previous year.",
    }

    values, sources, unknown, _ = verify_extraction(extracted, document)

    assert values["min_percentage"] is None
    assert "min_percentage" in unknown
    assert "attendance" in sources["min_percentage"]["reason"]


def test_a_sentence_about_both_marks_and_attendance_is_still_accepted():
    """
    The other half of the trade. Plenty of schemes ask for marks and
    attendance in one sentence, and rejecting those would throw away
    good extractions to catch a rarer bad one.
    """
    document = "Applicants must have 60% marks and maintain 75% attendance."
    extracted = {
        "min_percentage": 60,
        "min_percentage_quote": "Applicants must have 60% marks and maintain 75% attendance.",
    }

    values, _, unknown, _ = verify_extraction(extracted, document)

    assert values["min_percentage"] == 60
    assert unknown == []
