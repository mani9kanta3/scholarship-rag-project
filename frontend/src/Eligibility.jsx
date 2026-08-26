import React, { useState } from "react";
import { Link } from "react-router-dom";

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

/*
  The eligibility page.

  This is the one page with no language model behind it at all. The
  profile goes to the backend, the backend runs one SQL query, and the
  list that comes back is exact. That is the point of the whole project,
  so the page says why each scheme matched rather than just listing
  names.

  Three things are shown that most tools leave out:

  - why a scheme matched, in the student's own numbers,
  - rules that could not be checked because the form was left blank,
  - the near misses, so "you were 0.2 CGPA short" is visible instead of
    the scheme just quietly vanishing.
*/
function Eligibility() {
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [result, setResult] = useState(null);
  const [load, setLoad] = useState(false);
  const [error, setError] = useState("");

  async function check(event) {
    event.preventDefault();

    try {
      setLoad(true);
      setError("");
      const response = await api.post("/eligibility", { profile });
      setResult({
        ...response.data,
        matches: response.data.matches || [],
        near_misses: response.data.near_misses || [],
      });
    } catch (err) {
      setError(getErrorMessage(err, "Could not check your eligibility."));
      setResult(null);
    } finally {
      setLoad(false);
    }
  }

  function reset() {
    setProfile(EMPTY_PROFILE);
    setResult(null);
    setError("");
  }

  return (
    <div>
      <PageHeader
        icon="fa-clipboard-check"
        title="Check your eligibility"
        subtitle="Fill in what you know. Blank boxes are treated as unknown, not as zero."
      />

      <form onSubmit={check} className="panel corners p-4 mb-4">
        <ProfileForm profile={profile} onChange={setProfile} disabled={load} />

        <div className="d-flex gap-2 mt-4">
          <button type="submit" className="btn btn-brand" disabled={load}>
            {load ? "Checking ..." : "Find my schemes"}
          </button>
          <button
            type="button"
            className="btn btn-light"
            onClick={reset}
            disabled={load}
          >
            Clear
          </button>
        </div>
      </form>

      {error && <div className="alert alert-danger">{error}</div>}

      {result && (
        <>
          <div className="result-summary corners p-3 mb-3">
            <strong>{result.matches.length}</strong> of{" "}
            <strong>{result.total_schemes}</strong> schemes in this corpus match
            your profile.
            {result.matches.length === 0 && (
              <span>
                {" "}
                Nothing matched exactly, so nothing is being suggested. The near
                misses below are the closest ones.
              </span>
            )}
          </div>

          {result.matches.map((scheme) => (
            <div className="scheme-card corners p-4 mb-3" key={scheme.id}>
              <div className="d-flex flex-wrap align-items-start">
                <div className="flex-grow-1">
                  <h5 className="mb-1">
                    <Link to={`/schemes/${scheme.id}`}>{scheme.name}</Link>
                  </h5>
                  <p className="scheme-provider mb-2">{scheme.provider}</p>
                </div>
                {scheme.deadline && (
                  <span className="badge-deadline">
                    <i className="fa-regular fa-calendar me-1"></i>
                    Closes {scheme.deadline}
                  </span>
                )}
              </div>

              <p className="info-text">{scheme.description}</p>

              {scheme.amount_text && (
                <p className="mb-3">
                  <i className="fa-solid fa-indian-rupee-sign me-2 text-brand"></i>
                  {scheme.amount_text}
                </p>
              )}

              <div className="reasons">
                <p className="reasons-title mb-2">Why this matched you</p>
                <ul className="mb-0">
                  {scheme.match_reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>

              {scheme.unchecked_rules.length > 0 && (
                <div className="unchecked mt-3">
                  <p className="reasons-title mb-2">
                    <i className="fa-solid fa-triangle-exclamation me-2"></i>
                    Could not be checked
                  </p>
                  <ul className="mb-0">
                    {scheme.unchecked_rules.map((rule) => (
                      <li key={rule}>{rule}</li>
                    ))}
                  </ul>
                </div>
              )}

              {scheme.unverified_fields.length > 0 && (
                <div className="unverified mt-3">
                  <i className="fa-solid fa-circle-question me-2"></i>
                  We could not confirm these rules against the source page:{" "}
                  <strong>{scheme.unverified_fields.join(", ")}</strong>. Please
                  check them yourself before applying.
                </div>
              )}

              <a
                className="btn btn-outline-brand btn-sm mt-3"
                href={scheme.source_url}
                target="_blank"
                rel="noreferrer"
              >
                Open the official page
                <i className="fa-solid fa-arrow-up-right-from-square ms-2"></i>
              </a>
            </div>
          ))}

          {result.near_misses.length > 0 && (
            <>
              <h4 className="section-title mt-4 mb-2">You just missed these</h4>
              <p className="info-text">
                Each of these failed on exactly one rule. Nothing else about
                your profile was a problem.
              </p>

              {result.near_misses.map((scheme) => (
                <div className="near-miss-card corners p-3 mb-2" key={scheme.id}>
                  <div className="d-flex flex-wrap align-items-center">
                    <div className="flex-grow-1">
                      <strong>
                        <Link to={`/schemes/${scheme.id}`}>{scheme.name}</Link>
                      </strong>
                      <div className="scheme-provider">{scheme.provider}</div>
                    </div>
                    <span className="missed-by">{scheme.missed_by}</span>
                  </div>
                </div>
              ))}
            </>
          )}
        </>
      )}
    </div>
  );
}

export default Eligibility;
