import { useEffect, useState } from "react";

/*
  Wait until the user stops typing before doing anything with the value.

  Without this the browse page fires a request on every keystroke, so
  typing "scholarship" sends eleven requests and the answers can come
  back in the wrong order. The timer is cleared and restarted on each
  change, so only the last one survives.
*/
function useDebounce(value, delay = 500) {
  const [settled, setSettled] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return settled;
}

export default useDebounce;
