import React, { useState } from "react";

import api from "./api";
import getErrorMessage from "./errorMessage";
import PageHeader from "./PageHeader";
import ProfileForm from "./ProfileForm";

const EMPTY_PROFILE = {
  percentage: null,
  cgpa: null,
  income: null,
  category: null,
  gender: null,
  course_level: null,
  state: null,
  age: null,
};

const EXAMPLES = [
  "What documents do I need for the AICTE Pragati Scholarship?",
  "How do I apply for the Post Matric Scholarship for SC students?",
  "What is the income limit for the Central Sector Scheme?",
  "Which scholarships can I get with 72 percent marks?",
];

/*
  The ask page.

  The part worth looking at is what happens when the system refuses. A
  refusal comes back as a normal answer with abstained set to true, and
  it is shown in a box of its own rather than hidden or turned into an
  error. If the system says it cannot confirm a deadline, that is the
  most useful sentence on the page and burying it would waste the whole
  grounding check behind it.

  The mode switch at the bottom is unusual for a product. It runs the
  same question through the naive baseline, the version with no SQL
  filter and no refusals, so the difference the project is about can be
  seen rather than just described.
*/
function Ask() {
  const [question, setQuestion] = useState("");
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [showProfile, setShowProfile] = useState(false);
  const [mode, setMode] = useState("hybrid");

  const [answer, setAnswer] = useState(null);
  const [load, setLoad] = useState(false);
  const [error, setError] = useState("");

  const hasProfile = Object.values(profile).some((value) => value !== null && value !== "");

  async function ask(event) {
    event.preventDefault();

    if (question.trim().length < 3) {
      setError("Please write a question first.");
      return;
    }

    try {
      setLoad(true);
      setError("");
      setAnswer(null);

      const response = await api.post("/ask", {
        question: question.trim(),
        // Only send the profile if the student actually filled some of
        // it in. An all null profile would still switch the backend
        // into eligibility mode and narrow the search for no reason.
        profile: hasProfile ? profile : null,
        mode: mode,
      });

      setAnswer({
        ...response.data,
        // The lists are read straight into .map further down, so make
        // sure they are lists whatever the server sent.
        citations: response.data.citations || [],
        warnings: response.data.warnings || [],
        near_misses: response.data.near_misses || [],
      });
    } catch (err) {
      setError(getErrorMessage(err, "Could not answer that question."));
    } finally {
      setLoad(false);
    }
  }

  return (
    <div>
      <PageHeader
        icon="fa-comments"
        title="Ask a question"
        subtitle="Answers come only from the scheme pages held here, with a link to each one."
      />

      <form onSubmit={ask} className="panel corners p-4 mb-4">
        <label className="field-label form-label">Your question</label>
        <textarea
          className="form-control mb-2"
          rows="3"
          maxLength="500"
          placeholder="Ask about a scheme, its documents, or how to apply"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={load}
        />

        <div className="examples mb-3">
          {EXAMPLES.map((example) => (
            <button
              type="button"
              key={example}
              className="example-chip"
              onClick={() => setQuestion(example)}
              disabled={load}
            >
              {example}
            </button>
          ))}
        </div>

        <button
          type="button"
          className="btn btn-link p-0 mb-2 toggle-profile"
          onClick={() => setShowProfile(!showProfile)}
        >
          <i
            className={`fa-solid ${showProfile ? "fa-chevron-down" : "fa-chevron-right"} me-2`}
          ></i>
          Add your details, so only schemes you qualify for are searched
        </button>

        {showProfile && (
          <div className="mt-3 mb-2">
            <ProfileForm profile={profile} onChange={setProfile} disabled={load} />
          </div>
        )}

        <div className="d-flex flex-wrap align-items-center gap-3 mt-3">
          <button type="submit" className="btn btn-brand" disabled={load}>
            {load ? "Thinking ..." : "Ask"}
          </button>

          <div className="mode-switch">
            <span className="field-label me-2">Retrieval:</span>
            <div className="btn-group btn-group-sm">
              <button
                type="button"
                className={mode === "hybrid" ? "btn btn-brand" : "btn btn-outline-brand"}
                onClick={() => setMode("hybrid")}
                disabled={load}
              >
                Hybrid
              </button>
              <button
                type="button"
                className={mode === "naive" ? "btn btn-brand" : "btn btn-outline-brand"}
                onClick={() => setMode("naive")}
                disabled={load}
              >
                Naive baseline
              </button>
            </div>
          </div>
        </div>

        {mode === "naive" && (
          <div className="baseline-warning mt-3">
            <i className="fa-solid fa-flask me-2"></i>
            This is the deliberately weaker version kept for comparison. It
            searches every scheme by meaning alone, with no filtering on your
            numbers. It is here to show the difference, not to be trusted.
          </div>
        )}
      </form>

      {error && <div className="alert alert-danger">{error}</div>}

      {answer && (
        <div className={answer.abstained ? "answer-box refused corners p-4" : "answer-box corners p-4"}>
          {answer.abstained ? (
            <>
              <h5 className="mb-3">
                <i className="fa-solid fa-hand me-2"></i>
                This one is being refused
              </h5>
              <p className="answer-text mb-3">{answer.answer}</p>
              {answer.abstain_reason && (
                <p className="refuse-reason mb-0">
                  Reason recorded: <code>{answer.abstain_reason}</code>
                </p>
              )}
            </>
          ) : (
            <>
              <h5 className="mb-3">
                <i className="fa-solid fa-lightbulb me-2"></i>
                Answer
              </h5>
              <p className="answer-text">{answer.answer}</p>
            </>
          )}

          {answer.near_misses && answer.near_misses.length > 0 && (
            <div className="mt-3">
              <p className="reasons-title mb-2">Closest schemes to your profile</p>
              <ul className="mb-0">
                {answer.near_misses.map((scheme) => (
                  <li key={scheme.id}>
                    {scheme.name} - {scheme.missed_by}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {answer.warnings && answer.warnings.length > 0 && (
            <div className="stale-warning mt-3">
              {answer.warnings.map((warning) => (
                <div key={warning}>
                  <i className="fa-solid fa-clock-rotate-left me-2"></i>
                  {warning}
                </div>
              ))}
            </div>
          )}

          {answer.citations.length > 0 && (
            <div className="citations mt-4">
              <p className="reasons-title mb-2">Sources used</p>
              {answer.citations.map((citation) => (
                <div className="citation" key={citation.number}>
                  <span className="citation-number">[{citation.number}]</span>
                  <a href={citation.source_url} target="_blank" rel="noreferrer">
                    {citation.scheme_name}
                  </a>
                  <span className="citation-section"> - {citation.section}</span>
                </div>
              ))}
            </div>
          )}

          <div className="answer-meta mt-4">
            <span>mode: {mode}</span>
            {answer.eligible_count !== null && (
              <span>schemes searched: {answer.eligible_count}</span>
            )}
            <span>top match: {answer.top_score}</span>
            <span>grounded: {String(answer.grounded)}</span>
            <span>{answer.latency_ms} ms</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default Ask;
