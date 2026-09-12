import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, api } from "../services/api.js";
import { formatScore, isValidId, severityTone } from "../utils/validate.js";
import NetworkGraph from "../components/NetworkGraph.jsx";
import Timeline from "../components/Timeline.jsx";

export default function Investigation() {
  const { id } = useParams();
  const [report, setReport] = useState(null);
  const [graph, setGraph] = useState(null);
  const [timeline, setTimeline] = useState(null);
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
    ])
      .then(([data, neighborhood, events]) => {
        setReport(data);
        setGraph(neighborhood);
        setTimeline(events);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Load failed."))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p className="text-sm text-gray-500">Loading investigation…</p>;
  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!report) return <p className="text-sm text-gray-500">No investigation found.</p>;

  const priority = report.priority || {};
  const anomaly = report.anomaly || {};
  const metrics = report.graph_metrics || {};

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Investigation report</h1>
        <button
          className="no-print rounded border border-gray-300 px-3 py-1.5 text-sm"
          type="button"
          onClick={() => window.print()}
        >
          Print report
        </button>
      </div>

      <section className="rounded border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
        Flagged for investigation — requires investigator review. Scores below are triage
        signals, not findings of guilt or proof of criminal activity.
      </section>

      <section className="rounded border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="font-medium text-gray-900">Primary entity</h2>
        <p className="mt-1 text-lg font-semibold">{report.entity?.name}</p>
        <p className="font-mono text-xs text-gray-500">
          {report.entity?.id} · {report.entity?.type}
        </p>
      </section>

      <section className="rounded border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="font-medium text-gray-900">Investigation Priority</h2>
        <p className="mt-1 text-3xl font-bold">{formatScore(priority.score)}</p>
        <p className="mt-1 font-mono text-xs text-gray-500">{priority.formula} (v{priority.formula_version})</p>
        <dl className="mt-2 grid grid-cols-3 gap-2 text-sm">
          <div><dt className="text-gray-500">PageRank</dt><dd className="font-medium">{formatScore(priority.components?.pagerank)}</dd></div>
          <div><dt className="text-gray-500">Betweenness</dt><dd className="font-medium">{formatScore(priority.components?.betweenness)}</dd></div>
          <div><dt className="text-gray-500">Anomaly</dt><dd className="font-medium">{formatScore(priority.components?.anomaly_score)}</dd></div>
        </dl>
        {report.explanations?.length ? (
          <ul className="mt-3 list-disc pl-5 text-sm text-gray-700">
            {report.explanations.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="rounded border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="font-medium text-gray-900">Graph context</h2>
        <dl className="mt-2 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          <div><dt className="text-gray-500">Degree</dt><dd className="font-medium">{metrics.degree ?? "—"}</dd></div>
          <div><dt className="text-gray-500">Community</dt><dd className="font-medium">{metrics.community_id ?? "—"}</dd></div>
          <div>
            <dt className="text-gray-500">Anomaly</dt>
            <dd>
              <span className={`rounded border px-2 py-0.5 text-xs font-semibold ${severityTone(anomaly.severity)}`}>
                {anomaly.severity || "LOW"} · {formatScore(anomaly.anomaly_score)}
              </span>
            </dd>
          </div>
          <div><dt className="text-gray-500">Relationships</dt><dd className="font-medium">{report.key_relationships?.length ?? 0}</dd></div>
        </dl>
        {anomaly.reasons?.length ? (
          <ul className="mt-2 list-disc pl-5 text-sm text-gray-700">
            {anomaly.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : null}
        <div className="mt-3">
          {graph ? <NetworkGraph nodes={graph.nodes} edges={graph.edges} height={360} /> : null}
        </div>
        {report.key_relationships?.length ? (
          <table className="mt-3 w-full text-left text-xs text-gray-700">
            <thead>
              <tr className="border-b">
                <th className="py-1 pr-2">Edge</th>
                <th className="py-1 pr-2">Source</th>
                <th className="py-1 pr-2">Target</th>
                <th className="py-1">Type</th>
              </tr>
            </thead>
            <tbody>
              {report.key_relationships.map((edge) => (
                <tr key={edge.id} className="border-b font-mono">
                  <td className="py-1 pr-2">{edge.id}</td>
                  <td className="py-1 pr-2">{edge.source}</td>
                  <td className="py-1 pr-2">{edge.target}</td>
                  <td className="py-1">{edge.type}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </section>

      <section className="rounded border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="font-medium text-gray-900">Timeline</h2>
        <div className="mt-2">
          <Timeline events={timeline?.events || report.timeline} />
        </div>
      </section>

      <section className="rounded border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="font-medium text-gray-900">Evidence &amp; provenance</h2>
        {report.sources?.length ? (
          <ul className="mt-2 list-disc pl-5 font-mono text-xs text-gray-700">
            {report.sources.map((source, index) => (
              <li key={`${source.document_id}-${index}`}>{source.document_id}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-gray-500">No source references recorded.</p>
        )}
      </section>
    </div>
  );
}
