import { ShieldAlert } from "lucide-react";
import { riskStyle } from "../../lib/format.js";

export default function RiskPanel({ assessment }) {
  if (!assessment) return null;
  const style = riskStyle(assessment.level);

  return (
    <div className={`rounded-2xl border p-5 ${style.className}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldAlert size={20} />
          <h3 className="font-semibold">{style.label}</h3>
        </div>
        {assessment.score !== null && assessment.score !== undefined && (
          <span className="text-sm font-medium">Score: {assessment.score.toFixed(0)}/100</span>
        )}
      </div>
      {assessment.reasons?.length > 0 && (
        <ul className="mt-3 space-y-1.5 text-sm leading-5">
          {assessment.reasons.map((reason, idx) => (
            <li key={idx} className="flex gap-2">
              <span aria-hidden>•</span>
              <span>{reason}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
