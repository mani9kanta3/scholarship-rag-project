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

/*
  Refuse a reply that is not JSON.

  This caught a real bug the first time the site was deployed. VITE_API_URL
  was not set, so axios had no base URL and asked the site itself for
  /schemes. The single page app rewrite answers every path with
  index.html and a 200, so axios handed back a page of HTML, the code
  read .results off it, got undefined, and the whole page went white
  with a console error nobody would see.

  A 200 carrying HTML is not a successful API call. Saying so here turns
  a blank screen into one clear sentence, and it says the thing that is
  actually wrong.
*/
api.interceptors.response.use((response) => {
  const looksLikeHtml =
    typeof response.data === "string" && response.data.trim().startsWith("<");

  if (looksLikeHtml) {
    return Promise.reject(
      new Error(
        "The API address is not set correctly, so the site asked itself " +
          "instead of the server. Check VITE_API_URL."
      )
    );
  }

  return response;
});

export default api;
