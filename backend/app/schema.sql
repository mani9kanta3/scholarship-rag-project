-- Every table in the project.
--
-- Postgres holds the criteria, the chunks AND the embeddings. Chroma is
-- built from this file's data at boot, so if the Chroma folder is
-- deleted nothing is lost. That is the reason the embedding lives here
-- and not only in the vector store.
--
-- Running this file twice is safe. It drops nothing.


-- One scholarship or government scheme.
CREATE TABLE IF NOT EXISTS scheme (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    provider      TEXT NOT NULL,          -- ministry, state government or university
    description   TEXT NOT NULL,
    amount_text   TEXT,                   -- free text on purpose, amounts are messy
    deadline      DATE,                   -- NULL means the scheme has no fixed date
    source_url    TEXT NOT NULL,          -- every answer cites this
    source_file   TEXT NOT NULL,          -- the local copy in data/raw
    last_updated  DATE NOT NULL,          -- when the source page said it was updated
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);


-- The rules, pulled out of the document into real columns.
-- This is the table that does the actual eligibility work.
--
-- NULL in any of these columns means "this scheme sets no limit here",
-- NOT "we do not know". A field we could not read is a different thing
-- and it is recorded in field_sources instead, so the answering layer
-- can refuse to state it as fact.
CREATE TABLE IF NOT EXISTS eligibility_criteria (
    id                     SERIAL PRIMARY KEY,
    scheme_id              INTEGER NOT NULL UNIQUE REFERENCES scheme(id) ON DELETE CASCADE,
    min_cgpa               NUMERIC(4, 2),
    min_percentage         NUMERIC(5, 2),   -- both exist in the wild, keep both
    max_family_income      NUMERIC(12, 2),  -- annual, in rupees
    categories             TEXT[],          -- SC, ST, OBC, EWS, GEN, MINORITY
    genders                TEXT[],          -- MALE, FEMALE, OTHER
    course_levels          TEXT[],          -- UG, PG, PHD, DIPLOMA
    states                 TEXT[],          -- NULL means all India
    min_age                INTEGER,
    max_age                INTEGER,

    -- For every field above, the sentence the model quoted from the
    -- document, and whether that sentence really contains the value.
    -- Looks like {"min_cgpa": {"value": 7.5, "quote": "...", "verified": true}}
    field_sources          JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Fields the model filled in but that failed the quote check.
    -- These are the third state. The column above stays NULL so the
    -- filter still offers the scheme as a candidate, but a field named
    -- here must never be asserted as fact in an answer.
    unknown_fields         TEXT[] NOT NULL DEFAULT '{}',

    -- How many of the extracted fields passed that check, 0.00 to 1.00.
    -- A measured number, not the model's own opinion of itself.
    extraction_confidence  NUMERIC(3, 2) NOT NULL DEFAULT 0,

    -- True once a human has read the extraction against the document.
    hand_checked           BOOLEAN NOT NULL DEFAULT FALSE
);


-- The descriptive text, split into pieces and embedded.
CREATE TABLE IF NOT EXISTS document_chunk (
    id                SERIAL PRIMARY KEY,
    scheme_id         INTEGER NOT NULL REFERENCES scheme(id) ON DELETE CASCADE,
    chunk_text        TEXT NOT NULL,
    section           TEXT NOT NULL,     -- eligibility / benefits / documents / how to apply / other
    source_page       INTEGER,           -- for the citation

    -- The raw floats from the embedding model. JSONB because it is easy
    -- to read back and this corpus is small. Chroma is rebuilt from it.
    embedding         JSONB NOT NULL,

    -- Section 7 of the guide. The corpus is public PDFs I did not write,
    -- so a chunk could contain "ignore previous instructions". Scanned
    -- once at ingestion and eyeballed, rather than checked every query.
    injection_flag    BOOLEAN NOT NULL DEFAULT FALSE,
    injection_reason  TEXT
);

CREATE INDEX IF NOT EXISTS document_chunk_scheme_idx ON document_chunk(scheme_id);


-- The 40 hand written eval questions.
CREATE TABLE IF NOT EXISTS eval_question (
    id                  SERIAL PRIMARY KEY,
    question            TEXT NOT NULL,
    profile             JSONB,             -- the student profile, for eligibility questions
    expected_scheme_ids INTEGER[],         -- ground truth
    expected_answer     TEXT,              -- what a correct answer should say
    expected_abstain    BOOLEAN NOT NULL DEFAULT FALSE,
    question_type       TEXT NOT NULL,     -- eligibility / threshold / detail / trap
    why_it_exists       TEXT NOT NULL      -- I have to be able to defend every question
);


-- One row per eval run, so naive and hybrid can be compared over time.
CREATE TABLE IF NOT EXISTS eval_run (
    id       SERIAL PRIMARY KEY,
    run_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    config   JSONB NOT NULL,   -- which mode, which model, reranker on or off
    metrics  JSONB NOT NULL
);


-- Every live question the API answers.
--
-- Nothing reads this yet. It is here from day one because it only
-- becomes useful once it has history, and starting it a month after
-- launch means starting from zero.
CREATE TABLE IF NOT EXISTS query_log (
    id                  SERIAL PRIMARY KEY,
    asked_at            TIMESTAMP NOT NULL DEFAULT NOW(),
    question            TEXT NOT NULL,
    mode                TEXT NOT NULL,     -- naive or hybrid
    eligible_count      INTEGER,           -- zero every time means the SQL filter broke
    top_retrieval_score NUMERIC(6, 4),     -- drifting down means retrieval is degrading
    abstained           BOOLEAN NOT NULL DEFAULT FALSE,
    abstain_reason      TEXT,
    grounded            BOOLEAN,           -- did the layer 1 number check pass
    latency_ms          INTEGER,
    tokens              INTEGER
);

CREATE INDEX IF NOT EXISTS query_log_asked_at_idx ON query_log(asked_at);
