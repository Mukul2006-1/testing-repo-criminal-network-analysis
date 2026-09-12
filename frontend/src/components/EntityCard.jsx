import { Link } from "react-router-dom";
import { formatScore } from "../utils/validate.js";

export default function EntityCard({ entity }) {
  if (!entity) return null;
  const summary = entity.analytics_summary || {};
  return (
    <div className="rounded border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-lg font-semibold text-gray-900">{entity.name}</h3>
        <span className="rounded bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700">
          {entity.type}
        </span>
      </div>
      <p className="mt-1 font-mono text-xs text-gray-500">{entity.id}</p>
      {entity.aliases?.length ? (
        <p className="mt-2 text-sm text-gray-600">Also seen as: {entity.aliases.join(", ")}</p>
      ) : null}
      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <div><dt className="text-gray-500">Degree</dt><dd className="font-medium">{summary.degree ?? "—"}</dd></div>
        <div><dt className="text-gray-500">PageRank</dt><dd className="font-medium">{formatScore(summary.pagerank)}</dd></div>
        <div><dt className="text-gray-500">Betweenness</dt><dd className="font-medium">{formatScore(summary.betweenness)}</dd></div>
        <div><dt className="text-gray-500">Community</dt><dd className="font-medium">{summary.community_id ?? "—"}</dd></div>
        <div><dt className="text-gray-500">Anomaly</dt><dd className="font-medium">{formatScore(summary.anomaly_score)}</dd></div>
        <div>
          <dt className="text-gray-500">Investigation Priority</dt>
          <dd className="font-semibold">{formatScore(summary.priority_score)}</dd>
        </div>
      </dl>
      <div className="mt-3 flex gap-3 text-sm">
        <Link className="text-blue-700 underline" to={`/entities/${encodeURIComponent(entity.id)}`}>
          Profile
        </Link>
        <Link className="text-blue-700 underline" to={`/investigation/${encodeURIComponent(entity.id)}`}>
          Investigation
        </Link>
      </div>
    </div>
  );
}
