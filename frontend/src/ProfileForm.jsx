import React from "react";

import { CATEGORIES, COURSE_LEVELS, GENDERS, STATES } from "./options";
import { inWords } from "./money";

/*
  The profile form.

  Two pages need it, the eligibility page and the ask page, so it lives
  in its own file and the parent holds the state. That keeps the two
  pages from drifting apart, which is what happened in my last project
  when I copied a form instead of sharing it.

  Nothing here is required. A student who does not know their family
  income should still be able to press the button and get something
  useful, and the backend reports which rules it could not check rather
  than pretending they passed.
*/
function ProfileForm({ profile, onChange, disabled }) {
  function set(field, value) {
    // An empty box means "not answered", which has to reach the backend
    // as null. Sending "" would be read as a real value and match
    // nothing at all.
    onChange({ ...profile, [field]: value === "" ? null : value });
  }

  return (
    <div className="row g-3">
      <div className="col-md-4">
        <label className="field-label form-label">Percentage of marks</label>
        <input
          type="number"
          className="form-control"
          min="0"
          max="100"
          step="0.01"
          placeholder="e.g. 72"
          value={profile.percentage ?? ""}
          onChange={(e) => set("percentage", e.target.value)}
          disabled={disabled}
        />
        <div className="form-hint">From your last completed exam.</div>
      </div>

      <div className="col-md-4">
        <label className="field-label form-label">CGPA (out of 10)</label>
        <input
          type="number"
          className="form-control"
          min="0"
          max="10"
          step="0.01"
          placeholder="e.g. 7.6"
          value={profile.cgpa ?? ""}
          onChange={(e) => set("cgpa", e.target.value)}
          disabled={disabled}
        />
        <div className="form-hint">Only if your college uses CGPA.</div>
      </div>

      <div className="col-md-4">
        <label className="field-label form-label">Annual family income</label>
        <input
          type="number"
          className="form-control"
          min="0"
          step="1000"
          placeholder="e.g. 240000"
          value={profile.income ?? ""}
          onChange={(e) => set("income", e.target.value)}
          disabled={disabled}
        />
        <div className="form-hint">
          {profile.income
            ? `That is ${inWords(profile.income)} rupees a year.`
            : "In rupees, from all sources."}
        </div>
      </div>

      <div className="col-md-4">
        <label className="field-label form-label">Category</label>
        <select
          className="form-select"
          value={profile.category ?? ""}
          onChange={(e) => set("category", e.target.value)}
          disabled={disabled}
        >
          <option value="">Not saying</option>
          {CATEGORIES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </div>

      <div className="col-md-4">
        <label className="field-label form-label">Course level</label>
        <select
          className="form-select"
          value={profile.course_level ?? ""}
          onChange={(e) => set("course_level", e.target.value)}
          disabled={disabled}
        >
          <option value="">Not saying</option>
          {COURSE_LEVELS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </div>

      <div className="col-md-4">
        <label className="field-label form-label">State</label>
        <select
          className="form-select"
          value={profile.state ?? ""}
          onChange={(e) => set("state", e.target.value)}
          disabled={disabled}
        >
          <option value="">Not saying</option>
          {STATES.map((state) => (
            <option key={state} value={state}>
              {state}
            </option>
          ))}
        </select>
      </div>

      <div className="col-md-4">
        <label className="field-label form-label">Gender</label>
        <select
          className="form-select"
          value={profile.gender ?? ""}
          onChange={(e) => set("gender", e.target.value)}
          disabled={disabled}
        >
          <option value="">Not saying</option>
          {GENDERS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </div>

      <div className="col-md-4">
        <label className="field-label form-label">Age</label>
        <input
          type="number"
          className="form-control"
          min="5"
          max="100"
          placeholder="e.g. 19"
          value={profile.age ?? ""}
          onChange={(e) => set("age", e.target.value)}
          disabled={disabled}
        />
        <div className="form-hint">Some schemes have an age limit.</div>
      </div>
    </div>
  );
}

export default ProfileForm;
