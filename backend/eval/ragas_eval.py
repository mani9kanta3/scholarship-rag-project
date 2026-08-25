"""
The four standard RAG metrics, from RAGAS rather than from me.

    pip install ragas langchain-groq
    python -m eval.ragas_eval
    python -m eval.ragas_eval --runs 3      report the spread

run_eval.py measures the things that are specific to this design:
threshold accuracy, abstention in both directions, and whether a
generated number can be traced to a source. No library has those,
because they only mean something given how this system is built.

RAGAS is here for the opposite reason. Faithfulness, answer relevancy,
context precision and context recall are the standard names, and quoting
standard metrics is fairer to an interviewer than quoting four numbers I
invented and defined myself.

**It is a judge, so it wobbles.** RAGAS asks a language model to break
an answer into claims and check each one, so the same answer scores
slightly differently on different runs. --runs 3 runs it three times and
reports the spread as well as the mean. A single decimal from a metric
that moves is a false precision, and knowing your own metric has
variance is worth more than the metric.

The contexts are rebuilt by re-running retrieval rather than read from
the saved results. Retrieval is deterministic given the same index and
costs no tokens, so this reproduces exactly what each answer was written
from without having to store it twice.
"""

import json
import statistics
import sys

from app import config, embeddings, llm, retrieval

from .questions import QUESTIONS

RESULTS_DIR = config.DATA_DIR / "eval"
BY_ID = {question["id"]: question for question in QUESTIONS}


def rebuild_contexts(row):
    """Get back the chunks this answer was written from."""
    question = BY_ID[row["id"]]

    if row["retrieved_scheme_ids"]:
        chunks, _ = retrieval.hybrid_retrieve(
            question["question"],
            profile=question.get("profile"),
            scheme_ids=row["retrieved_scheme_ids"],
            use_reranker=True,
        )
    else:
        chunks = retrieval.naive_retrieve(question["question"])

    return [chunk["chunk_text"] for chunk in chunks]


def build_dataset(name):
    """Turn one results file into the shape RAGAS wants."""
    path = RESULTS_DIR / f"results_{name}.json"
    if not path.exists():
        raise SystemExit(f"No results for {name}. Run python -m eval.run_eval first.")

    rows = json.loads(path.read_text(encoding="utf-8"))

    samples = []
    for row in rows:
        # Trap questions are left out. The correct answer to them is a
        # refusal, and faithfulness has nothing to measure when there is
        # deliberately no supporting context. Their scoring lives in the
        # abstention numbers instead.
        if row["expected_abstain"]:
            continue

        samples.append(
            {
                "user_input": row["question"],
                "response": row["answer"] or "",
                "retrieved_contexts": rebuild_contexts(row),
                "reference": BY_ID[row["id"]]["expected_answer"],
            }
        )

    return samples


def get_scorers():
    """
    Wire RAGAS up to the same models this project already uses.

    Groq for the judging, and the same local bge-small that built the
    index for the embedding based metrics. Using a different embedding
    model here would be measuring a retriever I did not build.
    """
    from langchain_groq import ChatGroq
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
    )

    judge = LangchainLLMWrapper(
        ChatGroq(model=llm.model_name("judge"), api_key=config.GROQ_API_KEY, temperature=0)
    )

    class LocalEmbeddings:
        """The project's own embedding model, in the shape LangChain expects."""

        def embed_documents(self, texts):
            return embeddings.embed_texts(texts)

        def embed_query(self, text):
            return embeddings.embed_query(text)

    wrapped_embeddings = LangchainEmbeddingsWrapper(LocalEmbeddings())

    return [
        Faithfulness(llm=judge),
        AnswerRelevancy(llm=judge, embeddings=wrapped_embeddings),
        ContextPrecision(llm=judge),
        ContextRecall(llm=judge),
    ]


def score_once(samples):
    """One RAGAS pass. Returns {metric: mean score}."""
    from ragas import evaluate
    from ragas.dataset_schema import EvaluationDataset

    dataset = EvaluationDataset.from_list(samples)
    result = evaluate(dataset=dataset, metrics=get_scorers())

    scores = {}
    for metric, value in result._repr_dict.items():
        scores[metric] = round(float(value), 3)
    return scores


def main():
    name = "hybrid"
    if "--config" in sys.argv:
        name = sys.argv[sys.argv.index("--config") + 1]

    runs = 1
    if "--runs" in sys.argv:
        runs = int(sys.argv[sys.argv.index("--runs") + 1])

    samples = build_dataset(name)
    print(f"{len(samples)} answerable questions from the {name} run")
    print(f"judged by {llm.model_name('judge')}, {runs} run(s)\n")

    all_runs = []
    for number in range(runs):
        print(f"run {number + 1} of {runs} ...")
        all_runs.append(score_once(samples))

    metrics = sorted({key for run in all_runs for key in run})

    print("\n--- RAGAS ---")
    summary = {}
    for metric in metrics:
        values = [run[metric] for run in all_runs if metric in run]
        mean = round(statistics.mean(values), 3)
        spread = round(max(values) - min(values), 3) if len(values) > 1 else 0.0
        summary[metric] = {"mean": mean, "spread": spread, "runs": values}
        note = f"  (spread {spread} across {len(values)} runs)" if len(values) > 1 else ""
        print(f"  {metric:<20} {mean}{note}")

    if runs == 1:
        print("\nOne run only. These move a little between runs because RAGAS")
        print("grades with a language model, so quote them with --runs 3.")

    path = RESULTS_DIR / f"ragas_{name}.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWritten to {path}")


if __name__ == "__main__":
    main()
