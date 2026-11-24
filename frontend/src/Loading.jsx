import React, { useEffect, useState } from "react";

/*
  The wait, explained once it stops being a normal wait.

  The API runs on a free instance that goes to sleep after fifteen
  minutes with nobody on it, and takes the better part of a minute to
  wake up again. Measured from the live site, the first request after a
  sleep came back in 8.2 seconds, and a cold morning start is longer.

  Every one of those seconds used to show the word "Loading" and
  nothing else, which is exactly how a working page comes to look
  broken. Eight seconds is far past the point where a reader decides
  something has gone wrong, and the first visitor of the day is the one
  who sees it. For this project that visitor is usually somebody
  deciding whether the whole thing works.

  So: say "Loading" straight away, because most of the time that is the
  truth and the data arrives before anyone reads it. Then, after two
  and a half seconds, say what is actually happening. The explanation
  only appears when the wait has already become unusual, so a fast load
  is never cluttered by an apology it did not need.

  Being specific matters more than being reassuring. "Please wait" tells
  a reader nothing. "The server sleeps when nobody is using it, and
  takes about a minute to wake" tells them it is a free hosting tier
  rather than a broken service, and gives them a number so they can
  decide whether to stay.
*/

// Long enough that an ordinary load never triggers it, short enough to
// arrive before a reader concludes the page is dead.
const EXPLAIN_AFTER_MS = 2500;

function Loading({ what = "this" }) {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), EXPLAIN_AFTER_MS);
    // Cleared if the data arrives first, so a component that unmounts
    // quickly does not set state after it has gone.
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="loading-state" role="status" aria-live="polite">
      <div className="loading-row">
        <span className="loading-spinner" aria-hidden="true"></span>
        <span className="loading-label">Loading {what}</span>
      </div>

      {slow && (
        <p className="loading-note mb-0">
          This is taking longer than usual. The API runs on a free instance
          that sleeps when nobody is using it, and it can take up to a minute
          to wake up. It will be quick after this.
        </p>
      )}
    </div>
  );
}

export default Loading;
