import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../services/api.js";
import { formatScore } from "../utils/validate.js";
import { SeverityBadge } from "./Badges.jsx";
import NameId from "./NameId.jsx";
import { T, useLang } from "../i18n/LangContext.jsx";
import { STRINGS } from "../i18n/strings.js";

/** "Why is this flagged?" — traffic-light verdict, plain reasons, evidence. */
export default function WhyFlagged({ entityId }) {
  const { t } = useLang();
  const [detail, setDetail] = useState(null);
  const [anomaly, setAnomaly] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!entityId) return;
    setLoading(true);
    Promise.all([
      api.entity(entityId).catch(() => null),
      api.anomalies({ entity_id: entityId, page_size: 1 }).catch(() => ({ items: [] })),
    ])
      .then(([entity, anoms]) => {
        setDetail(entity);
        setAnomaly((anoms.items || [])[0] || null);
      })
      .catch(() => {
        setDetail(null);
        setAnomaly(null);
      })
      .finally(() => setLoading(false));
  }, [entityId]);

  if (!entityId || loading) {
    return <p className="text-sm text-slate-500"><T k="loading" /></p>;
  }
  if (!detail) {
    return <p className="text-sm text-slate-500">No data for this entity.</p>;
  }
  const summary = detail.analytics_summary || {};
  const score = Number(summary.priority_score ?? 0);
  const verdict = score >= 0.6 ? "verdict_high" : score >= 0.35 ? "verdict_mid" : "verdict_low";
  const dot = score >= 0.6 ? "bg-red-500" : score >= 0.35 ? "bg-amber-500" : "bg-green-500";
  const reasons = [...(anomaly?.reasons || [])].filter(
    (r) => r && r !== "No anomaly signal"
  ).slice(0, 3);
  const refs = (detail.source_refs || []).slice(0, 3);

  return (
    <div className="rounded-2xl border border-argus-200 bg-argus-50/60 p-4">
      <p className="flex items-center gap-2 text-sm font-extrabold text-ink">
        <span className={`inline-block h-3 w-3 rounded-full ${dot}`} />
        <T k={verdict} />
        <span className="font-mono font-semibold text-slate-500">{formatScore(summary.priority_score)}</span>
      </p>
      <p className="mt-1 text-sm">
        <NameId name={detail.name} id={detail.id} />
      </p>
      <div className="mt-2 space-y-1 text-xs text-slate-600">
        <p>Network influence <span className="font-mono font-bold">{formatScore(summary.pagerank)}</span>
          {" · "}Bridge role <span className="font-mono font-bold">{formatScore(summary.betweenness)}</span>
          {" · "}Unusual-pattern flag <span className="font-mono font-bold">{formatScore(summary.anomaly_score)}</span></p>
      </div>
      {anomaly ? (
        <p className="mt-2"><SeverityBadge severity={anomaly.severity} score={formatScore(anomaly.anomaly_score)} /></p>
      ) : null}
      {reasons.length > 0 ? (
        <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-slate-700">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
      {refs.length > 0 ? (
        <p className="mt-2 font-mono text-[11px] text-slate-500">
          Evidence: {refs.map((r) => r.document_id).join(", ")}
        </p>
      ) : null}
      <div className="mt-3 flex gap-3 text-xs font-bold">
        <Link className="text-argus-700 hover:underline" to={`/entities/${encodeURIComponent(detail.id)}`}>
          Profile
        </Link>
        <Link className="text-argus-700 hover:underline" to={`/investigation/${encodeURIComponent(detail.id)}`}>
          Full report
        </Link>
      </div>
      <p className="mt-2 text-[11px] text-slate-500">{t(STRINGS.triage_note)}</p>
    </div>
  );
}
