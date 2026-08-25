"""
The model that grades answers, and the check on the grader.

Correctness cannot be measured with string matching. "The income limit
is 2.5 lakh" and "You need a family income below INR 2,50,000" are the
same answer written two ways, and an exact match test would call the
second one wrong. So a model reads the expected answer and the actual
answer and says whether they agree on the facts.

**Nobody is checking the grader**, which is the obvious hole in that.
calibrate_judge.py exists for exactly this: twenty of these answers get
graded by hand, and the agreement rate between me and the judge is
reported alongside the scores. If it agrees with me ninety percent of
the time, the numbers mean something. If it agrees sixty five percent of
the time, they do not, and no amount of decimal places fixes that.

The judge is told to look at facts and numbers and to ignore wording,
because a difference in phrasing is not a difference in answer, and a
judge that punishes phrasing would quietly reward whichever system
writes in the style of my expected answers.
"""

from pydantic import BaseModel

from app import llm


class CorrectnessVerdict(BaseModel):
    """Typed, so there is nothing to fish out of prose."""

    correct: bool
    reason: str


JUDGE_SYSTEM = """\
You grade answers about Indian scholarship schemes.

You are given a question, the answer that was expected, and the answer a
system actually gave. Decide whether the actual answer agrees with the
expected one on the facts.

How to grade:

- Compare facts, not wording. Different phrasing of the same fact is correct.
- Numbers must agree. "2.5 lakh" and "250000" are the same number and are
  correct. 250000 against 800000 is wrong, however well written.
- An answer that is right but adds extra correct detail is still correct.
- An answer that refuses, or says it does not know, is NOT correct when the
  expected answer contains real information. Refusing is only correct when
  the expected answer is itself a refusal.
- An answer that is partly right and partly wrong is wrong. A student acting
  on the wrong half is the failure this is measuring.\
"""

JUDGE_PROMPT = """\
Question:
{question}

Expected answer:
{expected}

Actual answer:
{actual}

Is the actual answer correct? Give a one sentence reason.\
"""


def grade(question, expected_answer, actual_answer):
    """
    Grade one answer.

    Returns (correct, reason, tokens).
    """
    verdict, tokens = llm.generate_json(
        JUDGE_PROMPT.format(
            question=question,
            expected=expected_answer,
            actual=actual_answer,
        ),
        response_schema=CorrectnessVerdict,
        system_instruction=JUDGE_SYSTEM,
        # A different model from the one that wrote the answer. A model
        # recognises its own phrasing and marks it generously, so this
        # is the cheap version of not marking your own homework.
        model=llm.model_name("judge"),
    )

    return bool(verdict.get("correct")), verdict.get("reason", ""), tokens
