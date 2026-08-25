"""
Getting the right chunks in front of the model.

Two modes live here on purpose, and the whole project is the difference
between them.

**naive** is the baseline I built first, deliberately, so that I would
have a "before" number. It embeds the question, searches every chunk in
the corpus, and hands back the closest ones. This is what most tutorial
RAG does, and on threshold questions it is close to guessing, because
"income below 2.5 lakh" and "income below 8 lakh" sit almost on top of
each other in embedding space.

**hybrid** filters in SQL first and only then searches, inside the
schemes that survived. The relational filter is doing the arithmetic and
the embeddings are only doing what they are good at, which is finding
the passage that talks about the thing the student asked about.

Chroma's own metadata filter cannot replace the SQL step. Six nullable
columns where NULL means "no constraint" is a relational query, not a
metadata match, so Postgres works out the ids and then hands them to
Chroma as a plain "$in" list. That handoff is the seam between the two
stores and it is the design.
"""

import re

from . import config, db, eligibility, embeddings, reranker, vector_store


def _search(question, limit, scheme_ids=None):
    """Embed the question and ask the vector store for the closest chunks."""
    query_vector = embeddings.embed_query(question)
    return vector_store.search(query_vector, limit=limit, scheme_ids=scheme_ids)


def naive_retrieve(question, limit=None, use_reranker=False):
    """
    The baseline. Semantic search over everything, no filtering.

    Kept in the codebase rather than deleted after it was beaten,
    because the comparison table in the README is the most useful thing
    the project produces and it needs both numbers to keep being true.
    """
    limit = limit or config.CANDIDATE_CHUNKS
    hits = _search(question, limit=limit)

    if use_reranker:
        return reranker.rerank(question, hits)

    return hits[: config.CONTEXT_CHUNKS]


def hybrid_retrieve(question, profile=None, scheme_ids=None, use_reranker=True):
    """
    Filter first, then search inside what survived.

    scheme_ids, when given, is a scheme the question already named, so
    the search is scoped to it directly. Otherwise the profile goes
    through the SQL filter and the ids it returns become the scope.

    Returns (chunks, eligible_ids). eligible_ids is returned even when
    it is empty, because an empty list is a real answer that the caller
    has to abstain on, not an error and not a reason to go and search
    everything instead.
    """
    if scheme_ids is None and profile:
        scheme_ids = [scheme["id"] for scheme in eligibility.find_matches(profile)]

    hits = _search(question, limit=config.CANDIDATE_CHUNKS, scheme_ids=scheme_ids)

    if use_reranker:
        hits = reranker.rerank(question, hits)
    else:
        hits = hits[: config.CONTEXT_CHUNKS]

    return hits, scheme_ids


def find_named_scheme(question):
    """
    Did the question name a scheme we hold?

    This is the cheap intent heuristic the guide asks for instead of an
    agent. It scores each scheme name by how many of its distinctive
    words appear in the question. "Tell me about the Pragati scholarship"
    hits AICTE Pragati Scholarship for Girls and nothing else.

    Common words are ignored, otherwise every scheme with "scholarship"
    in its name would match every question ever asked.
    """
    schemes = db.fetch_all("SELECT id, name FROM scheme ORDER BY id")

    words_in_question = set(re.findall(r"[a-z]+", question.lower()))

    ignore = {
        "scholarship", "scholarships", "scheme", "schemes", "for", "of", "the",
        "and", "students", "student", "national", "india", "indian", "post",
        "pre", "class", "category", "programme", "program", "fellowship",
    }

    best_id = None
    best_score = (0, 0.0)

    for scheme in schemes:
        name_words = set(re.findall(r"[a-z]+", scheme["name"].lower())) - ignore
        if not name_words:
            continue

        overlap = len(name_words & words_in_question)

        # At least two distinctive words, or one word that is most of a
        # short name. One word out of eight is a coincidence.
        if overlap < 2 and not (overlap == 1 and len(name_words) <= 2):
            continue

        # Two scores, in order. How many distinctive words matched, then
        # what share of the name they were.
        #
        # The share is the tie breaker and it earns its place. "Post
        # Matric Scholarship for SC Students" matches two words of the
        # scheme by that exact name, and also two words of "NSP
        # Pre-Matric Scholarship Scheme for SC Students, Chandigarh".
        # On count alone it is a coin toss decided by row order. On
        # share, the first is 2 words out of 2 and the second is 2 out
        # of 6, so the one the student actually named wins.
        share = overlap / len(name_words)
        if (overlap, share) > best_score:
            best_score = (overlap, share)
            best_id = scheme["id"]

    return best_id


def route(question, profile=None):
    """
    Decide which of the two query modes this question is.

    "scheme_detail"  the question named a scheme, so scope to it
    "eligibility"    a profile was given, so filter on it
    "open"           neither, so search the whole corpus

    A heuristic, not a classifier and definitely not an agent. There are
    two outcomes and one of them is decided by whether a form was filled
    in, so anything cleverer would be machinery for its own sake.
    """
    named = find_named_scheme(question)
    if named is not None:
        return "scheme_detail", [named]

    if profile:
        return "eligibility", None

    return "open", None
