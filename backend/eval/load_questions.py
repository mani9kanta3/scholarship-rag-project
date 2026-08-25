"""
Put the hand written questions into the eval_question table.

    python -m eval.load_questions

The questions live in questions.py, as Python, because that is where I
edit them and a code review of the eval set is a real thing I want to be
able to do. The table is the copy the guide's data model asks for, so
the questions sit next to the runs that were scored against them and a
result can always be traced back to the exact question it came from.

Running this again replaces the lot. There is no partial update, because
a half updated eval set that still reports old numbers is worse than one
that is obviously stale.
"""

import json

from app import db

from .questions import QUESTIONS


def main():
    db.execute("TRUNCATE eval_question RESTART IDENTITY")

    for question in QUESTIONS:
        db.execute(
            """
            INSERT INTO eval_question
                (question, profile, expected_scheme_ids, expected_answer,
                 expected_abstain, question_type, why_it_exists)
            VALUES
                (%(question)s, %(profile)s, %(scheme_ids)s, %(expected_answer)s,
                 %(expected_abstain)s, %(question_type)s, %(why)s)
            """,
            {
                "question": question["question"],
                "profile": json.dumps(question["profile"]) if question["profile"] else None,
                "scheme_ids": question["expected_scheme_ids"],
                "expected_answer": question["expected_answer"],
                "expected_abstain": question["expected_abstain"],
                "question_type": question["type"],
                "why": question["why"],
            },
        )

    rows = db.fetch_all(
        "SELECT question_type, count(*) AS n FROM eval_question GROUP BY question_type ORDER BY question_type"
    )

    print(f"Loaded {len(QUESTIONS)} questions.")
    for row in rows:
        print(f"  {row['question_type']:<12} {row['n']}")


if __name__ == "__main__":
    main()
