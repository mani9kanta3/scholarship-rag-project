"""
Ask the system a question from the terminal.

    python -m scripts.ask "What documents do I need for the Pragati Scholarship?"
    python -m scripts.ask --naive "What is the income limit for the Central Sector Scheme?"

Useful while working on the pipeline, because it prints the parts the
API response hides: which schemes the SQL filter left, what was
retrieved and with what score, and why an answer was refused. Reading
that is how most of the bugs in this project were found.
"""

import sys

from app import answering, llm


def main():
    arguments = [item for item in sys.argv[1:] if not item.startswith("--")]
    if not arguments:
        print(__doc__)
        return

    question = " ".join(arguments)
    mode = "naive" if "--naive" in sys.argv else "hybrid"
    use_reranker = "--no-rerank" not in sys.argv

    print(f"provider {llm.model_name()}   mode {mode}   reranker {use_reranker}")
    print(f"\nQ: {question}\n")

    result = answering.answer_question(
        question,
        mode=mode,
        use_reranker=use_reranker,
        run_judge="--judge" in sys.argv,
        log=False,
    )

    if result["abstained"]:
        print("REFUSED")
        print(f"  reason: {result['abstain_reason']}")
        print(f"\n{result['answer']}")
    else:
        print(result["answer"])

    if result.get("citations"):
        print("\nSources:")
        for citation in result["citations"]:
            print(f"  [{citation['number']}] {citation['scheme_name']} ({citation['section']})")
            print(f"      {citation['source_url']}")

    for warning in result.get("warnings", []):
        print(f"\nWarning: {warning}")

    print(
        f"\neligible schemes: {result.get('eligible_count')}   "
        f"top score: {result.get('top_score')}   "
        f"grounded: {result.get('grounded')}   "
        f"{result['latency_ms']} ms   {result.get('tokens', 0)} tokens"
    )


if __name__ == "__main__":
    main()
