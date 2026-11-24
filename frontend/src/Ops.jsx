import React, { useEffect, useState } from "react";

import api from "./api";
import getErrorMessage from "./errorMessage";
import PageHeader from "./PageHeader";
import Loading from "./Loading";

/*
  What the service has actually been doing.

  None of the numbers on this page come from new instrumentation. Every
  answer since the first day has written a row to query_log with its
  retrieval score, whether it refused and why, how long it took and how
  many tokens it cost. The data was always there. This page is the data
  finally being looked at.

  The offline evaluation and this page answer different questions, and
  it took me a while to see that. The evaluation says "on forty
  questions I wrote, here is how well it does". This says "on the
  questions real people are actually asking, is it still behaving".
  An abstention rate that climbs, a top score that drifts down, or an
  eligible count stuck at zero are all things the evaluation cannot
  see, because the evaluation only runs when I run it.

  The percentiles matter more than the mean. This runs on a free
  instance that sleeps after fifteen minutes, so one cold start drags
  the mean latency up by seconds and makes a healthy service look
  broken. That is the kind of false alarm that teaches people to stop
  trusting dashboards, so p50 is shown first and the mean last.
*/

function percent(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  return Math.round(value * 100) + "%";
}

function Ops() {
  const [summary, setSummary] = useState(null);
  const [days, setDays] = useState(14);
  const [error, setError] = useState("");
  const [load, setLoad] = useState(true);

  useEffect(() => {
    async function loadSummary() {
      try {
        setLoad(true);
        const response = await api.get("/ops/summary", { params: { days } });
        setSummary(response.data);
      } catch (err) {
        setError(getErrorMessage(err, "Could not load the service numbers."));
      } finally {
        setLoad(false);
      }
    }

    loadSummary();
  }, [days]);

  const spent = summary ? summary.today.tokens : 0;
  const budget = summary ? summary.today.budget : 1;
  const usedShare = Math.min((spent / budget) * 100, 100);

  const busiest = summary
    ? Math.max(...summary.by_day.map((day) => day.queries), 1)
    : 1;

  return (
    <div>
      <PageHeader
        icon="fa-gauge-high"
        title="How it is running"
        subtitle="Live numbers from the query log, not from the evaluation"
      >
        <select
          className="form-select"
          value={days}
          onChange={(event) => setDays(Number(event.target.value))}
        >
          <option value={7}>last 7 days</option>
          <option value={14}>last 14 days</option>
          <option value={30}>last 30 days</option>
        </select>
      </PageHeader>

      {error && <div className="alert alert-danger">{error}</div>}
      {load && <Loading what="the service numbers" />}

      {summary && summary.queries === 0 && (
        <div className="panel corners p-4">
          <p className="info-text mb-0">
            No questions have been asked in the last {summary.days} days, so
            there is nothing to show yet. Ask something on the questions page
            and it will appear here.
          </p>
        </div>
      )}

      {summary && summary.queries > 0 && (
        <>
          <div className="row g-3 mb-3">
            {[
              { label: "questions asked", value: summary.queries },
              { label: "refused", value: percent(summary.abstain_rate) },
              { label: "grounded", value: percent(summary.grounded_rate) },
              {
                label: "median answer time",
                value: summary.latency_ms.p50 + " ms",
              },
            ].map((card) => (
              <div className="col-6 col-lg-3" key={card.label}>
                <div className="panel corners p-3 h-100">
                  <div className="stat-value">{card.value}</div>
                  <div className="stat-label">{card.label}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="row g-3 mb-3">
            <div className="col-lg-6">
              <div className="panel corners p-4 h-100">
                <h2 className="section-title">Today against the budget</h2>
                <p className="info-text">
                  Questions are rate limited by tokens rather than by requests,
                  because the model quota is counted in tokens. Twenty long
                  questions can cost more than a hundred short ones, so a
                  request limit would be the wrong shape for the thing it is
                  protecting.
                </p>

                <div className="budget-track">
                  <div
                    className="budget-bar"
                    style={{ width: usedShare + "%" }}
                  ></div>
                </div>

                <p className="info-text mt-2 mb-0">
                  {spent.toLocaleString()} of {budget.toLocaleString()} tokens
                  used today, across {summary.today.queries} question
                  {summary.today.queries === 1 ? "" : "s"}. When this runs out,
                  questions stop but eligibility checking keeps working, because
                  that runs in SQL and never calls a model.
                </p>
              </div>
            </div>

            <div className="col-lg-6">
              <div className="panel corners p-4 h-100">
                <h2 className="section-title">Answer time</h2>
                <table className="table eval-table mb-3">
                  <tbody>
                    <tr>
                      <td>Median (p50)</td>
                      <td className="text-end">{summary.latency_ms.p50} ms</td>
                    </tr>
                    <tr>
                      <td>Slowest 5% (p95)</td>
                      <td className="text-end">{summary.latency_ms.p95} ms</td>
                    </tr>
                    <tr>
                      <td>Mean</td>
                      <td className="text-end">{summary.latency_ms.mean} ms</td>
                    </tr>
                  </tbody>
                </table>
                <p className="info-text mb-0">
                  A gap between the median and the mean is usually a cold start.
                  The free instance sleeps after fifteen minutes, and waking it
                  up costs about fifty seconds that has nothing to do with the
                  pipeline.
                </p>
              </div>
            </div>
          </div>

          <div className="row g-3">
            <div className="col-lg-7">
              <div className="panel corners p-4 h-100">
                <h2 className="section-title">Day by day</h2>
                <table className="table eval-table mb-0">
                  <thead>
                    <tr>
                      <th>Day</th>
                      <th>Questions</th>
                      <th className="text-center">Refused</th>
                      <th className="text-center">Top score</th>
                      <th className="text-center">Median</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.by_day.map((day) => (
                      <tr key={day.day}>
                        <td>{day.day}</td>
                        <td>
                          <span className="day-track">
                            <span
                              className="day-bar"
                              style={{
                                width: (day.queries / busiest) * 100 + "%",
                              }}
                            ></span>
                          </span>
                          <span className="day-count">{day.queries}</span>
                        </td>
                        <td className="text-center">
                          {percent(day.abstain_rate)}
                        </td>
                        <td className="text-center">{day.mean_top_score}</td>
                        <td className="text-center">
                          {day.p50_latency_ms} ms
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="col-lg-5">
              <div className="panel corners p-4 h-100">
                <h2 className="section-title">Why it refused</h2>
                <p className="info-text">
                  Six rules can stop an answer. Which one is firing tells you
                  something different each time: the filter matching nothing
                  means the profile is unusual, while the grounding check firing
                  often would mean the model is inventing figures.
                </p>

                {summary.abstain_reasons.length === 0 ? (
                  <p className="info-text mb-0">
                    Nothing was refused in this window.
                  </p>
                ) : (
                  <table className="table eval-table mb-0">
                    <tbody>
                      {summary.abstain_reasons.map((reason) => (
                        <tr key={reason.reason}>
                          <td>{reason.reason}</td>
                          <td className="text-end">{reason.times}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default Ops;
