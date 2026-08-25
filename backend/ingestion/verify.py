"""
Checking the model's work against the document it read.

This is the second defence from section 5, and the guide is blunt about
it: an LLM is writing my database, and if it invents an income limit
then every answer built on that row is confidently wrong while all my
retrieval metrics still look fine.

So nothing is trusted just because it came back in the right shape.
For every field the model filled in, two questions get asked:

1. **Is the quoted sentence really in the document?** If not, the model
   wrote the sentence itself, and the value came from nowhere.
2. **Does that sentence actually contain the value?** A real quote with
   a number that is not in it is the exact failure this is here to
   catch.

A field that fails is not silently dropped. It goes into unknown_fields,
because "I could not read this" and "this scheme has no limit here" are
different things, and treating the first as the second would make a
scheme look open to everyone.
"""

import re

from app.numbers import contains_number, normalise

from .criteria_schema import LIST_FIELDS, NUMERIC_FIELDS, STATE_WORDS, VALUE_WORDS

# How much of a quote has to appear in the document before I accept it
# as a real quote. Models re-type a sentence slightly, dropping a comma
# or expanding "INR" to "Rs", and failing those would throw away good
# extractions. Below this, it is not a quote any more.
WORD_OVERLAP_NEEDED = 0.8


def quote_is_in_document(quote, document_text):
    """
    Did this sentence come from the document?

    First an exact check on the squashed text, which is what a clean
    copy paste gives. Then a word overlap check, which forgives small
    re-typing but not invention, because an invented sentence shares
    almost no uncommon words with the source.
    """
    clean_quote = normalise(quote)
    clean_document = normalise(document_text)

    if not clean_quote:
        return False

    if clean_quote in clean_document:
        return True

    quote_words = clean_quote.split()
    if not quote_words:
        return False

    document_words = set(clean_document.split())
    matched = sum(1 for word in quote_words if word in document_words)
    return matched / len(quote_words) >= WORD_OVERLAP_NEEDED


def check_numeric(value, quote):
    """The number has to be written in the sentence."""
    if not contains_number(quote, value):
        return False, f"{value} does not appear in the quoted sentence"
    return True, None


def mentions(word, clean_quote):
    """
    Does this sentence really use this word?

    Short codes have to match as whole words. A plain substring test
    looked fine until a test caught it: "st" sits inside "must", so
    every sentence in the corpus appeared to mention Scheduled Tribes,
    and "sc" sits inside "scheduled", so the check on SC was passing for
    a reason that had nothing to do with SC. Anything built on that was
    only pretending to be verified.

    Longer words stay as substring matches, so "master" still finds
    "masters" and "post-graduate" still finds "post-graduates".
    """
    word = word.strip()
    if not word:
        return False

    if len(word) <= 4:
        # A word boundary in front, and no letter behind, so "sc" hits
        # "SC category" but not "scheduled".
        return re.search(rf"\b{re.escape(word)}(?![a-z])", clean_quote) is not None

    return word in clean_quote


def check_list(values, quote, field=None):
    """
    Every value in the list has to be recognisable in the sentence.

    A document says "Scheduled Caste", not "SC", so the check looks for
    any of the words that mean that value rather than the value itself.
    States are matched on their full name plus the short forms real
    documents use, because "colleges in MP" is how a Madhya Pradesh rule
    actually gets written.
    """
    clean_quote = normalise(quote)

    for value in values:
        if field == "states":
            words = [value.lower()] + STATE_WORDS.get(value, [])
        else:
            words = VALUE_WORDS.get(value, [value.lower()])

        if not any(mentions(word, clean_quote) for word in words):
            return False, f"nothing in the quoted sentence means {value!r}"

    return True, None


def check_deadline(value, quote):
    """
    The year has to be in the sentence.

    Only the year, not the whole date. The model converts "31st October
    2026" into 2026-10-31, so the day and month are never going to be
    there in the stored format, but a fabricated year is the mistake
    that actually matters here.
    """
    year = value.split("-")[0]
    if year not in quote:
        return False, f"the year {year} does not appear in the quoted sentence"
    return True, None


def verify_extraction(extracted, document_text):
    """
    Check every filled in field of one extraction.

    Returns (clean_values, field_sources, unknown_fields, confidence).

    clean_values     what is safe to write into the columns
    field_sources    the full record, kept in JSONB, including failures
    unknown_fields   fields the model filled in that I could not confirm
    confidence       verified / attempted, as a plain measured fraction
    """
    clean_values = {}
    field_sources = {}
    unknown_fields = []

    fields = NUMERIC_FIELDS + LIST_FIELDS + ["deadline"]

    for field in fields:
        value = extracted.get(field)
        quote = extracted.get(f"{field}_quote")

        # The model left it empty, which means "this scheme sets no
        # limit here". That is an answer, so it is not counted as an
        # attempt and it does not drag the confidence down.
        if value is None or (isinstance(value, list) and not value):
            clean_values[field] = None
            continue

        ok, reason = _check_one(field, value, quote, document_text)

        field_sources[field] = {
            "value": value,
            "quote": quote,
            "verified": ok,
            "reason": reason,
        }

        if ok:
            clean_values[field] = value
        else:
            # Rejected. The column stays NULL so the SQL filter still
            # offers the scheme as a candidate, but the field name is
            # recorded so the answering layer refuses to state it.
            clean_values[field] = None
            unknown_fields.append(field)

    attempted = len(field_sources)
    verified = sum(1 for record in field_sources.values() if record["verified"])
    confidence = round(verified / attempted, 2) if attempted else 1.0

    return clean_values, field_sources, unknown_fields, confidence


def _check_one(field, value, quote, document_text):
    """Run the right check for one field. Returns (ok, reason)."""
    if not quote:
        return False, "the model gave a value with no quote"

    if not quote_is_in_document(quote, document_text):
        return False, "the quoted sentence is not in the document"

    if field in NUMERIC_FIELDS:
        return check_numeric(value, quote)

    if field in LIST_FIELDS:
        return check_list(value, quote, field=field)

    if field == "deadline":
        return check_deadline(value, quote)

    return True, None
