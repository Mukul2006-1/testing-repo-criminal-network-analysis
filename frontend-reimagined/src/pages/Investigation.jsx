import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, api } from "../services/api.js";
import { formatScore, isValidId } from "../utils/validate.js";
import { SeverityBadge } from "../components/Badges.jsx";
import Card from "../components/Card.jsx";
import NameId from "../components/NameId.jsx";
import NetworkGraph from "../components/NetworkGraph.jsx";
import ScoreBar from "../components/ScoreBar.jsx";
import Term from "../components/Glossary.jsx";
import { T, useLang } from "../i18n/LangContext.jsx";
import Timeline from "../components/Timeline.jsx";
import { buildNarrative } from "../utils/narrative.js";

export default function Investigation() {
  const { id } = useParams();
  const { lang } = useLang();
  const [report, setReport] = useState(null);
  const [graph, setGraph] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [audit, setAudit] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isValidId(id || "")) {
      setError("Invalid entity ID in the address bar.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    Promise.all([
      api.investigation(id),
      api.graph(id, { depth: 1 }).catch(() => null),
      api.timeline(id, { page_size: 100 }).catch(() => null),
      api.auditVerify().catch(() => null),
    ])
      .then(([data, neighborhood, events, chain]) => {
        setReport(data);
        setGraph(neighborhood);
        setTimeline(events);
        setAudit(chain);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Load failed."))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p className="text-sm text-slate-500">Loading investigation…</p>;
  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!report) return <p className="text-sm text-slate-500">No investigation found.</p>;

  const priority = report.priority || {};
  const anomaly = report.anomaly || {};
  const metrics = report.graph_metrics || {};

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-400">
            ARGUS Node // Report
          </p>
          <h1 className="text-3xl font-extrabold text-ink"><T k="report_title" /></h1>
          <p className="mt-1">
            <NameId name={report.entity?.name} id={report.entity?.id} />
            <span className="ml-2 text-xs text-slate-500">{report.entity?.type}</span>
          </p>
        </div>
        <button
          className="no-print rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700 shadow-card hover:border-argus-400"
          type="button"
          onClick={() => window.print()}
        >
          ⎙ Export report
        </button>
      </div>

      <section className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm leading-relaxed text-amber-900">
        <strong>Flagged for investigation — requires investigator review.</strong> Scores below
        are triage signals, not findings of guilt or proof of criminal activity.
      </section>

      <Card title={<T k="summary_title" />}>
        <p className="text-sm leading-relaxed text-slate-800">{buildNarrative(report, lang)}</p>
        <p className="mt-2 text-xs text-slate-500">
          Hover any underlined term anywhere in the app for its meaning:{" "}
          <Term k="priority" /> · <Term k="pagerank" /> · <Term k="betweenness" /> ·{" "}
          <Term k="anomaly" />
        </p>
      </Card>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Investigation priority" className="xl:col-span-1">
          <p className="text-5xl font-extrabold tabular-nums text-ink">
            {formatScore(priority.score)}
          </p>
          <p className="mt-1 font-mono text-[11px] text-slate-500">
            {priority.formula} (v{priority.formula_version})
          </p>
          <div className="mt-4 space-y-3">
            <ScoreBar label="Network influence (PageRank) × 0.35" value={priority.components?.pagerank} display={formatScore(priority.components?.pagerank)} />
            <ScoreBar label="Bridge role (Betweenness) × 0.35" value={priority.components?.betweenness} display={formatScore(priority.components?.betweenness)} barClass="bg-sky-500" />
            <ScoreBar label="Unusual-pattern flag (Anomaly) × 0.30" value={priority.components?.anomaly_score} display={formatScore(priority.components?.anomaly_score)} barClass="bg-amber-500" />
          </div>
          {report.explanations?.length ? (
            <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-slate-700">
              {report.explanations.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}
        </Card>

        <Card title="Primary entity & graph context" className="xl:col-span-2">
          <p className="text-xl">
            <NameId name={report.entity?.name} id={report.entity?.id} />
          </p>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div className="rounded-xl bg-slate-50 p-3">
              <dt className="text-xs text-slate-500">Degree</dt>
              <dd className="font-mono font-bold">{metrics.degree ?? "—"}</dd>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <dt className="text-xs text-slate-500">Community</dt>
              <dd className="font-mono font-bold">{metrics.community_id ?? "—"}</dd>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <dt className="text-xs text-slate-500">Relationships</dt>
              <dd className="font-mono font-bold">{report.key_relationships?.length ?? 0}</dd>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <dt className="text-xs text-slate-500">Anomaly</dt>
              <dd className="mt-1">
                <SeverityBadge severity={anomaly.severity} score={formatScore(anomaly.anomaly_score)} />
              </dd>
            </div>
          </dl>
          {anomaly.reasons?.length ? (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-700">
              {anomaly.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}
          <div className="mt-4">
            {graph ? <NetworkGraph nodes={graph.nodes} edges={graph.edges} height={320} /> : null}
          </div>
        </Card>
      </div>

      {report.key_relationships?.length ? (
        <Card title="Key relationships">
          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-xs text-slate-700">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="py-2 pr-3">Edge</th>
                  <th className="py-2 pr-3">Source</th>
                  <th className="py-2 pr-3">Target</th>
                  <th className="py-2">Type</th>
                </tr>
              </thead>
              <tbody>
                {report.key_relationships.map((edge) => (
                  <tr key={edge.id} className="border-b border-slate-100">
                    <td className="py-1.5 pr-3">{edge.id}</td>
                    <td className="py-1.5 pr-3">{edge.source}</td>
                    <td className="py-1.5 pr-3">{edge.target}</td>
                    <td className="py-1.5">{edge.type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Timeline">
          <Timeline events={timeline?.events || report.timeline} />
        </Card>
        <Card title="Evidence & provenance">
          {audit ? (
            <p className={`rounded-xl p-3 font-mono text-xs ${audit.verified ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"}`}>
              Audit chain: {audit.verified ? `verified (${audit.count} events)` : `BROKEN at ${audit.broken_at}`}
              {audit.head_hash ? ` · head ${audit.head_hash.slice(0, 12)}…` : ""}
            </p>
          ) : null}
          {report.sources?.length ? (
            <ul className="space-y-1.5">
              {report.sources.map((source, index) => (
                <li key={`${source.document_id}-${index}`} className="rounded-lg bg-slate-50 px-3 py-1.5 font-mono text-xs text-slate-700">
                  {source.document_id}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">No source references recorded.</p>
          )}
        </Card>
      </div>
    </div>
  );
}
