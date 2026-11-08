import { AlertTriangle } from "lucide-react";
import { SEVERITY_STYLES, isDemoAlert } from "../../lib/format.js";

export default function AlertsList({ alerts, dataStatus }) {
  const notConfigured = dataStatus?.sources?.some(
    (s) => s.name === "alerts" && s.status === "not_configured"
  );

  if (notConfigured) {
    return (
      <p className="text-sm text-slate-500">
        Alerts: not available for this deployment — no live alerts provider is configured. This does
        not mean the route is clear.
      </p>
    );
  }

  if (!alerts || alerts.length === 0) {
    return <p className="text-sm text-slate-500">No alerts reported for this route.</p>;
  }

  return (
    <ul className="space-y-3">
      {alerts.map((alert, idx) => (
        <li key={alert.id || idx} className="rounded-xl border border-slate-100 p-3">
          <div className="flex items-center gap-2">
            <AlertTriangle size={16} className="text-amber-600" />
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_STYLES[alert.severity] || SEVERITY_STYLES.unknown}`}>
              {alert.severity}
            </span>
            {isDemoAlert(alert) && (
              <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
                Demo data
              </span>
            )}
          </div>
          <p className="mt-2 text-sm leading-5 text-slate-700">{alert.description}</p>
        </li>
      ))}
    </ul>
  );
}
