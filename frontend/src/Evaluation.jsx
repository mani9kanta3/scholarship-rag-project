import React, { useEffect, useState } from "react";

import api from "./api";
import getErrorMessage from "./errorMessage";
import PageHeader from "./PageHeader";

/*
  The page that shows how well this thing actually works.

  Putting your own marks in the product is not normal, and that is why
  it is here. The numbers come straight from the last evaluation run,
  including the ones where the system does badly, and the naive baseline
  sits in the next column so the difference is visible rather than
  claimed.

  The abstention numbers are the ones to read carefully. A system that
  refuses everything would score perfectly on safety and be useless, so
  both directions are shown: how often it refused when it should, and
  how often it refused when it should not have.
*/

const ROWS = [
  {
    key: "overall_correctness",
    label: "Overall correctness",
    help: "All 40 questions, graded against the expected answer.",
  },
  {
    key: "threshold_correctness",
    label: "Threshold questions",
    help: "Profiles sitting just above and just below a cutoff. This is the row the project is about.",
    highlight: true,
  },
  {
    key: "retrieval_hit_rate",
    label: "Retrieval hit rate",
    help: "Was the correct scheme anywhere in the retrieved set.",
  },
  {
    key: "groundedness",
    label: "Groundedness",
    help: "Share of answers where every number traced back to a source.",
  },
  {
    key: "hallucinated_numbers",
    label: "Answers with an invented figure",
    help: "Lower is better. A number in the answer that appears in no source.",
    lowerIsBetter: true,
  },
  {
    key: "abstention_recall",
    label: "Refused when it should",
    help: "Of the questions with no answer in the corpus, how many were refused.",
  },
  {
    key: "abstention_precision",
    label: "Refusals that were right",
    help: "Of everything it refused, how much genuinely had no answer. Low here means it is refusing too much.",
  },
];

function show(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  return typeof value === "number" ? value.toFixed(2) : value;
}

function Evaluation() {
  const [runs, setRuns] = useState([]);
  const [message, setMessage] = useState("");
  const [load, setLoad] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadRuns() {
      try {
        setLoad(true);
        const response = await api.get("/eval/latest");
        setRuns(response.data.runs || []);
        setMessage(response.data.message || "");
      } catch (err) {
        setError(getErrorMessage(err, "Could not load the evaluation results."));
      } finally {
        setLoad(false);
      }
    }

    loadRuns();
  }, []);

  // The newest run of each configuration. The eval writes one row per
  // configuration per run, so this picks the latest of each.
  const naive = runs.find((run) => run.config && run.config.mode === "naive");
  const hybrid = runs.find((run) => run.config && run.config.mode === "hybrid");

  return (
    <div>
      <PageHeader
        icon="fa-chart-simple"
        title="How well it works"
        subtitle="The numbers from the most recent evaluation, good and bad"
      />

      {error && <div className="alert alert-danger">{error}</div>}
      {load && <p className="info-text">Loading ...</p>}

      {!load && !hybrid && (
        <div className="panel corners p-4">
          <p className="info-text mb-0">
            {message || "No evaluation has been run yet."} Run{" "}
            <code>python -m eval.run_eval</code> in the backend folder to fill
            this page in.
          </p>
        </div>
      )}

      {hybrid && (
        <>
          <div className="panel corners p-4 mb-3">
            <table className="table eval-table mb-0">
              <thead>
                <tr>
                  <th>Measure</th>
                  <th className="text-center">Naive semantic RAG</th>
                  <th className="text-center">Hybrid + abstention</th>
                </tr>
              </thead>
              <tbody>
                {ROWS.map((row) => (
                  <tr key={row.key} className={row.highlight ? "highlight-row" : ""}>
                    <td>
                      <strong>{row.label}</strong>
                      <div className="info-text">{row.help}</div>
                    </td>
                    <td className="text-center number-cell">
                      {show(naive && naive.metrics[row.key])}
                    </td>
                    <td className="text-center number-cell">
                      {show(hybrid.metrics[row.key])}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="row g-3">
            <div className="col-md-6">
              <div className="panel corners p-4 h-100">
                <h5 className="mb-3">What was run</h5>
                <p className="info-text mb-1">
                  Questions: <strong>{hybrid.config.questions}</strong>
                </p>
                <p className="info-text mb-1">
                  Model: <code>{hybrid.config.model}</code>
                </p>
                <p className="info-text mb-1">
                  Reranker: {hybrid.config.use_reranker ? "on" : "off"}
                </p>
                <p className="info-text mb-0">Run at {hybrid.run_at}</p>
              </div>
            </div>

            <div className="col-md-6">
              <div className="panel corners p-4 h-100">
                <h5 className="mb-3">Reading these honestly</h5>
                <p className="info-text mb-0">
                  Correctness is graded by a language model, so it carries some
                  error of its own. The judge was checked against 20 answers
                  graded by hand, and that agreement rate is reported with the
                  run. A grader nobody checks is not a measurement.
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default Evaluation;
