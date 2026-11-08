// frontend/src/hooks/useAbortableRequest.js
//
// Generalizes two patterns that already exist separately in this codebase:
//   - NearbyPlacesPage.jsx: a monotonically increasing `latestRequestRef`
//     so a slow, earlier-started request can never overwrite state set by
//     a faster, later one.
//
// Both guards matter and neither alone is airtight:
//   - AbortController cancels the network request, but a handler can
//     still run after abort() in edge cases (a response already fully
//     buffered before abort fires, a mocked fetch in tests, a
//     service-worker intercepting the request) — so "aborted" is not a
//     100% reliable signal on its own.
//   - A request-id guard is a pure in-memory check with no such edge
//     cases: it is cheap, synchronous, and always correct.
// Using both means: if either one says "this result is stale", you throw
// it away.
//
// Returns a `run(taskFn, { debounceMs })` function. taskFn receives an
// AbortSignal and should pass it to fetch(). The returned promise resolves
// to `{ aborted: true }` for any stale/cancelled attempt (including ones
// superseded while they were still in the debounce window) or
// `{ aborted: false, value }` on success — it never resolves with a stale
// value, and it re-throws a genuine (non-abort) error so the caller's own
// try/catch still runs its error-handling branch.
//
// Automatically aborts any in-flight request on unmount, which is the
// single most common source of the "Can't perform a React state update on
// an unmounted component" warning in viewport/typeahead-driven fetchers.

import { useCallback, useEffect, useRef } from "react";

export function useAbortableRequest() {
  const controllerRef = useRef(null);
  const requestIdRef = useRef(0);

  const run = useCallback(async (taskFn, { debounceMs = 0 } = {}) => {
    const requestId = ++requestIdRef.current;

    // Cancel whatever was previously in flight (or still debouncing) —
    // this is what makes "type/pan fast, only the last request's result
    // ever lands" work without any manual bookkeeping at call sites.
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    if (debounceMs > 0) {
      await new Promise((resolve) => {
        const timer = setTimeout(resolve, debounceMs);
        controller.signal.addEventListener("abort", () => {
          clearTimeout(timer);
          resolve();
        });
      });
    }

    const isStale = () => requestIdRef.current !== requestId || controller.signal.aborted;
    if (isStale()) return { aborted: true };

    try {
      const value = await taskFn(controller.signal);
      if (isStale()) return { aborted: true };
      return { aborted: false, value };
    } catch (error) {
      if (isStale() || controller.signal.aborted || error?.name === "AbortError") {
        return { aborted: true };
      }
      throw error; // a real error — let the caller's catch block handle it
    }
  }, []);

  useEffect(() => () => controllerRef.current?.abort(), []);

  return run;
}
