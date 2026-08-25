import React from "react";
import { Outlet } from "react-router-dom";

import Navbar from "./Navbar";

/*
  The shell every page sits inside: the nav bar on top, the page below.
  Outlet is where React Router puts the page.

  The hardware store used a sidebar because it was a tool people work in
  all day. This is a site a student visits once, so a plain top bar with
  four links is enough and leaves the whole width for the results.
*/
function Layout() {
  return (
    <div className="app-shell">
      <Navbar />
      <div className="app-content">
        <Outlet />
      </div>
      <footer className="app-footer text-center">
        <p className="mb-0">
          Scholarship information is collected from public pages and may be out
          of date. Always check the official source link before applying.
        </p>
      </footer>
    </div>
  );
}

export default Layout;
