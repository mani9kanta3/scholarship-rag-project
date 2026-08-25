import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import api from "./api";
import getErrorMessage from "./errorMessage";
import money from "./money";
import PageHeader from "./PageHeader";

/*
  One scheme in full.

  The unusual part of this page is the extraction panel at the bottom.
  It shows which rules were read out of the document by a language
  model, the exact sentence each one came from, and whether the
  automatic check could confirm it.

  Most tools hide that. I would rather show it, because the rules in the
  table were written by a model and a student deciding whether to spend
  a day on an application deserves to see the sentence behind the number
  and judge it themselves.
*/
function SchemeDetail() {
  const { id } = useParams();

  const [scheme, setScheme] = useState(null);
  const [load, setLoad] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadScheme() {
      try {
        setLoad(true);
        setError("");
        const response = await api.get(`/schemes/${id}`);
        setScheme(response.data);
      } catch (err) {
        setError(getErrorMessage(err, "Could not load that scheme."));
      } finally {
        setLoad(false);
      }
    }

    loadScheme();
  }, [id]);

  if (load) {
    return <p className="info-text p-4">Loading ...</p>;
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="alert alert-danger">{error}</div>
        <Link className="btn btn-light" to="/schemes">
          Back to all schemes
        </Link>
      </div>
    );
  }

  const rules = [
    ["Minimum percentage", scheme.min_percentage !== null ? `${scheme.min_percentage}%` : null],
    ["Minimum CGPA", scheme.min_cgpa !== null ? scheme.min_cgpa : null],
    ["Family income limit", scheme.max_family_income !== null ? money(scheme.max_family_income) : null],
    ["Categories", scheme.categories ? scheme.categories.join(", ") : null],
    ["Gender", scheme.genders ? scheme.genders.join(", ") : null],
    ["Course levels", scheme.course_levels ? scheme.course_levels.join(", ") : null],
    ["States", scheme.states ? scheme.states.join(", ") : null],
    ["Minimum age", scheme.min_age],
    ["Maximum age", scheme.max_age],
  ];

  return (
    <div>
      <PageHeader icon="fa-file-lines" title={scheme.name} subtitle={scheme.provider}>
        <a
          className="btn btn-brand"
          href={scheme.source_url}
          target="_blank"
          rel="noreferrer"
        >
          Official page
          <i className="fa-solid fa-arrow-up-right-from-square ms-2"></i>
        </a>
      </PageHeader>

      <div className="panel corners p-4 mb-3">
        <p className="info-text">{scheme.description}</p>
        {scheme.amount_text && (
          <p className="mb-2">
            <i className="fa-solid fa-indian-rupee-sign me-2 text-brand"></i>
            {scheme.amount_text}
          </p>
        )}
        <p className="mb-0 scheme-provider">
          Deadline: {scheme.deadline || "not stated"} &nbsp;|&nbsp; Page collected
          on {scheme.last_updated}
        </p>
      </div>

      <div className="panel corners p-4 mb-3">
        <h5 className="mb-3">The rules, as columns</h5>
        <table className="table rules-table mb-0">
          <tbody>
            {rules.map(([label, value]) => (
              <tr key={label}>
                <th>{label}</th>
                <td>
                  {value === null || value === undefined ? (
                    <span className="no-limit">no limit set</span>
                  ) : (
                    value
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="info-text mt-3 mb-0">
          "No limit set" means the scheme document does not restrict that field,
          so it never rules anyone out. It does not mean the value is unknown.
        </p>
      </div>

      <div className="panel corners p-4 mb-3">
        <h5 className="mb-1">Where these rules came from</h5>
        <p className="info-text">
          Each rule was read out of the scheme document by a language model,
          which had to quote the sentence it read it from. The check confirms
          that the sentence really is in the document and really contains the
          value. Confidence is the share of rules that passed:{" "}
          <strong>{scheme.extraction_confidence}</strong>.
        </p>

        {Object.keys(scheme.field_sources).length === 0 && (
          <p className="info-text mb-0">No rules were extracted for this scheme.</p>
        )}

        {Object.entries(scheme.field_sources).map(([field, record]) => (
          <div className="source-row" key={field}>
            <div className="d-flex align-items-center flex-wrap">
              <strong className="me-2">{field}</strong>
              <code className="me-2">{JSON.stringify(record.value)}</code>
              <span className={record.verified ? "check-pass" : "check-fail"}>
                {record.verified ? "confirmed" : "not confirmed"}
              </span>
            </div>
            <p className="quoted mb-0">"{record.quote}"</p>
            {!record.verified && <p className="fail-reason mb-0">{record.reason}</p>}
          </div>
        ))}
      </div>

      <div className="panel corners p-4">
        <h5 className="mb-3">The document</h5>
        {scheme.sections.map((section, index) => (
          <div className="doc-section" key={index}>
            <p className="doc-section-name">{section.section}</p>
            <p className="doc-section-text mb-0">{section.chunk_text}</p>
          </div>
        ))}
      </div>

      <div className="mt-3">
        <Link className="btn btn-light" to="/schemes">
          Back to all schemes
        </Link>
      </div>
    </div>
  );
}

export default SchemeDetail;
