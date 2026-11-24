import React, { useEffect, useState } from "react";

import api from "./api";
import getErrorMessage from "./errorMessage";
import PageHeader from "./PageHeader";
import Loading from "./Loading";
import useDebounce from "./useDebounce";

/*
  What the system is actually reading.

  Chunking is the part of a RAG project that nobody shows. It runs once,
  offline, and after that every retrieval number depends on it while
  nobody can see what was done. So this page shows the chunks: how many,
  how long, which section of which scheme each came from, and the one
  measurement that says what chunking cost.

  That measurement is the split count, and it needs a sentence of
  explanation. The rule when building the corpus was one chunk per
  section, with the text splitter only getting involved when a section
  was longer than the maximum. So a section that produced one chunk is
  whole, and no rule inside it can have been cut in half. A section that
  produced two or more was split, and those are the only places where an
  income limit could sit in one chunk and the category list it applies
  to in another.

  On this corpus the splitter never ran once. That is worth showing and
  it is also worth not overselling, which is why the note on the page
  says it is a fact about these documents rather than a property of the
  design.
*/

const PAGE_SIZE = 10;

function Corpus() {
  const [stats, setStats] = useState(null);
  const [page, setPage] = useState({ total: 0, chunks: [] });

  const [section, setSection] = useState("");
  const [search, setSearch] = useState("");
  const [splitOnly, setSplitOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [openChunk, setOpenChunk] = useState(null);

  const [error, setError] = useState("");
  const [load, setLoad] = useState(true);

  // Wait a moment after the last keystroke, so typing a word does not
  // fire one request per letter.
  const typed = useDebounce(search, 350);

  useEffect(() => {
    async function loadStats() {
      try {
        const response = await api.get("/corpus/stats");
        setStats(response.data);
      } catch (err) {
        setError(getErrorMessage(err, "Could not load the corpus summary."));
      } finally {
        setLoad(false);
      }
    }

    loadStats();
  }, []);

  useEffect(() => {
    // Wait for the summary before asking for chunks.
    //
    // These used to go out together, which is faster when the server is
    // awake and worse when it is not. The API sleeps on its free tier,
    // so on the first visit both requests race a server that is still
    // starting, one of them loses, and the page shows a red network
    // error while the spinner is still turning. An error and a loading
    // state at the same time is the most confusing thing a page can
    // say.
    //
    // Letting the summary go first means one request wakes the server
    // and the rest are quick. It costs a few hundred milliseconds when
    // everything is warm, which nobody will notice, and removes a
    // failure that every first-time visitor would have seen.
    if (!stats) {
      return;
    }

    async function loadChunks() {
      try {
        const response = await api.get("/corpus/chunks", {
          params: {
            section: section,
            search: typed,
            split_only: splitOnly,
            limit: PAGE_SIZE,
            offset: offset,
          },
        });
        setPage(response.data);
      } catch (err) {
        setError(getErrorMessage(err, "Could not load the chunks."));
      }
    }

    loadChunks();
  }, [stats, section, typed, splitOnly, offset]);

  // Any change to a filter has to send the reader back to the first
  // page. Staying on page four of a list that now has one page shows
  // nothing and looks broken.
  function change(apply) {
    setOffset(0);
    apply();
  }

  const tallest = stats
    ? Math.max(...stats.histogram.map((bucket) => bucket.chunks), 1)
    : 1;

  return (
    <div>
      <PageHeader
        icon="fa-layer-group"
        title="What it reads"
        subtitle="Every chunk in the corpus, and what chunking did to the documents"
      />

      {error && !load && <div className="alert alert-danger">{error}</div>}
      {load && <Loading what="the corpus" />}

      {stats && (
        <>
          <div className="row g-3 mb-3">
            {[
              { label: "chunks", value: stats.chunks },
              { label: "schemes", value: stats.schemes },
              { label: "median length", value: stats.length.median + " chars" },
              { label: "longest chunk", value: stats.length.max + " chars" },
            ].map((card) => (
              <div className="col-6 col-lg-3" key={card.label}>
                <div className="panel corners p-3 h-100">
                  <div className="stat-value">{card.value}</div>
                  <div className="stat-label">{card.label}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="panel corners p-4 mb-3">
            <h2 className="section-title">How the documents were cut up</h2>
            <p className="info-text">
              The rule was one chunk per section. The splitter only runs on a
              section longer than {stats.settings.max_chars} characters, and
              when it does it overlaps the pieces by {stats.settings.overlap}{" "}
              characters so a sentence is not lost at the seam.
            </p>

            <div className="split-headline">
              <strong>
                {stats.sections.whole} of {stats.sections.total} sections stayed
                whole.
              </strong>{" "}
              {stats.sections.split === 0 ? (
                <span>
                  The splitter never ran. The longest section in the corpus is{" "}
                  {stats.length.max} characters, well under the limit, so no
                  rule in any scheme has been cut across two chunks.
                </span>
              ) : (
                <span>
                  {stats.sections.split} had to be split, including{" "}
                  {stats.sections.eligibility_split} eligibility section
                  {stats.sections.eligibility_split === 1 ? "" : "s"}. Those are
                  the only places where one rule could sit across two chunks.
                </span>
              )}
            </div>

            <p className="info-text mb-0">
              Worth being honest about: that is a fact about these forty four
              government scheme pages, which have short sections, not a property
              of the design. Longer documents would split, and the eligibility
              row below is the one I would watch if the corpus grew.
            </p>
          </div>

          <div className="row g-3 mb-3">
            <div className="col-lg-7">
              <div className="panel corners p-4 h-100">
                <h2 className="section-title">Sections</h2>
                <table className="table eval-table mb-0">
                  <thead>
                    <tr>
                      <th>Section</th>
                      <th className="text-center">Chunks</th>
                      <th className="text-center">Average</th>
                      <th className="text-center">Longest</th>
                      <th className="text-center">Split</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.by_section.map((row) => {
                      const split = stats.splits.find(
                        (item) => item.section === row.section
                      );
                      return (
                        <tr key={row.section}>
                          <td>{row.section}</td>
                          <td className="text-center">{row.chunks}</td>
                          <td className="text-center">{row.mean_chars}</td>
                          <td className="text-center">{row.max_chars}</td>
                          <td className="text-center">
                            {split && split.split > 0 ? (
                              <span className="badge-warn">{split.split}</span>
                            ) : (
                              "none"
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="col-lg-5">
              <div className="panel corners p-4 h-100">
                <h2 className="section-title">Chunk lengths</h2>
                <p className="info-text">
                  In buckets of 200 characters. The limit sits at{" "}
                  {stats.settings.max_chars}, off the right of this chart.
                </p>
                {stats.histogram.map((bucket) => (
                  <div className="hist-row" key={bucket.bucket}>
                    <span className="hist-label">
                      {bucket.bucket}-{bucket.bucket + 199}
                    </span>
                    <span className="hist-track">
                      <span
                        className="hist-bar"
                        style={{
                          width: (bucket.chunks / tallest) * 100 + "%",
                        }}
                      ></span>
                    </span>
                    <span className="hist-count">{bucket.chunks}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="panel corners p-4">
            <h2 className="section-title">Every chunk</h2>
            <p className="info-text">
              Exactly what the retriever sees, scheme name included. The name is
              glued to the top of each chunk on purpose: without it a chunk
              reads like "applicants must have an annual family income of less
              than two lakh" with no way of telling which scheme said so.
            </p>

            <div className="row g-2 mb-3">
              <div className="col-md-4">
                <select
                  className="form-select"
                  value={section}
                  onChange={(event) =>
                    change(() => setSection(event.target.value))
                  }
                >
                  <option value="">Every section</option>
                  {stats.by_section.map((row) => (
                    <option value={row.section} key={row.section}>
                      {row.section} ({row.chunks})
                    </option>
                  ))}
                </select>
              </div>

              <div className="col-md-5">
                <input
                  className="form-control"
                  placeholder="Search inside the chunk text"
                  value={search}
                  onChange={(event) =>
                    change(() => setSearch(event.target.value))
                  }
                />
              </div>

              <div className="col-md-3 d-flex align-items-center">
                <div className="form-check mb-0">
                  <input
                    className="form-check-input"
                    type="checkbox"
                    id="splitOnly"
                    checked={splitOnly}
                    disabled={stats.sections.split === 0}
                    onChange={(event) =>
                      change(() => setSplitOnly(event.target.checked))
                    }
                  />
                  <label className="form-check-label" htmlFor="splitOnly">
                    Split sections only
                    {stats.sections.split === 0 && (
                      <span className="info-text"> (none to show)</span>
                    )}
                  </label>
                </div>
              </div>
            </div>

            <p className="info-text">
              {page.total} chunk{page.total === 1 ? "" : "s"} match.
            </p>

            {page.chunks.map((chunk) => (
              <div className="chunk-card" key={chunk.id}>
                <button
                  type="button"
                  className="chunk-head"
                  onClick={() =>
                    setOpenChunk(openChunk === chunk.id ? null : chunk.id)
                  }
                >
                  <span className="chunk-id">#{chunk.id}</span>
                  <span className="chunk-scheme">{chunk.scheme_name}</span>
                  <span className="chunk-section">{chunk.section}</span>
                  <span className="chunk-chars">{chunk.chars} chars</span>
                  {chunk.pieces_in_section > 1 && (
                    <span className="badge-warn">
                      one of {chunk.pieces_in_section} pieces
                    </span>
                  )}
                </button>

                {openChunk === chunk.id && (
                  <pre className="chunk-text">{chunk.chunk_text}</pre>
                )}
              </div>
            ))}

            <div className="d-flex justify-content-between align-items-center mt-3">
              <button
                className="btn btn-outline-secondary"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </button>
              <span className="info-text">
                {page.total === 0
                  ? "nothing to show"
                  : offset +
                    1 +
                    " to " +
                    Math.min(offset + PAGE_SIZE, page.total) +
                    " of " +
                    page.total}
              </span>
              <button
                className="btn btn-outline-secondary"
                disabled={offset + PAGE_SIZE >= page.total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default Corpus;
