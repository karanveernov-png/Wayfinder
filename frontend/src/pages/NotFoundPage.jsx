import { Link } from "react-router-dom";
import { Compass, ArrowLeft } from "lucide-react";

/**
 * 404 page — shown when no route matches. Keeps the sidebar layout so the
 * user never feels lost, and offers a clear path back to the dashboard.
 */
export default function NotFoundPage() {
  return (
    <main className="page">
      <div className="text-center py-16 sm:py-20">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-slate-100 text-slate-400">
          <Compass size={32} />
        </div>
        <h1 className="mt-6 text-2xl font-bold">Page not found</h1>
        <p className="mt-2 max-w-sm mx-auto text-sm leading-6 text-slate-500">
          The route you requested doesn't exist. It may have been mistyped or
          removed.
        </p>
        <Link
          to="/"
          className="mt-6 inline-flex items-center gap-2 rounded-xl bg-[#203C5A] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#172E46]"
        >
          <ArrowLeft size={16} /> Back to Overview
        </Link>
      </div>
    </main>
  );
}