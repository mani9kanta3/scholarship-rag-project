import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import api from "./api";
import getErrorMessage from "./errorMessage";
import money from "./money";
import PageHeader from "./PageHeader";
import useDebounce from "./useDebounce";
import { STATES } from "./options";

/*
  Browse every scheme in the corpus.

  The search box and the state filter are sent to FastAPI as query
  params and the database does the filtering. It is only 44 schemes
  today, so filtering in the browser would work fine, but sending the
  whole table to React so React can filter it is a habit that stops
  working the moment the corpus grows, and I would rather not learn it.
*/
function Schemes() {
  const [schemes, setSchemes] = useState([]);
  const [total, setTotal] = useState(0);

  const [search, setSearch] = useState("");
  const [state, setState] = useState("");

  const [load, setLoad] = useState(true);
  const [error, setError] = useState("");

  const searchText = useDebounce(search, 500);

  // useCallback so the effect below does not build a new function on
  // every render and loop for ever.
  const loadSchemes = useCallback(async () => {
    try {
      setLoad(true);
      setError("");
      const response = await api.get("/schemes", {
        params: { search: searchText, state: state },
      });
      setSchemes(response.data.results);
      setTotal(response.data.count);
    } catch (err) {
      setError(getErrorMessage(err, "Could not load the schemes."));
    } finally {
      setLoad(false);
    }
  }, [searchText, state]);

  useEffect(() => {
    loadSchemes();
  }, [loadSchemes]);

  return (
    <div>
      <PageHeader
        icon="fa-list"
        title="Browse schemes"
        subtitle={`${total} schemes collected from public pages`}
      />

      <div className="panel corners p-3 mb-4">
        <div className="row g-3">
          <div className="col-md-8">
            <label className="field-label form-label">Search</label>
            <input
              type="text"
              className="form-control"
              placeholder="Scheme name or description"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="col-md-4">
            <label className="field-label form-label">State</label>
            <select
              className="form-select"
              value={state}
              onChange={(e) => setState(e.target.value)}
            >
              <option value="">All states</option>
              {STATES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {load && <p className="info-text">Loading ...</p>}

      {!load && schemes.length === 0 && !error && (
        <p className="info-text">No scheme matches that search.</p>
      )}

      <div className="row g-3">
        {schemes.map((scheme) => (
          <div className="col-md-6" key={scheme.id}>
            <div className="scheme-card corners p-4 h-100">
              <h5 className="mb-1">
                <Link to={`/schemes/${scheme.id}`}>{scheme.name}</Link>
              </h5>
              <p className="scheme-provider mb-2">{scheme.provider}</p>
              <p className="info-text">{scheme.description}</p>

              <div className="rule-chips">
                {scheme.max_family_income !== null && (
                  <span className="rule-chip">
                    Income up to {money(scheme.max_family_income)}
                  </span>
                )}
                {scheme.min_percentage !== null && (
                  <span className="rule-chip">{scheme.min_percentage}% and above</span>
                )}
                {scheme.min_cgpa !== null && (
                  <span className="rule-chip">CGPA {scheme.min_cgpa} and above</span>
                )}
                {scheme.categories &&
                  scheme.categories.map((category) => (
                    <span className="rule-chip" key={category}>
                      {category}
                    </span>
                  ))}
                {scheme.states &&
                  scheme.states.map((item) => (
                    <span className="rule-chip state-chip" key={item}>
                      {item}
                    </span>
                  ))}
                {!scheme.states && <span className="rule-chip state-chip">All India</span>}
              </div>

              {scheme.deadline && (
                <p className="mb-0 mt-3 scheme-deadline">
                  <i className="fa-regular fa-calendar me-2"></i>
                  Closes {scheme.deadline}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default Schemes;
