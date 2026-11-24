"""
The query pipeline, start to finish.

route -> retrieve -> generate -> check -> answer or refuse.

Every abstention rule from section 7 of the guide is enforced here, and
they are all in one function on purpose. Refusal is the behaviour I most
need to be able to explain, so it should be readable top to bottom in
one place rather than scattered across the modules that trigger it.

The rules, in the order they are checked:

1. The SQL filter matched nothing. Say that. Do **not** fall back to
   searching the whole corpus for something plausible, because the
   plausible thing is a scheme the student does not qualify for.
2. Nothing was retrieved at all.
3. The best retrieval score is too low to answer from.
4. Everything we could cite comes from an extraction we could not
   verify.
5. Layer 1 found a number or a date in the answer with no source.
6. The judge found a claim the sources do not support.

A refusal that names what is missing is a good answer here. "I do not
have the current income limit for this scheme, here is the source page"
beats a confident guess every single time.
"""

import random
import time
from datetime import date, timedelta

from . import config, db, eligibility, generation, grounding, query_log, retrieval, tracing


def load_schemes(scheme_ids):
    """Everything the answer needs about the schemes it is citing."""
    if not scheme_ids:
        return {}

    rows = db.fetch_all(
        """
        SELECT s.id, s.name, s.provider, s.source_url, s.deadline,
               s.last_updated, s.amount_text,
               c.unknown_fields, c.extraction_confidence
        FROM scheme s
        JOIN eligibility_criteria c ON c.scheme_id = s.id
        WHERE s.id = ANY(%(ids)s)
        """,
        {"ids": list(scheme_ids)},
    )
    return {row["id"]: row for row in rows}


def top_score(chunks):
    """
    The best retrieval score, on the vector scale.

    Always the cosine similarity, never the reranker score, even when
    reranking ran. The two are not on the same scale, and if the query
    log mixed them the trend line would be meaningless.
    """
    if not chunks:
        return 0.0
    return max(chunk.get("vector_similarity", chunk.get("similarity", 0)) for chunk in chunks)


_scheme_total = None


def scheme_total():
    """
    How many schemes are in the corpus.

    Read once and kept. The trace wants to say "9 of 44 passed the
    filter" rather than just "9", because the first one is a result and
    the second one is a number. The corpus does not change while the
    process is running, so asking Postgres every time would be a query
    per question for a figure that cannot move.
    """
    global _scheme_total
    if _scheme_total is None:
        row = db.fetch_one("SELECT COUNT(*) AS total FROM scheme")
        _scheme_total = int(row["total"]) if row else 0
    return _scheme_total


def staleness_warnings(schemes_by_id):
    """
    Warn when a page is old enough that its deadline may have passed.

    Not an abstention on its own. The rest of the scheme is still
    useful, the student just should not trust the date without checking.
    """
    warnings = []
    cutoff = date.today() - timedelta(days=config.STALE_AFTER_DAYS)

    for scheme in schemes_by_id.values():
        if scheme["last_updated"] and scheme["last_updated"] < cutoff:
            warnings.append(
                f"The page for {scheme['name']} was last checked on "
                f"{scheme['last_updated']}, so its deadline may have moved."
            )
        elif scheme["deadline"] and scheme["deadline"] < date.today():
            warnings.append(
                f"The deadline shown for {scheme['name']} "
                f"({scheme['deadline']}) has already passed."
            )

    return warnings


def build_citations(chunks, schemes_by_id):
    """One citation per source block, in the order the model was given them."""
    citations = []

    for number, chunk in enumerate(chunks, start=1):
        scheme = schemes_by_id.get(chunk["scheme_id"], {})
        citations.append(
            {
                "number": number,
                "scheme_id": chunk["scheme_id"],
                "scheme_name": scheme.get("name", "Unknown scheme"),
                "section": chunk["section"],
                "source_url": scheme.get("source_url", ""),
                "source_page": chunk.get("source_page"),
            }
        )

    return citations


def _refuse(reason, message, **extra):
    """Build a refusal. The reason is for the log, the message is for the student."""
    result = {
        "answer": message,
        "abstained": True,
        "abstain_reason": reason,
        "citations": [],
        "warnings": [],
        "grounded": None,
        "tokens": 0,
    }
    result.update(extra)
    return result


def answer_question(
    question,
    profile=None,
    mode="hybrid",
    use_reranker=True,
    run_judge=None,
    log=True,
    enforce_abstention=True,
):
    """
    Answer one question, or refuse to.

    mode is "hybrid" or "naive". The naive path is the baseline the
    project exists to beat, and it is kept working so the comparison in
    the README can be re-run rather than remembered.

    enforce_abstention=False makes the pipeline answer anyway, and just
    report whether the answer was grounded instead of blocking it. That
    is only used by the eval, and only for the baseline, because the
    comparison table needs a fair "before" number. Abstention is part of
    my contribution, so measuring plain RAG *with* my safety rules bolted
    on would be flattering the baseline and the comparison would prove
    nothing. Nothing in production ever passes False.
    """
    started = time.perf_counter()
    tokens = 0
    verdict = None

    # Whatever had been retrieved when the pipeline decided to stop.
    # finish() reads this, so a refusal still reports which schemes were
    # found and still sends them to Langfuse. A refusal is exactly the
    # case where I want to know what was in front of it.
    retrieved = []

    # Every stage of the pipeline writes one line in here as it runs.
    #
    # This exists because the interesting part of this project is
    # invisible. A student sees an answer; what actually happened was a
    # SQL filter, a scoped vector search, a reranker, four abstention
    # rules and two grounding checks, and any one of them can be the
    # reason the answer looks the way it does. Keeping a record of the
    # decisions costs a few dictionaries and makes the whole thing
    # explainable after the fact, including the refusals, which are the
    # cases most worth explaining.
    trace = []

    def step(name, outcome, detail, **numbers):
        """
        Record one stage.

        outcome is one of four. "ok" passed, "skipped" did not run,
        "stopped" means this stage is why there is no answer, so there
        is at most one and it is always last. "failed" means the check
        did not pass but the pipeline was told not to enforce it, which
        only happens on the naive baseline and is exactly the number
        the comparison in the README reports.
        """
        trace.append({"step": name, "outcome": outcome, "detail": detail, **numbers})

    if run_judge is None:
        run_judge = random.random() < config.JUDGE_SAMPLE_RATE

    def finish(result):
        """Attach the timings, log it, trace it, and hand it back."""
        result.setdefault("question", question)
        result.setdefault("mode", mode)
        result.setdefault("eligible_count", None)
        result.setdefault("top_score", 0.0)
        # Which schemes the retrieval actually surfaced, even when the
        # pipeline refused before writing an answer. The eval measures
        # retrieval hit rate separately from answer correctness, and a
        # refusal still had a retrieval step worth scoring.
        result["retrieved_scheme_ids"] = sorted({chunk["scheme_id"] for chunk in retrieved})
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        result["trace"] = trace
        if log:
            query_log.record(result)
            tracing.record_answer(result, chunks=retrieved, profile=profile)
        return result

    # --- retrieve -------------------------------------------------
    if mode == "naive":
        # No filtering, no routing, no profile. This is the whole point
        # of the baseline: it only knows how to compare embeddings.
        step("route", "skipped",
             "The baseline does not read the question for intent. It embeds it "
             "and searches everything.")
        step("sql filter", "skipped",
             "The baseline has no filter. Searching the whole corpus and hoping "
             "the right page floats up is the gap this project exists to close.")
        chunks = retrieval.naive_retrieve(question, use_reranker=use_reranker)
        eligible_ids = None
        intent = "naive"
    else:
        intent, scoped_ids = retrieval.route(question, profile)
        step("route", "ok",
             f"Read this as {'an' if intent[0] in 'aeiou' else 'a'} "
             f"{intent.replace('_', ' ')} question.",
             intent=intent,
             named_scheme_id=scoped_ids[0] if scoped_ids else None)

        chunks, eligible_ids = retrieval.hybrid_retrieve(
            question,
            profile=profile,
            scheme_ids=scoped_ids,
            use_reranker=use_reranker,
        )

        # The question named a scheme and the student gave their
        # details, so the eligibility answer is a comparison, not a
        # reading task. Settle it in SQL here and hand the model the
        # verdict. Without this step the whole pipeline would find the
        # right page and then let the model decide whether 79.5 clears
        # a bar of 80, which is the exact failure the project is about.
        if profile and intent == "scheme_detail" and scoped_ids:
            verdict = eligibility.check_one(profile, scoped_ids[0])

        if scoped_ids:
            step("sql filter", "skipped",
                 "The question named one scheme, so the search was scoped "
                 "straight to it and the profile filter was not needed.",
                 kept=len(scoped_ids), total=scheme_total())
        elif eligible_ids is None:
            step("sql filter", "skipped",
                 "No profile was given, so there were no typed criteria to "
                 "filter on and the search ran over the whole corpus.")
        else:
            step("sql filter", "ok",
                 f"{len(eligible_ids)} of {scheme_total()} schemes passed the "
                 f"typed criteria. The vector search only ever saw these.",
                 kept=len(eligible_ids), total=scheme_total())

    retrieved = chunks
    eligible_count = len(eligible_ids) if eligible_ids is not None else None

    reranked = any("rerank_score" in chunk for chunk in chunks)
    step("vector search", "ok",
         f"Asked for {config.CANDIDATE_CHUNKS} candidate chunks, kept "
         f"{len(chunks)}.",
         candidates=config.CANDIDATE_CHUNKS,
         kept=len(chunks),
         top_similarity=round(top_score(chunks), 4))
    step("rerank", "ok" if reranked else "skipped",
         "The cross encoder read each chunk together with the question and "
         "reordered them."
         if reranked else
         "The cross encoder is switched off here, so the vector order stands. "
         "It needs PyTorch, which does not fit in the deployed instance.")

    # --- rule 1: the filter matched nothing -----------------------
    if (
        enforce_abstention
        and mode != "naive"
        and profile
        and intent == "eligibility"
        and eligible_count == 0
    ):
        near = eligibility.find_near_misses(profile)
        message = (
            "No scheme in this corpus matches your profile exactly, so I am not "
            "going to suggest one that does not fit."
        )
        if near:
            missed = "; ".join(f"{item['name']} ({item['missed_by']})" for item in near[:3])
            message += f" The closest ones are: {missed}"

        step("abstention", "stopped",
             "No scheme matched the profile, so there is nothing honest to "
             "recommend. Showing the near misses instead.",
             rule="sql filter returned nothing")
        return finish(
            _refuse(
                "sql filter returned nothing",
                message,
                eligible_count=0,
                near_misses=near,
            )
        )

    # --- rule 2: nothing came back at all -------------------------
    # This one is not optional even for the baseline. With no chunks
    # there is nothing to build an answer out of at all.
    if not chunks:
        step("abstention", "stopped",
             "The search came back empty, so there is nothing to build an "
             "answer out of.",
             rule="no chunks retrieved")
        return finish(
            _refuse(
                "no chunks retrieved",
                "I could not find anything in my sources about that.",
                eligible_count=eligible_count,
            )
        )

    best = top_score(chunks)

    # --- rule 3: the best match is too weak -----------------------
    if enforce_abstention and best < config.MIN_SIMILARITY:
        step("abstention", "stopped",
             f"The best chunk scored {round(best, 4)}, under the "
             f"{config.MIN_SIMILARITY} floor, so nothing retrieved is close "
             f"enough to the question to answer from.",
             rule="top retrieval score below threshold",
             top_similarity=round(best, 4),
             threshold=config.MIN_SIMILARITY)
        return finish(
            _refuse(
                "top retrieval score below threshold",
                "I do not have a source that answers that closely enough to be "
                "worth trusting, so I would rather not guess.",
                eligible_count=eligible_count,
                top_score=best,
            )
        )

    schemes_by_id = load_schemes({chunk["scheme_id"] for chunk in chunks})

    # --- rule 4: everything citable is unverified -----------------
    confidences = [
        float(scheme["extraction_confidence"]) for scheme in schemes_by_id.values()
    ]
    if enforce_abstention and confidences and max(confidences) < config.MIN_EXTRACTION_CONFIDENCE:
        links = ", ".join(
            f"{scheme['name']} ({scheme['source_url']})"
            for scheme in list(schemes_by_id.values())[:3]
        )
        step("abstention", "stopped",
             "Every scheme worth citing here has rules I could not verify "
             "against its own source page, so I will not state them.",
             rule="extraction confidence too low",
             best_confidence=round(max(confidences), 2))
        return finish(
            _refuse(
                "extraction confidence too low",
                "I could not confirm the rules for the schemes that match this "
                f"question against their source pages, so I will not state them. "
                f"Please check directly: {links}",
                eligible_count=eligible_count,
                top_score=best,
            )
        )

    step("abstention rules", "ok",
         "All four checks before generation passed: the filter found schemes, "
         "the search found chunks, the best one cleared the similarity floor, "
         "and at least one scheme has verified rules.")

    # --- generate -------------------------------------------------
    answer, answer_tokens = generation.generate_answer(
        question,
        chunks,
        schemes_by_id,
        profile=profile,
        schemes=list(schemes_by_id.values()),
        verdict=verdict,
    )
    tokens += answer_tokens
    step("generate", "ok",
         f"Wrote a draft from {len(chunks)} chunks. The draft is not shown to "
         f"anyone until the two checks below have run.",
         tokens=answer_tokens)

    # --- rule 5: layer 1, numbers and dates -----------------------
    # The student's own numbers count as sources. An answer that repeats
    # "your income of 240000" is quoting the question, not inventing.
    extra_texts = [question]
    if profile:
        extra_texts.append(" ".join(str(value) for value in profile.values() if value is not None))
    if verdict:
        # The verdict sentences carry both numbers, the cutoff and the
        # student's own. They came out of the database, so an answer
        # that repeats them is quoting a source, not inventing one.
        extra_texts.extend(verdict["reasons"])

    layer_one = grounding.check_layer_one(answer, chunks, extra_texts)

    _loose = layer_one["unsupported_numbers"] + layer_one["unsupported_dates"]
    step("grounding: numbers and dates",
         "ok" if layer_one["grounded"] else ("stopped" if enforce_abstention else "failed"),
         "Every figure in the draft traces back to a retrieved sentence, the "
         "question itself, or the database verdict."
         if layer_one["grounded"] else
         f"The draft contains {_loose} with no source behind it.",
         unsupported_numbers=layer_one["unsupported_numbers"],
         unsupported_dates=layer_one["unsupported_dates"])

    if not layer_one["grounded"] and enforce_abstention:
        problems = []
        if layer_one["unsupported_numbers"]:
            problems.append(f"numbers {layer_one['unsupported_numbers']}")
        if layer_one["unsupported_dates"]:
            problems.append(f"dates {layer_one['unsupported_dates']}")

        return finish(
            _refuse(
                f"layer 1 failed on {' and '.join(problems)}",
                "I drafted an answer but it contained a figure I could not trace "
                "back to a source, so I have blocked it rather than risk giving "
                "you a wrong threshold or deadline. Please check the scheme page "
                "directly.",
                eligible_count=eligible_count,
                top_score=best,
                grounded=False,
                tokens=tokens,
                citations=build_citations(chunks, schemes_by_id),
            )
        )

    # --- rule 6: layer 2, the judge -------------------------------
    if not run_judge:
        step("grounding: the judge", "skipped",
             f"The judge runs on {int(config.JUDGE_SAMPLE_RATE * 100)}% of live "
             f"answers, sampled, because it costs a second model call every "
             f"time. This question was not in the sample.")

    if run_judge:
        supported, unsupported_claims, judge_tokens = grounding.check_layer_two(answer, chunks)
        tokens += judge_tokens
        step("grounding: the judge",
             "ok" if supported else ("stopped" if enforce_abstention else "failed"),
             "A second model, a different one from the writer, read the draft "
             "against the sources and backed every claim."
             if supported else
             f"The judge could not back: {'; '.join(unsupported_claims)[:160]}",
             tokens=judge_tokens)

        if not supported and enforce_abstention:
            return finish(
                _refuse(
                    f"judge rejected: {'; '.join(unsupported_claims)[:200]}",
                    "I drafted an answer but could not confirm every claim in it "
                    "against my sources, so I am not going to give it to you. "
                    "Please check the scheme page directly.",
                    eligible_count=eligible_count,
                    top_score=best,
                    grounded=False,
                    tokens=tokens,
                    citations=build_citations(chunks, schemes_by_id),
                )
            )

    # --- answer ---------------------------------------------------
    return finish(
        {
            "answer": answer,
            "abstained": False,
            "abstain_reason": None,
            "citations": build_citations(chunks, schemes_by_id),
            "warnings": staleness_warnings(schemes_by_id),
            # For the baseline this can be False and the answer still
            # goes out. That is the whole point of the comparison: how
            # often does plain RAG hand over an ungrounded number.
            "grounded": layer_one["grounded"],
            "unsupported_numbers": layer_one["unsupported_numbers"],
            "unsupported_dates": layer_one["unsupported_dates"],
            "eligible_count": eligible_count,
            "top_score": best,
            "tokens": tokens,
            "intent": intent,
        }
    )
