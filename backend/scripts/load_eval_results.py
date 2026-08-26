"""
Put the saved evaluation metrics into the eval_run table.

    python -m scripts.load_eval_results

`GET /api/eval/latest` reads eval_run, and that table is written by
eval/run_eval.py as it goes. A fresh deployment has an empty one, and
re-running the whole evaluation against a hosted database just to fill
it in would cost a day of tokens to reproduce numbers already sitting in
data/eval/metrics.json.

So this reads that file and writes the rows. It is the deployment
counterpart of the extraction cache: the expensive part was done once,
the result is in the repository, and moving it into a new database is
free.

Running it again replaces the rows rather than adding a second copy, so
the endpoint never shows the same run twice.
"""

import json

from app import config, db, llm

METRICS_FILE = config.DATA_DIR / "eval" / "metrics.json"

# Which configuration each name describes, so the stored row matches
# what run_eval.py would have written itself.
CONFIG_SHAPE = {
    "naive": {"mode": "naive", "use_reranker": False, "enforce_abstention": False},
    "hybrid_no_reranker": {"mode": "hybrid", "use_reranker": False, "enforce_abstention": True},
    "hybrid": {"mode": "hybrid", "use_reranker": True, "enforce_abstention": True},
}


def main():
    if not METRICS_FILE.exists():
        raise SystemExit(
            f"No metrics at {METRICS_FILE}. Run python -m eval.run_eval first."
        )

    all_metrics = json.loads(METRICS_FILE.read_text(encoding="utf-8"))

    for name, metrics in all_metrics.items():
        shape = CONFIG_SHAPE.get(name, {"mode": name})

        stored = {
            "name": name,
            "model": llm.model_name(),
            "judge_model": llm.model_name("judge"),
            "provider": config.LLM_PROVIDER,
            "embedding_model": config.EMBEDDING_MODEL,
            "questions": metrics.get("questions"),
            **shape,
        }

        # Delete first, so loading twice does not leave the endpoint
        # showing two versions of the same run.
        db.execute(
            "DELETE FROM eval_run WHERE config->>'name' = %(name)s",
            {"name": name},
        )
        db.execute(
            "INSERT INTO eval_run (config, metrics) VALUES (%(config)s, %(metrics)s)",
            {"config": json.dumps(stored), "metrics": json.dumps(metrics)},
        )

        print(f"  {name}: overall {metrics.get('overall_correctness')}, "
              f"threshold {metrics.get('threshold_correctness')}")

    rows = db.fetch_all("SELECT count(*) AS n FROM eval_run")
    print(f"\neval_run now holds {rows[0]['n']} rows.")
    print("GET /api/eval/latest will show them.")


if __name__ == "__main__":
    main()
