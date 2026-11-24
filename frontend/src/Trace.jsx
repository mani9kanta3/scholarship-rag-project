import React, { useState } from "react";

/*
  The pipeline, shown stage by stage.

  A student sees one answer. What actually happened was a routing
  decision, a SQL filter, a scoped vector search, a reranker, four
  abstention rules and two grounding checks, and any one of them can be
  the reason the answer reads the way it does. The backend records a
  line for each stage as it runs, and this component puts them on the
  screen.

  It is collapsed by default, because a student asking about their marks
  does not want a pipeline diagram. It is open to anyone who clicks,
  because the whole argument of this project lives in these steps, and
  "the SQL filter cut 44 schemes down to 9 before the search ran" is
  worth more than any paragraph I could write about it.

  The refusals are the ones really worth reading. When the system
  declines to answer, this says exactly which rule stopped it and what
  the numbers were.
*/

// How each outcome looks. stopped is the one that ended the pipeline,
// failed is a check that did not pass but was not enforced, which only
// happens on the naive baseline.
const LOOK = {
  ok: { icon: "fa-check", className: "trace-ok", label: "passed" },
  skipped: { icon: "fa-minus", className: "trace-skipped", label: "not needed" },
  stopped: { icon: "fa-hand", className: "trace-stopped", label: "stopped here" },
  failed: { icon: "fa-xmark", className: "trace-failed", label: "did not pass" },
};

/*
  The numbers each stage happens to carry. Every stage reports different
  ones, so rather than a fixed table this picks out whichever are
  present and gives them a readable label.
*/
const NUMBERS = [
  { key: "kept", label: "schemes kept" },
  { key: "total", label: "schemes in corpus" },
  { key: "candidates", label: "candidates asked for" },
  { key: "top_similarity", label: "best score" },
  { key: "threshold", label: "floor" },
  { key: "tokens", label: "tokens" },
  { key: "best_confidence", label: "best confidence" },
  { key: "intent", label: "intent" },
];

function chips(step) {
  const found = [];

  NUMBERS.forEach((item) => {
    const value = step[item.key];
    if (value !== undefined && value !== null) {
      found.push({ label: item.label, value });
    }
  });

  // These two are lists, so they only earn a chip when they have
  // something in them. An empty list means the check found nothing
  // wrong, which the sentence already says.
  ["unsupported_numbers", "unsupported_dates"].forEach((key) => {
    if (Array.isArray(step[key]) && step[key].length > 0) {
      found.push({
        label: key === "unsupported_numbers" ? "figures with no source" : "dates with no source",
        value: step[key].join(", "),
      });
    }
  });

  return found;
}

function Trace({ trace }) {
  const [open, setOpen] = useState(false);

  if (!trace || trace.length === 0) {
    return null;
  }

  const stopped = trace.find((step) => step.outcome === "stopped");

  return (
    <div className="panel corners mt-3">
      <button
        type="button"
        className="trace-toggle w-100 text-start p-3"
        onClick={() => setOpen(!open)}
      >
        <i className={`fa-solid ${open ? "fa-chevron-down" : "fa-chevron-right"} me-2`}></i>
        <strong>Show how this answer was reached</strong>
        <span className="info-text ms-2">
          {trace.length} stages
          {stopped ? ", stopped at " + stopped.step : ""}
        </span>
      </button>

      {open && (
        <div className="px-3 pb-3">
          <p className="info-text">
            Every stage below ran in order. Nothing here is written after the
            fact: each line is recorded by the stage itself as it happens.
          </p>

          <ol className="trace-list">
            {trace.map((step, index) => {
              const look = LOOK[step.outcome] || LOOK.ok;

              return (
                <li key={index} className={`trace-step ${look.className}`}>
                  <span className="trace-mark">
                    <i className={`fa-solid ${look.icon}`}></i>
                  </span>

                  <div className="trace-body">
                    <div className="trace-head">
                      <span className="trace-name">{step.step}</span>
                      <span className="trace-outcome">{look.label}</span>
                    </div>

                    <p className="trace-detail mb-1">{step.detail}</p>

                    {chips(step).length > 0 && (
                      <div className="trace-chips">
                        {chips(step).map((chip) => (
                          <span className="trace-chip" key={chip.label}>
                            {chip.label}: <strong>{String(chip.value)}</strong>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </div>
  );
}

export default Trace;
