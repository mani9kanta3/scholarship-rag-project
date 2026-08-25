import React from "react";
import { Link } from "react-router-dom";

/*
  The landing page.

  It says what the tool does and, just as importantly, what it will not
  do. A student reading eligibility advice needs to know up front that
  this refuses when it is unsure, because a system that sometimes says
  "I do not know" is only trustworthy if you were told to expect it.
*/
function Home() {
  return (
    <div className="home">
      <section className="hero text-center">
        <h1 className="hero-title">Which scholarships can you actually get?</h1>
        <p className="hero-subtitle">
          Fill in your marks, income and category once. Every scheme is checked
          against your numbers exactly, and every answer links back to the page
          it came from.
        </p>
        <div className="d-flex justify-content-center flex-wrap gap-2 mt-4">
          <Link className="btn btn-brand btn-lg" to="/eligibility">
            <i className="fa-solid fa-clipboard-check me-2"></i>
            Check my eligibility
          </Link>
          <Link className="btn btn-outline-brand btn-lg" to="/ask">
            <i className="fa-solid fa-comments me-2"></i>
            Ask a question
          </Link>
        </div>
      </section>

      <section className="row g-3 mt-2">
        <div className="col-md-4">
          <div className="info-card corners h-100 p-4">
            <div className="info-icon mb-3">
              <i className="fa-solid fa-calculator"></i>
            </div>
            <h5>Your numbers are compared, not guessed</h5>
            <p className="info-text mb-0">
              The income limits and mark cutoffs are stored as real numbers in a
              database, and your profile is compared against them with plain
              arithmetic. "CGPA above 7.5" and "above 8.5" look almost identical
              to a search engine. They do not look alike to a subtraction.
            </p>
          </div>
        </div>

        <div className="col-md-4">
          <div className="info-card corners h-100 p-4">
            <div className="info-icon mb-3">
              <i className="fa-solid fa-link"></i>
            </div>
            <h5>Every answer names its source</h5>
            <p className="info-text mb-0">
              Answers are written only from the scheme pages we hold, and each
              one carries a link to the page it was read from, so you can check
              it yourself before you apply.
            </p>
          </div>
        </div>

        <div className="col-md-4">
          <div className="info-card corners h-100 p-4">
            <div className="info-icon mb-3">
              <i className="fa-solid fa-shield-halved"></i>
            </div>
            <h5>It says when it does not know</h5>
            <p className="info-text mb-0">
              If a figure in an answer cannot be traced back to a source, the
              answer is blocked rather than shown. A wrong deadline is worse
              than no deadline, so you will sometimes be told to go and check
              the official page instead.
            </p>
          </div>
        </div>
      </section>

      <section className="mt-4">
        <div className="honest-note corners p-4">
          <h5 className="mb-2">
            <i className="fa-solid fa-circle-info me-2"></i>
            What this is not
          </h5>
          <p className="info-text mb-0">
            This is a study project built on a small set of scholarship pages
            collected from the web, not an official government service. It does
            not cover every scheme in India, the pages it holds may have changed
            since they were collected, and it cannot submit an application for
            you. Treat it as a starting point and confirm everything on the
            official portal. You can see exactly how well it performs, including
            where it gets things wrong, on the{" "}
            <Link to="/evaluation">How well it works</Link> page.
          </p>
        </div>
      </section>
    </div>
  );
}

export default Home;
