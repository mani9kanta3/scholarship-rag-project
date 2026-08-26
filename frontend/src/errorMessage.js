/*
  FastAPI sends errors back in a few different shapes, so every page was
  ending up with the same messy if-else. This turns any of them into one
  plain sentence I can show the user.
*/

function getErrorMessage(error, fallback = "Something went wrong. Please try again.") {
  // The request never reached the server at all.
  if (error && error.code === "ECONNABORTED") {
    return "The server took too long to answer. Please try again.";
  }

  // Thrown by the interceptor in api.js when the reply was a web page
  // rather than data. It already reads as a sentence, so pass it on.
  if (error && error.message && !error.response) {
    return error.message;
  }

  const data = error && error.response && error.response.data;

  if (!data) {
    return fallback;
  }

  // {"detail": "No scheme with that id."}
  if (typeof data.detail === "string") {
    return data.detail;
  }

  /*
    A 422 from Pydantic looks like:
    {"detail": [{"loc": ["body", "profile", "cgpa"], "msg": "..."}]}
    The last part of loc is the field name, which is the only bit of it
    a person actually needs to see.
  */
  if (Array.isArray(data.detail)) {
    const messages = data.detail.map((item) => {
      const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : "";
      return field ? `${field}: ${item.msg}` : item.msg;
    });
    return messages.join(" ");
  }

  return fallback;
}

export default getErrorMessage;
