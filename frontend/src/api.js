/*
  One axios instance for the whole app.

  There is no login here, so no token interceptor like the hardware
  store had. What there is instead is a longer timeout, because a
  question goes through retrieval, a reranker and a language model
  before it comes back, and the default 0 (no timeout) would leave the
  page spinning for ever if the backend hung.
*/

import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  // 60 seconds. A cold start on a free tier plus a slow model can
  // genuinely take half a minute, so anything shorter would cut off
  // answers that were about to arrive.
  timeout: 60000,
});

export default api;
