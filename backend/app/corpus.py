"""
The corpus, described to anyone who wants to look at it.

Chunking is the part of a RAG system that nobody shows. It happens once,
offline, and then every retrieval number in the project depends on it
and nobody can see what was done. This module exists so the chunks are
inspectable: how many there are, how long they are, which section of
which scheme each came from, and what the chunking cost.

**The measurement worth reading is the split count.**

The strategy is one chunk per section. A section only goes through the
splitter when it is longer than config.CHUNK_MAX_CHARS. So a section
that produced one chunk is whole, and a rule inside it cannot have been
cut in half. A section that produced two or more was split, and those
are the only places in the corpus where an income limit could end up in
one chunk and the category list it applies to in another.

That makes "how many sections had to be split" an honest measure of what
chunking cost, and it is a GROUP BY rather than a guess. The eligibility
sections are called out separately, because they are the ones the whole
project turns on.
"""

from . import config, db

# Both halves of the chunk query filter on the same three things. Kept
# in one place so the page of rows and the count of rows can never
# quietly disagree about what is being counted.
FILTERS = """
    (%(section)s = '' OR c.section = %(section)s)
    AND (%(scheme_id)s::int IS NULL OR c.scheme_id = %(scheme_id)s::int)
    AND (%(search)s = '' OR c.chunk_text ILIKE %(like)s)
"""


def stats():
    """Everything the corpus page needs, in one call."""
    totals = db.fetch_one(
        """
        SELECT COUNT(*)                                   AS chunks,
               COUNT(DISTINCT scheme_id)                  AS schemes,
               MIN(LENGTH(chunk_text))                    AS min_chars,
               MAX(LENGTH(chunk_text))                    AS max_chars,
               ROUND(AVG(LENGTH(chunk_text)))             AS mean_chars,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY LENGTH(chunk_text))
                                                          AS median_chars
        FROM document_chunk
        """
    )

    by_section = db.fetch_all(
        """
        SELECT section,
               COUNT(*)                        AS chunks,
               COUNT(DISTINCT scheme_id)       AS schemes,
               ROUND(AVG(LENGTH(chunk_text)))  AS mean_chars,
               MAX(LENGTH(chunk_text))         AS max_chars
        FROM document_chunk
        GROUP BY section
        ORDER BY COUNT(*) DESC
        """
    )

    # The cost of chunking. A section that became more than one chunk
    # was too long to keep whole, so it is a place a rule could be cut.
    splits = db.fetch_all(
        """
        SELECT section,
               COUNT(*)                            AS sections,
               COUNT(*) FILTER (WHERE pieces > 1)  AS split,
               MAX(pieces)                         AS most_pieces
        FROM (
            SELECT scheme_id, section, COUNT(*) AS pieces
            FROM document_chunk
            GROUP BY scheme_id, section
        ) AS per_section
        GROUP BY section
        ORDER BY COUNT(*) FILTER (WHERE pieces > 1) DESC, section
        """
    )

    histogram = db.fetch_all(
        """
        SELECT (LENGTH(chunk_text) / 200) * 200 AS bucket,
               COUNT(*)                         AS chunks
        FROM document_chunk
        GROUP BY 1
        ORDER BY 1
        """
    )

    per_scheme = db.fetch_all(
        """
        SELECT s.id, s.name, COUNT(*) AS chunks
        FROM document_chunk c
        JOIN scheme s ON s.id = c.scheme_id
        GROUP BY s.id, s.name
        ORDER BY COUNT(*) DESC, s.name
        """
    )

    sections = sum(row["sections"] for row in splits)
    split = sum(row["split"] for row in splits)

    eligibility = next((row for row in splits if row["section"] == "eligibility"), None)

    return {
        "chunks": totals["chunks"],
        "schemes": totals["schemes"],
        "length": {
            "min": totals["min_chars"],
            "median": int(totals["median_chars"] or 0),
            "mean": int(totals["mean_chars"] or 0),
            "max": totals["max_chars"],
        },
        "settings": {
            "max_chars": config.CHUNK_MAX_CHARS,
            "overlap": config.CHUNK_OVERLAP,
            "strategy": "One chunk per section. The splitter only runs on a section longer than the maximum.",
        },
        "sections": {
            "total": sections,
            "whole": sections - split,
            "split": split,
            # The number that matters most. Eligibility is the section
            # the SQL filter and every threshold question depend on.
            "eligibility_split": eligibility["split"] if eligibility else 0,
            "eligibility_total": eligibility["sections"] if eligibility else 0,
        },
        "by_section": [dict(row) for row in by_section],
        "splits": [dict(row) for row in splits],
        "histogram": [dict(row) for row in histogram],
        "per_scheme": [dict(row) for row in per_scheme],
    }


def chunks(section="", scheme_id=None, search="", split_only=False, limit=25, offset=0):
    """
    The chunks themselves, filtered and paged.

    pieces_in_section comes back on every row, so the page can mark the
    split ones without a second query. A window function is the cheap
    way to carry a group level fact on each row, and filtering on it
    needs the subquery, because a window function cannot go in a WHERE.
    """
    split_clause = "WHERE counted.pieces_in_section > 1" if split_only else ""
    params = {
        "section": section,
        "scheme_id": scheme_id,
        "search": search,
        "like": f"%{search}%",
        "limit": limit,
        "offset": offset,
    }

    rows = db.fetch_all(
        f"""
        SELECT counted.*, s.name AS scheme_name
        FROM (
            SELECT c.id, c.scheme_id, c.section, c.source_page,
                   c.chunk_text, LENGTH(c.chunk_text) AS chars,
                   COUNT(*) OVER (PARTITION BY c.scheme_id, c.section)
                       AS pieces_in_section
            FROM document_chunk c
            WHERE {FILTERS}
        ) AS counted
        JOIN scheme s ON s.id = counted.scheme_id
        {split_clause}
        ORDER BY s.name, counted.id
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
    )

    total = db.fetch_one(
        f"""
        SELECT COUNT(*) AS total
        FROM (
            SELECT COUNT(*) OVER (PARTITION BY c.scheme_id, c.section)
                       AS pieces_in_section
            FROM document_chunk c
            WHERE {FILTERS}
        ) AS counted
        {split_clause}
        """,
        params,
    )

    return {"total": total["total"], "chunks": [dict(row) for row in rows]}
