"""
Re-grade the trap questions from answers that were already produced.

    python -m eval.regrade_traps

I changed my mind about how a trap question should be graded, after a
run had already finished. The first version marked a trap correct only
if one of my abstention rules fired. That measures whether my rules
fired, which is not the same as whether the student was told the truth:
"the sources do not give a phone number for this scheme" is an honest
and correct answer even though no rule caught it.

Rather than re-run the whole evaluation, which costs a day's worth of
free tier tokens, this re-reads the saved answers and asks the judge
only about the trap questions the pipeline let through. About two dozen
calls instead of two hundred.

That is the point of writing every answer to disk as it is produced. A
change of mind about scoring should cost the scoring, not the run.
"""

import json

from app import config, db, llm

from .judge import grade
from .questions import QUESTIONS
from .run_eval import CONFIGS, compute_metrics, print_table

RESULTS_DIR = config.DATA_DIR / "eval"

BY_ID = {question["id"]: question for question in QUESTIONS}


def regrade_file(name):
    path = RESULTS_DIR / f"results_{name}.json"
    if not path.exists():
        print(f"  no results for {name}, skipping")
        return None

    rows = json.loads(path.read_text(encoding="utf-8"))
    changed = 0

    for row in rows:
        if not row["expected_abstain"]:
            continue

        if row["abstained"]:
            # A rule fired. Correct by definition, nothing to ask.
            if not row["correct"]:
                row["correct"] = True
                row["judge_reason"] = "the pipeline refused, which is what this question wants"
                changed += 1
            continue

        # It answered. Did it answer honestly?
        correct, reason, _ = grade(
            row["question"],
            BY_ID[row["id"]]["expected_answer"],
            row["answer"],
        )

        if correct != row["correct"]:
            changed += 1

        row["correct"] = correct
        row["judge_reason"] = reason

    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"  {name}: {changed} verdicts changed")
    return rows


def main():
    print(f"Re-grading trap questions, judge is {llm.model_name('judge')}")

    all_metrics = {}

    for settings in CONFIGS:
        rows = regrade_file(settings["name"])
        if rows is None:
            continue

        metrics = compute_metrics(rows)
        all_metrics[settings["name"]] = metrics

        # Replace the stored run rather than adding another, so
        # /api/eval/latest does not end up showing two versions of the
        # same run with different scoring.
        db.execute(
            """
            UPDATE eval_run
            SET metrics = %(metrics)s
            WHERE id = (
                SELECT id FROM eval_run
                WHERE config->>'name' = %(name)s
                ORDER BY run_at DESC
                LIMIT 1
            )
            """,
            {"metrics": json.dumps(metrics), "name": settings["name"]},
        )

    print_table(all_metrics)

    (RESULTS_DIR / "metrics.json").write_text(json.dumps(all_metrics, indent=2), encoding="utf-8")
    print(f"\nMetrics rewritten to {RESULTS_DIR / 'metrics.json'}")


if __name__ == "__main__":
    main()
