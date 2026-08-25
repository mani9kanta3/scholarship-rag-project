"""
The cross encoder that re-scores retrieved chunks.

Embedding search is a shortcut. The question and every chunk were turned
into vectors separately, long before the question existed, and then
compared. That is fast because the chunk vectors are computed once, but
the model never actually read the question and the chunk together.

A cross encoder does read them together, one pair at a time, and scores
how well the chunk answers the question. It is much better and much
slower, which is why it runs on 20 chunks instead of 264.

**Whether it is worth the latency is a measurement, not an opinion.**
eval/run_eval.py runs with it on and off and reports both, because
"I added a reranker because that is what you do" is a bad answer and
"it moved context precision this much for that many milliseconds" is a
good one.
"""

from . import config

_model = None


def get_model():
    """Load the cross encoder once."""
    global _model
    if _model is None:
        # Imported here rather than at the top so that a run which never
        # reranks, like the naive baseline, does not pay to load it.
        from sentence_transformers import CrossEncoder

        print(f"Loading reranker {config.RERANKER_MODEL} ...")
        _model = CrossEncoder(config.RERANKER_MODEL, cache_folder=str(config.MODEL_DIR))
    return _model


def rerank(question, hits, top_k=None):
    """
    Re-score chunks against the question and keep the best few.

    The score replaces "similarity" with "rerank_score". The old
    similarity is kept as "vector_similarity" because the abstention
    rule and the query log both want to know how the retrieval itself
    did, separately from how the reranker rated it.
    """
    top_k = top_k or config.CONTEXT_CHUNKS

    if not hits:
        return []

    pairs = [(question, hit["chunk_text"]) for hit in hits]
    scores = get_model().predict(pairs)

    scored = []
    for hit, score in zip(hits, scores):
        item = dict(hit)
        item["vector_similarity"] = hit["similarity"]
        # The raw output is a logit, roughly -11 to +11. Squashing it to
        # 0 to 1 makes it readable next to the cosine score and does not
        # change the ordering at all.
        item["rerank_score"] = round(float(1 / (1 + pow(2.718281828, -score))), 4)
        scored.append(item)

    scored.sort(key=lambda item: item["rerank_score"], reverse=True)
    return scored[:top_k]
