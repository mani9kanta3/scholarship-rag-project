import React from "react";
import { NavLink, Link } from "react-router-dom";

/*
  The top bar.

  NavLink is used instead of Link for the four page links because it
  knows whether it is the page you are on and hands me an isActive flag,
  so the current page can be highlighted without me tracking the URL
  myself.
*/
const LINKS = [
  { to: "/eligibility", label: "Check eligibility", icon: "fa-clipboard-check" },
  { to: "/ask", label: "Ask a question", icon: "fa-comments" },
  { to: "/schemes", label: "Browse schemes", icon: "fa-list" },
  { to: "/evaluation", label: "How well it works", icon: "fa-chart-simple" },
];

function Navbar() {
  return (
    <nav className="navbar navbar-expand-lg app-navbar">
      <div className="container">
        <Link className="navbar-brand d-flex align-items-center" to="/">
          <span className="brand-mark me-2">
            <i className="fa-solid fa-graduation-cap"></i>
          </span>
          <span className="brand-text">Scholarship Assistant</span>
        </Link>

        <button
          className="navbar-toggler"
          type="button"
          data-bs-toggle="collapse"
          data-bs-target="#mainNav"
        >
          <span className="navbar-toggler-icon"></span>
        </button>

        <div className="collapse navbar-collapse" id="mainNav">
          <ul className="navbar-nav ms-auto">
            {LINKS.map((link) => (
              <li className="nav-item" key={link.to}>
                <NavLink
                  to={link.to}
                  className={({ isActive }) =>
                    isActive ? "nav-link nav-link-active" : "nav-link"
                  }
                >
                  <i className={`fa-solid ${link.icon} me-2`}></i>
                  {link.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </nav>
  );
}

export default Navbar;
