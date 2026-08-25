import React from "react";
import { Link } from "react-router-dom";

/*
  Anything that is not a real route lands here.
*/
function NotFound() {
  return (
    <div className="not-found text-center">
      <div className="display-1 mb-3">404</div>
      <h2 className="mb-2">That page does not exist</h2>
      <p className="info-text mb-4">
        The link may be old, or the address may have a typo in it.
      </p>
      <Link className="btn btn-brand" to="/">
        Back to the start
      </Link>
    </div>
  );
}

export default NotFound;
