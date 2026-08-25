"""
Checking the grader.

Answer correctness in run_eval.py is decided by a language model. That
model is not checked by anything, which means the headline number in my
README rests on a measurement nobody has measured.

So this does the boring thing. It takes twenty answers from the last
run, writes them into a file with the judge's verdict hidden, and waits
for me to grade them myself. Then it compares the two and reports how
often we agreed.

    python -m eval.calibrate_judge --prepare     write the file
    ... grade the twenty by hand ...
    python -m eval.calibrate_judge               report the agreement

If the judge agrees with me ninety percent of the time, the correctness
scores mean roughly what they say. If it agrees sixty five percent of
the time they do not, and the fix is a better grading prompt or a
stronger model for grading, not more decimal places.

The judge's own verdict is deliberately kept out of the file. Seeing it
first would make me agree with it, and then the agreement rate would be
measuring nothing at all.
"""

import json
import random
import sys

from app import config

from .questions import QUESTIONS

# The per question results hold what the system said, not what it should
# have said, so the expected answer is looked up here. Without this the
# whole file said "(a refusal)" under every question and there would
# have been nothing to grade against.
EXPECTED = {question["id"]: question for question in QUESTIONS}

RESULTS = config.DATA_DIR / "eval"
LABELS_FILE = RESULTS / "hand_labels.md"
SAMPLE_SIZE = 20


def prepare():
    """Write twenty answers out for grading, without the judge's verdict."""
    source = RESULTS / "results_hybrid.json"
    if not source.exists():
        print("Run python -m eval.run_eval first.")
        return

    rows = json.loads(source.read_text(encoding="utf-8"))

    # A fixed seed, so re-running this picks the same twenty and my
    # earlier grading still applies. A different sample each time would
    # make the agreement rate wander for no reason.
    random.seed(42)
    sample = random.sample(rows, min(SAMPLE_SIZE, len(rows)))
    sample.sort(key=lambda row: row["id"])

    lines = [
        "# Judge calibration",
        "",
        f"{len(sample)} answers from the last hybrid run.",
        "",
        "For each one, read the question, what the answer should say, and what the",
        "system actually said. Then write `yes` or `no` after `My verdict:`.",
        "",
        "Grade it the way the judge was told to: do the facts agree? Ignore wording.",
        "A refusal is only correct when the expected answer is itself a refusal.",
        "",
        "The judge's own verdict is not in this file on purpose. If I could see it",
        "I would agree with it, and the agreement rate would measure nothing.",
        "",
        "---",
        "",
    ]

    for row in sample:
        question = EXPECTED[row["id"]]

        lines.append(f"## Question {row['id']} ({row['type']})")
        lines.append("")
        lines.append(f"**Asked:** {row['question']}")
        lines.append("")

        if question["profile"]:
            given = ", ".join(
                f"{field} {value}"
                for field, value in question["profile"].items()
                if value is not None
            )
            lines.append(f"**The student said:** {given}")
            lines.append("")

        lines.append(f"**Should say:** {question['expected_answer']}")
        lines.append("")
        lines.append("**System said:**")
        lines.append("")
        lines.append("> " + (row["answer"] or "").replace("\n", "\n> "))
        lines.append("")
        lines.append("My verdict: ")
        lines.append("")
        lines.append("---")
        lines.append("")

    RESULTS.mkdir(parents=True, exist_ok=True)
    LABELS_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {len(sample)} answers to {LABELS_FILE}")
    print("Grade them, then run this again with no arguments.")


def read_hand_labels():
    """Read my yes/no answers back out of the file."""
    labels = {}
    current = None

    for line in LABELS_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        if stripped.startswith("## Question "):
            current = int(stripped.split()[2])

        if stripped.lower().startswith("my verdict:") and current is not None:
            verdict = stripped.split(":", 1)[1].strip().lower()
            if verdict in ("yes", "y", "correct"):
                labels[current] = True
            elif verdict in ("no", "n", "wrong", "incorrect"):
                labels[current] = False
            # Anything else, including blank, means I have not graded it.

    return labels


def report():
    """Compare my grading against the judge's."""
    if not LABELS_FILE.exists():
        print("No labels file. Run with --prepare first.")
        return

    rows = json.loads((RESULTS / "results_hybrid.json").read_text(encoding="utf-8"))
    judge = {row["id"]: row["correct"] for row in rows}
    by_id = {row["id"]: row for row in rows}

    mine = read_hand_labels()

    if not mine:
        print(f"Nothing graded yet in {LABELS_FILE}.")
        print("Write yes or no after each 'My verdict:' line.")
        return

    agreed = 0
    disagreements = []

    for question_id, my_verdict in mine.items():
        if judge.get(question_id) == my_verdict:
            agreed += 1
        else:
            disagreements.append((question_id, my_verdict, judge.get(question_id)))

    rate = agreed / len(mine)

    print(f"Graded by hand: {len(mine)}")
    print(f"Agreement with the judge: {agreed}/{len(mine)} = {rate:.2f}")

    if disagreements:
        print("\nWhere we disagreed:")
        for question_id, my_verdict, judge_verdict in disagreements:
            row = by_id[question_id]
            print(f"\n  Question {question_id} ({row['type']})")
            print(f"    me: {my_verdict}   judge: {judge_verdict}")
            print(f"    judge said: {row['judge_reason']}")

    print("")
    if rate >= 0.9:
        print("The correctness numbers can be quoted as they stand.")
    elif rate >= 0.75:
        print("Usable, but quote the agreement rate alongside the scores.")
    else:
        print("Too low to trust. The grading prompt or the grading model needs work,")
        print("and the correctness numbers should not be quoted until it improves.")

    (RESULTS / "judge_calibration.json").write_text(
        json.dumps(
            {
                "hand_labelled": len(mine),
                "agreed": agreed,
                "agreement_rate": round(rate, 3),
                "disagreements": [
                    {"id": qid, "mine": mine_v, "judge": judge_v}
                    for qid, mine_v, judge_v in disagreements
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    if "--prepare" in sys.argv:
        prepare()
    else:
        report()
