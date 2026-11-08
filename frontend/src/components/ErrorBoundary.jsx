import { Component } from "react";
import { AlertTriangle, RefreshCcw } from "lucide-react";

/**
 * Root-level error boundary. If any child component throws (a malformed API
 * shape, a Leaflet edge case, etc.), the whole app would otherwise unmount to
 * a blank white screen with no recovery. This catches it, shows what went
 * wrong, and offers a retry that re-mounts the tree.
 *
 * Intentionally minimal: it does not try to recover mid-state, it just
 * re-renders the subtree from scratch.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Keep the stack out of the DOM; log to console for debugging.
    if (typeof console !== "undefined") {
      console.error("Error boundary caught:", error, info);
    }
    this.setState({ info });
  }

  handleRetry() {
    this.setState({ hasError: false, error: null, info: null });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-[#f7f8fa] p-5 sm:p-8">
          <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-50 text-red-600">
              <AlertTriangle size={26} />
            </div>
            <h2 className="mt-5 text-lg font-semibold">Something went wrong</h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              A part of the app failed to render. This is usually a transient issue —
              reloading the page or retrying should get you back on track.
            </p>
            {this.state.error && (
              <details className="mt-4 rounded-lg bg-slate-50 p-3 text-left text-xs text-slate-600">
                <summary className="cursor-pointer font-medium">Technical details</summary>
                <pre className="mt-2 whitespace-pre-wrap break-words">
                  {this.state.error.message || String(this.state.error)}
                </pre>
              </details>
            )}
            <button
              onClick={() => this.handleRetry()}
              className="mt-6 inline-flex items-center gap-2 rounded-xl bg-[#203C5A] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#172E46]"
            >
              <RefreshCcw size={16} /> Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}