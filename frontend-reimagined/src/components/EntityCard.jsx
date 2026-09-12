import { Link } from "react-router-dom";
import { formatScore } from "../utils/validate.js";
import { TypeBadge } from "./Badges.jsx";
import NameId from "./NameId.jsx";
import ScoreBar from "./ScoreBar.jsx";

export default function EntityCard({ entity }) {
  if (!entity) return null;
  const summary = entity.analytics_summary || {};
  const initials = String(entity.name || entity.id || "?")
    .split(/[\s_]+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card">
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-argus-600 text-lg font-extrabold text-white">
          {initials}
        </span>
        <div className="min-w-0">
          <h3 className="truncate text-lg">
            <NameId name={entity.name} id={entity.id} />
          </h3>
        </div>
        <span className="ml-auto">
          <TypeBadge type={entity.type} />
        </span>
      </div>
      {entity.aliases?.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {entity.aliases.map((alias) => (
            <span key={alias} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-600">
              {alias}
            </span>
          ))}
        </div>
      ) : null}
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <ScoreBar label="PageRank" value={summary.pagerank} display={formatScore(summary.pagerank)} />
        <ScoreBar
          label="Betweenness"
          value={summary.betweenness}
          display={formatScore(summary.betweenness)}
          barClass="bg-sky-500"
        />
        <ScoreBar
          label="Anomaly"
          value={summary.anomaly_score}
          display={formatScore(summary.anomaly_score)}
          barClass="bg-amber-500"
        />
      </div>
      <div className="mt-3 flex items-center justify-between text-sm">
        <p className="text-slate-500">
          Priority <span className="font-mono font-bold text-ink">{formatScore(summary.priority_score)}</span>
          <span className="ml-2 text-xs">· Community {summary.community_id ?? "—"}</span>
        </p>
        <div className="flex gap-3">
          <Link className="font-semibold text-argus-700 hover:underline" to={`/entities/${encodeURIComponent(entity.id)}`}>
            Profile
          </Link>
          <Link className="font-semibold text-argus-700 hover:underline" to={`/investigation/${encodeURIComponent(entity.id)}`}>
            Investigation
          </Link>
        </div>
      </div>
    </div>
  );
}
