"""
Check the held-out questions against the documents before using them.

    python -m eval.check_holdout

This is not an evaluation. It never calls a model and it never scores
the system. It asks two things: does the answer I wrote by hand agree
with what the data says, and is there any scheme here whose document
states a rule the criteria table cannot hold.

The second check exists because the first draft of the held-out set was
wrong and this file did not catch it.

I wrote nine of the questions from the eligibility_criteria columns
rather than from the scheme documents. That table keeps one value per
rule, so a scheme like the National Overseas Scholarship, which sets 35
years for a Master's, 40 for a PhD and 45 for post-doctoral study,
appears in it as a single max_age of 45. I read 45, wrote a question
about a 45 year old Master's applicant, and marked them eligible. The
document says they are not.

Three questions were wrong that way, and all three were wrong in the
direction that agreed with the system, because the system reads the same
flattened column I did. A checker that compares my answers against that
column cannot see any of it: it just finds agreement and reports that
everything is fine, which is exactly what it did.

So the scan below reads the documents instead and flags any scheme
stating more than one threshold. Those are the schemes where ground
truth has to be read from the text, and where the system is expected to
be wrong no matter how good the retrieval is.
"""

import re

from app import db, eligibility

from .holdout_questions import HOLDOUT_QUESTIONS

EXPECTED_SPLIT = {"eligibility": 8, "threshold": 10, "detail": 6, "trap": 6}

# Two or more of these in one eligibility section means the rule varies
# by something, and the single column in the table is a flattening of it.
MARKS = re.compile(r"(\d{2}(?:\.\d+)?)\s*%")
AGES = re.compile(r"(\d{2})\s*years")


def expected_verdict(question):
    """Read yes or no off the front of the expected answer."""
    answer = question["expected_answer"].strip().lower()
    if answer.startswith("yes"):
        return True
    if answer.startswith("no"):
        return False
    return None


def check_shape(problems):
    ids = [q["id"] for q in HOLDOUT_QUESTIONS]
    if len(set(ids)) != len(ids):
        problems.append("duplicate question ids")

    split = {}
    for question in HOLDOUT_QUESTIONS:
        split[question["type"]] = split.get(question["type"], 0) + 1
    if split != EXPECTED_SPLIT:
        problems.append(f"split is {split}, expected {EXPECTED_SPLIT}")

    for question in HOLDOUT_QUESTIONS:
        if question["type"] == "trap" and not question["expected_abstain"]:
            problems.append(f"q{question['id']}: a trap that does not expect a refusal")
        if question["type"] != "trap" and question["expected_abstain"]:
            problems.append(f"q{question['id']}: expects a refusal but is not a trap")

    return split


def check_arithmetic(problems, gaps):
    """
    Settle every profile question in SQL and compare with what I wrote.

    A disagreement is usually my arithmetic. It is not always: where the
    document states a rule the table cannot hold, the two genuinely
    differ, and the question records that on itself. Those are listed
    rather than reported as mistakes, because they are the finding.
    """
    checked = 0
    for question in HOLDOUT_QUESTIONS:
        if question["type"] not in ("eligibility", "threshold"):
            continue
        if not question["profile"] or len(question["expected_scheme_ids"]) != 1:
            continue

        mine = expected_verdict(question)
        if mine is None:
            problems.append(f"q{question['id']}: expected answer starts with neither yes nor no")
            continue

        verdict = eligibility.check_one(question["profile"], question["expected_scheme_ids"][0])
        checked += 1

        if verdict["eligible"] == mine:
            continue

        known = question.get("table_disagrees")
        if known:
            gaps.append(f"q{question['id']}: {known}")
        else:
            problems.append(
                f"q{question['id']}: I wrote {'yes' if mine else 'no'}, "
                f"the criteria table says {'yes' if verdict['eligible'] else 'no'}. "
                f"Reasons: {'; '.join(verdict['reasons'])}"
            )

    return checked


def find_flattened_rules():
    """
    The check that would have caught the first draft.

    Count the thresholds each scheme's own document states. The table
    holds one. More than one in the text means the column is a summary
    of several rules, and ground truth must come from the text.
    """
    used = sorted({i for q in HOLDOUT_QUESTIONS for i in q["expected_scheme_ids"]})
    if not used:
        return []

    rows = db.fetch_all(
        """
        SELECT s.id, s.name, c.chunk_text
        FROM document_chunk c
        JOIN scheme s ON s.id = c.scheme_id
        WHERE c.scheme_id = ANY(%(ids)s) AND c.section = 'eligibility'
        ORDER BY s.id
        """,
        {"ids": used},
    )

    found = []
    for row in rows:
        marks = sorted(set(MARKS.findall(row["chunk_text"])))
        ages = sorted(set(AGES.findall(row["chunk_text"])))
        parts = []
        if len(marks) > 1:
            parts.append(f"marks {marks}")
        if len(ages) > 1:
            parts.append(f"ages {ages}")
        if parts:
            found.append(f"[{row['id']:>2}] {row['name'][:42]}: {', '.join(parts)}")

    return found


def main():
    problems = []
    gaps = []

    split = check_shape(problems)
    checked = check_arithmetic(problems, gaps)
    flattened = find_flattened_rules()

    print(f"{len(HOLDOUT_QUESTIONS)} held-out questions")
    for kind, count in sorted(split.items()):
        print(f"  {kind:<12} {count}")
    print(f"\n{checked} settled in SQL and compared against what I wrote.")

    if flattened:
        print(f"\n{len(flattened)} scheme(s) state more than one threshold in their own")
        print("document while the table keeps a single value. Ground truth for")
        print("these has to be read from the document, never from the column:")
        for line in flattened:
            print(f"  - {line}")

    if gaps:
        print(f"\n{len(gaps)} question(s) where the document and the table genuinely")
        print("disagree. Recorded on the question, and expected to be failed:")
        for line in gaps:
            print(f"  - {line}")

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        raise SystemExit(1)

    print("\nEvery hand written verdict is accounted for.")


if __name__ == "__main__":
    main()
