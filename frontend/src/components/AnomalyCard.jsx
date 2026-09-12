import { Link } from "react-router-dom";
import { formatScore, severityTone } from "../utils/validate.js";

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
    <div className="rounded border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <Link
          className="font-medium text-blue-700 underline"
          to={`/entities/${encodeURIComponent(item.entity_id)}`}
        >
          {item.entity_id}
        </Link>
        <span className={`rounded border px-2 py-0.5 text-xs font-semibold ${severityTone(item.severity)}`}>
          {item.severity} · {formatScore(item.anomaly_score)}
        </span>
      </div>
      {item.reasons?.length ? (
        <ul className="mt-2 list-disc pl-5 text-sm text-gray-700">
          {item.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-gray-500">No elevated signals.</p>
      )}
      {item.features ? (
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-600 sm:grid-cols-4">
          {Object.entries(FEATURE_LABELS).map(([key, label]) => (
            <div key={key}>
              <dt>{label}</dt>
              <dd className="font-medium text-gray-900">{item.features[key] ?? "—"}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}
