import React from "react";

/*
  The title strip at the top of every page. All five pages had the same
  block of markup, so I pulled it out into one small component.
*/
function PageHeader({ icon, title, subtitle, children }) {
  return (
    <div className="page-header d-flex align-items-center flex-wrap p-4">
      <div className="page-icon me-3">
        <i className={`fa-solid ${icon}`}></i>
      </div>
      <div>
        <h1 className="page-title mb-1">{title}</h1>
        <p className="page-subtitle mb-0">{subtitle}</p>
      </div>
      <div className="ms-auto">{children}</div>
    </div>
  );
}

export default PageHeader;
