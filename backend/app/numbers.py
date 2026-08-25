"""
Pulling numbers out of Indian scholarship text.

This is used twice and both times it is doing the same job: proving that
a number came from somewhere real.

1. At ingestion, to check that the sentence the model quoted actually
   contains the value it claims to have extracted.
2. At answer time, to check that every number in a generated answer
   appears in the retrieved context.

The reason it needs its own file is that the same amount is written five
different ways in this domain:

    2,50,000        Indian digit grouping
    250000          plain
    2.5 lakh        the word does the multiplying
    INR 2.5 Lakhs   currency in front, capital L
    Rs. 2,50,000/-  the whole works

A naive "is the string in the text" check calls all of those different
numbers, so the income limit check would fail on almost every scheme and
I would end up switching the check off. So the numbers are turned into
plain floats first, and compared as floats.
"""

import re

# A number, optionally followed by lakh or crore. The digits part allows
# commas anywhere because Indian grouping is 2,50,000 not 250,000.
NUMBER_PATTERN = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|crores?)?",
    re.IGNORECASE,
)

MULTIPLIERS = {
    "lakh": 100000,
    "lakhs": 100000,
    "lac": 100000,
    "lacs": 100000,
    "crore": 10000000,
    "crores": 10000000,
}


def find_numbers(text):
    """
    Every number in the text, as a set of floats.

    "income of less than INR 2.5 lakhs" gives {250000.0} and not
    {2.5, 250000.0}. The word "lakh" is part of the number, not a
    separate fact, so the amount written there is two hundred and fifty
    thousand and nothing else.

    I had it returning both at first, and it made the grounding check
    reject a correct answer: the context said "INR 2,50,000", the answer
    said "2.5 lakh", and the stray 2.5 from the answer had no source. It
    looked like a hallucination and it was a unit.
    """
    if not text:
        return set()

    found = set()

    for digits, unit in NUMBER_PATTERN.findall(text):
        clean = digits.replace(",", "").rstrip(".")
        if not clean:
            continue

        try:
            value = float(clean)
        except ValueError:
            continue

        if unit:
            found.add(value * MULTIPLIERS[unit.lower()])
        else:
            found.add(value)

    return found


def contains_number(text, value, tolerance=0.01):
    """
    Is this exact value written somewhere in the text?

    The tolerance is for floats. 7.5 read back from the database is not
    always bit for bit the 7.5 parsed out of a sentence, and I do not
    want a rounding artefact to look like a hallucination.
    """
    if value is None:
        return False

    return any(abs(found - float(value)) <= tolerance for found in find_numbers(text))


# Dates, so a fabricated deadline can be caught the same way. Matches
# "31 October 2026", "October 31, 2026", "31-10-2026" and "2026-10-31".
DATE_PATTERN = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4}"
    r"|[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})\b"
)


def find_dates(text):
    """Every date in the text, as the raw strings that were matched."""
    if not text:
        return set()
    return {match.strip() for match in DATE_PATTERN.findall(text)}


def normalise(text):
    """
    Squash a piece of text so two versions of the same sentence match.

    Lowercase, collapse runs of whitespace, drop the punctuation that
    tends to move around when a model re-types a sentence. Used to check
    that a quoted sentence really is in the source document.
    """
    if not text:
        return ""

    lowered = text.lower()
    lowered = re.sub(r"[‘’“”]", "'", lowered)
    lowered = re.sub(r"[^a-z0-9%.,/\-' ]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()

    # Trim the punctuation off each end. A model that re-types a sentence
    # often drops or adds the full stop, and without this the same
    # sentence compares as two different ones.
    return lowered.strip(" .,")
