import { dataStatusStyle } from "../../lib/format.js";

/** Renders data_status.mode per the contract's rule: demo/degraded must never look like a confident live result. */
export default function DataStatusBadge({ mode, className = "" }) {
  const style = dataStatusStyle(mode);
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-medium ${style.className} ${className}`}>
      {style.label}
    </span>
  );
}
