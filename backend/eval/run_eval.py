"""
Run the eval set through every configuration and write down the numbers.

    python -m eval.run_eval                 all configurations
    python -m eval.run_eval --only hybrid   just one

Three configurations run:

**naive** is the baseline. Semantic search over the whole corpus, no SQL
filter, no reranker, and abstention turned off. This is what most
tutorial RAG builds, and it is here so the comparison table has a real
"before" number rather than a remembered one. Turning abstention off for
it matters: refusing is part of what I built, so measuring plain RAG
with my safety rules bolted on would flatter the baseline and prove
nothing.

**hybrid_no_reranker** is the real system with the cross encoder
switched off. It exists to answer "did the reranker actually help", with
a measurement instead of an opinion.

**hybrid** is the whole thing.

Results are written to disk after every question. Free tiers run out,
models return 503, and losing forty answered questions to a crash on
question thirty nine is avoidable.
"""

import json
import sys
import time

from app import answering, config, db, llm

from .judge import grade
from .questions import QUESTIONS

CONFIGS = [
    {
        "name": "naive",
        "mode": "naive",
        "use_reranker": False,
        "enforce_abstention": False,
        # The baseline gets the student's profile too.
        #
        # I had this switched off at first and then realised it made the
        # comparison worthless. Withholding the profile does not measure
        # semantic retrieval against hybrid retrieval, it measures a
        # system that was told the student's marks against one that was
        # not, and of course that wins.
        #
        # So the baseline gets exactly the same information. The profile
        # goes into its prompt as text, the schemes are searched by
        # meaning alone, and the model has to do the arithmetic itself
        # from what it read. That is the real failure being measured,
        # and a beaten baseline is only worth quoting if it was given a
        # fair go.
        "use_profile": True,
    },
    {
        "name": "hybrid_no_reranker",
        "mode": "hybrid",
        "use_reranker": False,
        "enforce_abstention": True,
        "use_profile": True,
    },
    {
        "name": "hybrid",
        "mode": "hybrid",
        "use_reranker": True,
        "enforce_abstention": True,
        "use_profile": True,
    },
]

# A pause between questions. Free tiers count requests per minute and
# each question is two model calls, so this keeps the run under the
# limit instead of relying on the retry to dig it back out.
SECONDS_BETWEEN_QUESTIONS = 2

RESULTS_DIR = config.DATA_DIR / "eval"


def answer_one(question, settings):
    """Put one question through the pipeline under one configuration."""
    profile = question.get("profile") if settings["use_profile"] else None

    return answering.answer_question(
        question["question"],
        profile=profile,
        mode=settings["mode"],
        use_reranker=settings["use_reranker"],
        enforce_abstention=settings["enforce_abstention"],
        # The judge is a separate step below, and running the in-pipeline
        # one as well would double the cost for the same information.
        run_judge=False,
        # Eval traffic is not real traffic. Logging it would pollute the
        # monitoring trend line with a hundred questions asked at once.
        log=False,
    )


def run_config(settings, resume=False):
    """
    Answer and grade every question under one configuration.

    resume picks up from whatever is already in the results file and
    only asks the questions that are missing. The free tier allows a
    fixed number of tokens a day, and a full run of three
    configurations does not fit in one day's allowance, so a run that
    could not be continued tomorrow would simply never finish.
    """
    print(f"\n=== {settings['name']} ===")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"results_{settings['name']}.json"

    rows = []
    if resume and path.exists():
        rows = json.loads(path.read_text(encoding="utf-8"))
        print(f"  resuming, {len(rows)} already done")

    done = {row["id"] for row in rows}
    tokens = 0

    for number, question in enumerate(QUESTIONS, start=1):
        if question["id"] in done:
            continue

        result = answer_one(question, settings)
        tokens += result.get("tokens", 0)

        if question["expected_abstain"] and result["abstained"]:
            # A trap question that the pipeline refused outright. That is
            # the required behaviour, so there is nothing to grade.
            correct = True
            reason = "the pipeline refused, which is what this question wants"
        elif question["expected_abstain"]:
            # A trap question the pipeline let through, so the model
            # wrote something. It still might have been the right thing:
            # "the sources do not give a phone number for this scheme" is
            # a correct answer even though no abstention rule fired.
            #
            # Counting that as a failure would have measured whether my
            # rules fired rather than whether the student was told the
            # truth, and it would have quietly flattered the rules by
            # marking every honest answer they did not catch as wrong.
            correct, reason, judge_tokens = grade(
                question["question"],
                question["expected_answer"],
                result["answer"],
            )
            tokens += judge_tokens
        elif result["abstained"]:
            # It refused a question that had a real answer. That is a
            # wrong answer, and it costs nothing to say so.
            correct = False
            reason = "refused a question that has an answer"
        else:
            correct, reason, judge_tokens = grade(
                question["question"],
                question["expected_answer"],
                result["answer"],
            )
            tokens += judge_tokens

        rows.append(
            {
                "id": question["id"],
                "type": question["type"],
                "question": question["question"],
                "expected_abstain": question["expected_abstain"],
                "expected_scheme_ids": question["expected_scheme_ids"],
                "retrieved_scheme_ids": result["retrieved_scheme_ids"],
                "abstained": result["abstained"],
                "abstain_reason": result.get("abstain_reason"),
                "grounded": result.get("grounded"),
                "unsupported_numbers": result.get("unsupported_numbers", []),
                "unsupported_dates": result.get("unsupported_dates", []),
                "correct": correct,
                "judge_reason": reason,
                "answer": result["answer"],
                "top_score": float(result.get("top_score") or 0),
                "latency_ms": result["latency_ms"],
            }
        )

        # Written every time, not at the end. A crash on question 39
        # should not cost the first 38.
        rows.sort(key=lambda row: row["id"])
        path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

        mark = "ok " if correct else "BAD"
        note = "refused" if result["abstained"] else f"{result['latency_ms']}ms"
        print(f"  [{number:2d}/{len(QUESTIONS)}] {mark} {question['type']:<11} {note}")

        time.sleep(SECONDS_BETWEEN_QUESTIONS)

    return rows, tokens


def share(rows, test):
    """The fraction of rows where test is true. None when there are none."""
    if not rows:
        return None
    return round(sum(1 for row in rows if test(row)) / len(rows), 3)


def compute_metrics(rows):
    """
    Turn the per question rows into the numbers for the README.

    Abstention is reported in both directions on purpose. A system that
    refuses everything scores a perfect recall and is useless, so recall
    without precision is not a result, it is half of one.
    """
    answerable = [row for row in rows if not row["expected_abstain"]]
    traps = [row for row in rows if row["expected_abstain"]]
    thresholds = [row for row in rows if row["type"] == "threshold"]
    answered = [row for row in rows if not row["abstained"]]
    refused = [row for row in rows if row["abstained"]]

    # Only questions that name a specific scheme can be scored on
    # retrieval, so trap questions are left out of this one.
    with_ground_truth = [row for row in rows if row["expected_scheme_ids"]]

    return {
        "questions": len(rows),
        "overall_correctness": share(rows, lambda row: row["correct"]),
        "threshold_correctness": share(thresholds, lambda row: row["correct"]),
        "eligibility_correctness": share(
            [row for row in rows if row["type"] == "eligibility"], lambda row: row["correct"]
        ),
        "detail_correctness": share(
            [row for row in rows if row["type"] == "detail"], lambda row: row["correct"]
        ),
        "retrieval_hit_rate": share(
            with_ground_truth,
            lambda row: bool(set(row["expected_scheme_ids"]) & set(row["retrieved_scheme_ids"])),
        ),
        "groundedness": share(answered, lambda row: row["grounded"] is not False),
        # The headline safety number. An answer that reached a student
        # carrying a figure with no source behind it.
        "hallucinated_numbers": share(
            answered, lambda row: bool(row["unsupported_numbers"] or row["unsupported_dates"])
        ),
        # Two different questions, kept apart on purpose.
        #
        # abstention_recall is strict: did an abstention rule actually
        # fire on a question with no answer in the corpus. That is the
        # thing I built and the thing I can point at.
        #
        # declined_correctly is looser and more useful to a student: was
        # the person told the truth, whether by a rule firing or by the
        # model saying plainly that the sources do not cover it.
        "abstention_recall": share(traps, lambda row: row["abstained"]),
        "declined_correctly": share(traps, lambda row: row["correct"]),
        "abstention_precision": share(refused, lambda row: row["expected_abstain"]),
        "answered_count": len(answered),
        "refused_count": len(refused),
        "mean_latency_ms": int(sum(row["latency_ms"] for row in rows) / len(rows)) if rows else 0,
    }


def save_run(settings, metrics, tokens):
    """Write one row to eval_run so runs can be compared over time."""
    db.execute(
        """
        INSERT INTO eval_run (config, metrics)
        VALUES (%(config)s, %(metrics)s)
        """,
        {
            "config": json.dumps(
                {
                    "mode": settings["name"] if settings["name"] == "naive" else settings["mode"],
                    "name": settings["name"],
                    "model": llm.model_name(),
                    "judge_model": llm.model_name("judge"),
                    "provider": config.LLM_PROVIDER,
                    "embedding_model": config.EMBEDDING_MODEL,
                    "use_reranker": settings["use_reranker"],
                    "enforce_abstention": settings["enforce_abstention"],
                    "questions": metrics["questions"],
                    "tokens": tokens,
                }
            ),
            "metrics": json.dumps(metrics),
        },
    )


def print_table(all_metrics):
    """The comparison table from section 8 of the guide, on the terminal."""
    names = list(all_metrics)
    rows = [
        ("Overall correctness", "overall_correctness"),
        ("Threshold questions", "threshold_correctness"),
        ("Eligibility questions", "eligibility_correctness"),
        ("Detail questions", "detail_correctness"),
        ("Retrieval hit rate", "retrieval_hit_rate"),
        ("Groundedness", "groundedness"),
        ("Answers with invented figure", "hallucinated_numbers"),
        ("Refused when it should", "abstention_recall"),
        ("Said 'not in my sources'", "declined_correctly"),
        ("Refusals that were right", "abstention_precision"),
        ("Mean latency (ms)", "mean_latency_ms"),
    ]

    width = 30
    header = "| " + "Measure".ljust(width) + " | " + " | ".join(name.ljust(18) for name in names) + " |"
    print("\n" + header)
    print("|" + "-" * (width + 2) + "|" + "|".join("-" * 20 for _ in names) + "|")

    for label, key in rows:
        cells = []
        for name in names:
            value = all_metrics[name].get(key)
            cells.append(("-" if value is None else str(value)).ljust(18))
        print("| " + label.ljust(width) + " | " + " | ".join(cells) + " |")


def main():
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]

    resume = "--resume" in sys.argv

    print(f"{len(QUESTIONS)} questions")
    print(f"  answers judged by  {llm.model_name('judge')}")
    print(f"  answers written by {llm.model_name()}")

    all_metrics = {}

    for settings in CONFIGS:
        if only and settings["name"] != only:
            continue

        rows, tokens = run_config(settings, resume=resume)
        metrics = compute_metrics(rows)
        save_run(settings, metrics, tokens)
        all_metrics[settings["name"]] = metrics

        print(f"  -> {tokens} tokens")

    print_table(all_metrics)

    summary = RESULTS_DIR / "metrics.json"
    summary.write_text(json.dumps(all_metrics, indent=2), encoding="utf-8")
    print(f"\nMetrics written to {summary}")


if __name__ == "__main__":
    main()
