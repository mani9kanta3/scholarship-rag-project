import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";

import "./App.css";
import Layout from "./Layout";
import Home from "./Home";
import Eligibility from "./Eligibility";
import Ask from "./Ask";
import Schemes from "./Schemes";
import SchemeDetail from "./SchemeDetail";
import Evaluation from "./Evaluation";
import NotFound from "./NotFound";

/*
  All the routes.

  There is no login anywhere in this project. A student answering
  questions about their own marks and income should not have to make an
  account first, and the guide lists user accounts under things not to
  build. So every page sits inside Layout and that is the whole routing
  story.
*/
function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/eligibility" element={<Eligibility />} />
          <Route path="/ask" element={<Ask />} />
          <Route path="/schemes" element={<Schemes />} />
          <Route path="/schemes/:id" element={<SchemeDetail />} />
          <Route path="/evaluation" element={<Evaluation />} />
        </Route>

        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
