"""
The whole offline pipeline, in one run.

    python -m scripts.run_ingestion

For every document in data/raw it:

  1. asks the model for the eligibility criteria and checks the quotes,
  2. splits the text into chunks and scans them for prompt injection,
  3. embeds the chunks,
  4. writes the scheme, its criteria and its chunks into Postgres,
  5. rebuilds the Chroma index from what it just wrote,
  6. writes data/review/extraction_review.md for the hand check.

Two things about how it starts.

It truncates and restarts the ids every time. Combined with reading the
documents in sorted filename order, that means scheme 17 is the same
scheme on every rebuild. The eval questions store scheme ids as ground
truth, so ids that moved between runs would quietly wreck the eval.

Chroma is rebuilt from Postgres at the end rather than written to
directly. Postgres is the source of truth for embeddings, and building
the index the same way the API builds it at boot means I am testing the
real path, not a second one that only ingestion uses.
"""

import json
import sys
import time

from app import config, db, embeddings, vector_store
from ingestion.chunker import chunk_document
from ingestion.extract_criteria import extract_for_document
from ingestion.injection_scan import scan_chunk
from ingestion.load_documents import load_all

# A small wait between model calls. Free tiers limit requests per
# minute, and llm.py will back off and retry anyway, but going in at a
# sensible pace means it rarely has to.
SECONDS_BETWEEN_CALLS = 2


def clear_tables():
    """
    Empty the scheme table and everything hanging off it.

    RESTART IDENTITY puts the id counter back to 1. CASCADE takes
    eligibility_criteria and document_chunk with it, so there is no
    chance of chunks left pointing at a scheme that no longer exists.
    """
    db.execute("TRUNCATE scheme RESTART IDENTITY CASCADE")
    vector_store.reset()
    print("Cleared old data.\n")


def insert_scheme(document, extraction):
    """Write one scheme row and give back its new id."""
    return db.insert_returning_id(
        """
        INSERT INTO scheme
            (name, provider, description, amount_text, deadline,
             source_url, source_file, last_updated)
        VALUES
            (%(name)s, %(provider)s, %(description)s, %(amount_text)s, %(deadline)s,
             %(source_url)s, %(source_file)s, %(last_updated)s)
        RETURNING id
        """,
        {
            "name": document["name"],
            "provider": document["provider"],
            "description": extraction["summary"],
            "amount_text": extraction["amount_text"],
            "deadline": extraction["values"].get("deadline"),
            "source_url": document["source_url"],
            "source_file": document["source_file"],
            # The day I fetched the page. Not perfect, the page itself
            # rarely says when it changed, but it is honest and it is
            # what the staleness warning is measured against.
            "last_updated": document["fetched_on"],
        },
    )


def insert_criteria(scheme_id, extraction):
    """Write the one criteria row for this scheme."""
    values = extraction["values"]

    db.execute(
        """
        INSERT INTO eligibility_criteria
            (scheme_id, min_cgpa, min_percentage, max_family_income,
             categories, genders, course_levels, states,
             min_age, max_age,
             field_sources, unknown_fields, extraction_confidence)
        VALUES
            (%(scheme_id)s, %(min_cgpa)s, %(min_percentage)s, %(max_family_income)s,
             %(categories)s, %(genders)s, %(course_levels)s, %(states)s,
             %(min_age)s, %(max_age)s,
             %(field_sources)s, %(unknown_fields)s, %(confidence)s)
        """,
        {
            "scheme_id": scheme_id,
            "min_cgpa": values.get("min_cgpa"),
            "min_percentage": values.get("min_percentage"),
            "max_family_income": values.get("max_family_income"),
            "categories": values.get("categories"),
            "genders": values.get("genders"),
            "course_levels": values.get("course_levels"),
            "states": values.get("states"),
            "min_age": values.get("min_age"),
            "max_age": values.get("max_age"),
            "field_sources": json.dumps(extraction["field_sources"]),
            "unknown_fields": extraction["unknown_fields"],
            "confidence": extraction["confidence"],
        },
    )


INSERT_CHUNK_SQL = """
INSERT INTO document_chunk
    (scheme_id, chunk_text, section, source_page,
     embedding, injection_flag, injection_reason)
VALUES
    (%(scheme_id)s, %(chunk_text)s, %(section)s, %(source_page)s,
     %(embedding)s, %(flagged)s, %(reason)s)
"""


def insert_chunks(scheme_id, chunks, vectors):
    """
    Write this scheme's chunks, with their embeddings and injection flags.

    All of them go in on one connection, because a scheme has six or
    seven chunks and opening a connection for each would be silly.
    Returns how many were flagged by the injection scan.
    """
    statements = []
    flagged_count = 0

    for chunk, vector in zip(chunks, vectors):
        flagged, reason = scan_chunk(chunk["chunk_text"])
        if flagged:
            flagged_count += 1

        statements.append(
            (
                INSERT_CHUNK_SQL,
                {
                    "scheme_id": scheme_id,
                    "chunk_text": chunk["chunk_text"],
                    "section": chunk["section"],
                    "source_page": chunk["source_page"],
                    "embedding": json.dumps(vector),
                    "flagged": flagged,
                    "reason": reason,
                },
            )
        )

    db.execute_many(statements)
    return flagged_count


def write_review_file(rows):
    """
    Write the file I read by hand.

    Section 5 of the guide says to check the first 30 myself, and I
    cannot do that against a database. Everything is here in reading
    order: what was extracted, the sentence it came from, and whether
    the automatic check passed, so I can spot a quote that is real but
    was read wrongly, which is the one thing verify.py cannot catch.
    """
    config.REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    path = config.REVIEW_DIR / "extraction_review.md"

    lines = [
        "# Extraction review",
        "",
        "One section per scheme, in id order. For each field the model filled in:",
        "the value, the sentence it quoted, and whether the automatic check passed.",
        "",
        "The automatic check proves the sentence is in the document and holds the",
        "number. It cannot prove the model read the right sentence. That is what I",
        "am looking for here.",
        "",
        "Tick the box once a scheme has been checked by hand.",
        "",
        "---",
        "",
    ]

    for row in rows:
        lines.append(f"## [ ] {row['id']}. {row['name']}")
        lines.append("")
        lines.append(f"Source: {row['source_url']}")
        lines.append(f"Confidence: {row['confidence']}")

        if row["unknown_fields"]:
            lines.append(f"Rejected fields: {', '.join(row['unknown_fields'])}")

        lines.append("")

        if not row["field_sources"]:
            lines.append("_No criteria were extracted for this scheme._")
            lines.append("")
        else:
            for field, record in row["field_sources"].items():
                mark = "PASS" if record["verified"] else "FAIL"
                lines.append(f"- **{field}** = `{record['value']}`  [{mark}]")
                lines.append(f"  - quote: \"{record['quote']}\"")
                if not record["verified"]:
                    lines.append(f"  - reason: {record['reason']}")
            lines.append("")

        lines.append("---")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReview file written to {path}")


def main():
    # Extractions already asked for are read back off the disk. Pass
    # --refresh after changing the extraction prompt, which costs a
    # model call per document again.
    refresh = "--refresh" in sys.argv

    documents = load_all()
    print(f"Found {len(documents)} documents in {config.RAW_DIR}")
    print("Re-asking the model for every extraction.\n" if refresh else "Using cached extractions where they exist.\n")

    clear_tables()

    review_rows = []
    total_chunks = 0
    total_flagged = 0
    total_tokens = 0
    confidences = []

    stopped_early = None

    for number, document in enumerate(documents, start=1):
        print(f"[{number}/{len(documents)}] {document['name']}")

        try:
            extraction = extract_for_document(document, refresh=refresh)
        except Exception as error:
            # Almost always the daily free tier quota. Stop here rather
            # than crash: every document already done is cached and
            # already in the database, so the system works with what it
            # has and tomorrow's run picks up exactly where this left
            # off. Half a corpus beats a traceback and an empty index.
            stopped_early = str(error)[:160]
            print(f"\n  Stopping early: {stopped_early}")
            print(f"  {number - 1} of {len(documents)} schemes are ingested.")
            break

        scheme_id = insert_scheme(document, extraction)
        insert_criteria(scheme_id, extraction)

        chunks = chunk_document(document)
        vectors = embeddings.embed_texts([chunk["chunk_text"] for chunk in chunks])
        flagged = insert_chunks(scheme_id, chunks, vectors)

        total_chunks += len(chunks)
        total_flagged += flagged
        total_tokens += extraction["tokens"]
        confidences.append(extraction["confidence"])

        note = f"    confidence {extraction['confidence']}, {len(chunks)} chunks"
        if extraction["unknown_fields"]:
            note += f", REJECTED {extraction['unknown_fields']}"
        if flagged:
            note += f", {flagged} chunks flagged for injection"
        print(note)

        review_rows.append(
            {
                "id": scheme_id,
                "name": document["name"],
                "source_url": document["source_url"],
                "confidence": extraction["confidence"],
                "unknown_fields": extraction["unknown_fields"],
                "field_sources": extraction["field_sources"],
            }
        )

        # Only wait when a request actually went out. A cached
        # extraction reports zero tokens and needs no pacing.
        if extraction["tokens"]:
            time.sleep(SECONDS_BETWEEN_CALLS)

    print("\nBuilding the Chroma index from Postgres ...")
    vector_store.load_from_postgres()

    write_review_file(review_rows)

    average = sum(confidences) / len(confidences) if confidences else 0
    perfect = sum(1 for value in confidences if value == 1.0)

    print("\n--- Ingestion finished ---")
    if stopped_early:
        print(f"STOPPED EARLY     {stopped_early}")
    print(f"schemes           {len(review_rows)} of {len(documents)}")
    print(f"chunks            {total_chunks}")
    print(f"injection flags   {total_flagged}")
    print(f"model tokens      {total_tokens}")
    print(f"mean confidence   {average:.2f}")
    print(f"fully verified    {perfect}/{len(confidences)} schemes")


if __name__ == "__main__":
    main()
