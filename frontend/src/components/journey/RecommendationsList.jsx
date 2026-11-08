import { Lightbulb } from "lucide-react";

export default function RecommendationsList({ recommendations }) {
  if (!recommendations || recommendations.length === 0) return null;
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="flex items-center gap-2">
        <Lightbulb size={20} className="text-[#203C5A]" />
        <h3 className="font-semibold">Recommendations</h3>
      </div>
      <ul className="mt-3 space-y-2 text-sm leading-5 text-slate-600">
        {recommendations.map((rec, idx) => (
          <li key={idx} className="flex gap-2">
            <span aria-hidden>•</span>
            <span>{rec}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
