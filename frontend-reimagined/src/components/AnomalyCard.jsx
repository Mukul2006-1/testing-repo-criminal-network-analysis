import { Link } from "react-router-dom";
import { formatScore } from "../utils/validate.js";
import { SeverityBadge } from "./Badges.jsx";

const FEATURE_LABELS = {
  calls_per_day: "Calls/day",
  unique_contacts: "Contacts",
  average_call_duration: "Avg call (s)",
  night_calls: "Night calls",
  transaction_count: "Transactions",
  transaction_amount: "Txn amount",
  unique_locations: "Locations",
  location_changes: "Location changes",
};

export default function AnomalyCard({ item }) {
  if (!item) return null;
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link
          className="font-mono text-sm font-bold text-argus-700 hover:underline"
          to={`/entities/${encodeURIComponent(item.entity_id)}`}
        >
          {item.entity_id}
        </Link>
        <SeverityBadge severity={item.severity} score={formatScore(item.anomaly_score)} />
      </div>
      {item.reasons?.length ? (
        <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm text-slate-700">
          {item.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-slate-500">No elevated signals.</p>
      )}
      {item.features ? (
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-slate-100 pt-3 text-xs text-slate-500 sm:grid-cols-4">
          {Object.entries(FEATURE_LABELS).map(([key, label]) => (
            <div key={key}>
              <dt>{label}</dt>
              <dd className="font-mono font-semibold text-ink">{item.features[key] ?? "—"}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}
