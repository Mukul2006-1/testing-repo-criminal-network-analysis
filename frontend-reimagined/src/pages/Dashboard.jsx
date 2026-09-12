import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../services/api.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { useLang, T } from "../i18n/LangContext.jsx";
import { STRINGS } from "../i18n/strings.js";
import { formatScore } from "../utils/validate.js";
import Card from "../components/Card.jsx";
import StatCard from "../components/StatCard.jsx";
import Term from "../components/Glossary.jsx";

const TERMINAL = new Set(["SUCCEEDED", "PARTIAL", "FAILED"]);

function Stage({ label, state }) {
  const tone =
    state === "SUCCEEDED" || state === "done"
      ? "bg-green-100 text-green-800"
      : state === "FAILED"
        ? "bg-red-100 text-red-800"
        : state === "PARTIAL"
          ? "bg-amber-100 text-amber-800"
          : state === "running"
            ? "bg-argus-100 text-argus-700"
            : "bg-slate-100 text-slate-500";
  return (
    <span className={`rounded-full px-2.5 py-0.5 font-mono text-xs font-semibold ${tone}`}>
      {label}: {state || "pending"}
    </span>
  );
}

export default function Dashboard() {
  const { canRunAnalytics } = useAuth();
  const { t } = useLang();
  const [stats, setStats] = useState(null);
  const [statsError, setStatsError] = useState("");
  const [loading, setLoading] = useState(true);
  const [file, setFile] = useState(null);
  const [datasetType, setDatasetType] = useState("FIR");
  const [stages, setStages] = useState({});
  const [pipelineError, setPipelineError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [receipt, setReceipt] = useState("");
  const [refreshError, setRefreshError] = useState("");

  const loadStats = useCallback(async () => {
    setLoading(true);
    setStatsError("");
    try {
      const [entities, anomalies, pagerank, communities, degree] = await Promise.all([
        api.entities({ page: 1, page_size: 1 }),
        api.anomalies({ page: 1, page_size: 1 }),
        api.pagerank({ page: 1, page_size: 5 }).catch(() => ({ items: [], pagination: { total: 0 } })),
        api.communities({ page: 1, page_size: 100 }).catch(() => ({ items: [] })),
        api.degree({ page: 1, page_size: 100 }).catch(() => ({ items: [] })),
      ]);
      const relationshipCount = degree.items
        ? Math.round(degree.items.reduce((sum, row) => sum + (row.degree || 0), 0) / 2)
        : null;
      setStats({
        entities: entities.pagination?.total ?? 0,
        relationships: relationshipCount,
        anomalies: anomalies.pagination?.total ?? 0,
        communities: new Set((communities.items || []).map((row) => row.community_id)).size,
        top: pagerank.items || [],
      });
    } catch (error) {
      setStatsError(error instanceof ApiError ? error.message : "Failed to load dashboard.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  async function pollJob(jobId) {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const job = await api.job(jobId);
      const status = job.status || job.result?.status;
      if (status && TERMINAL.has(status)) return job;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    throw new ApiError(0, "TIMEOUT", "Processing did not finish in time.");
  }

  async function runPipeline(event) {
    event.preventDefault();
    if (!file) {
      setPipelineError("Choose a file first.");
      return;
    }
    setBusy(true);
    setPipelineError("");
    setStages({ upload: "running" });
    try {
      const upload = await api.upload(file, datasetType);
      setStages({ upload: "done", process: "running" });
      const proc = await api.process(upload.upload_id);
      const job = await pollJob(proc.job_id);
      const finalStatus = job.status || job.result?.status;
      setStages((prev) => ({ ...prev, process: finalStatus }));
      if (finalStatus !== "SUCCEEDED" && finalStatus !== "PARTIAL") {
        throw new ApiError(0, "PROCESS_FAILED", `Processing ended as ${finalStatus}.`);
      }
      setStages((prev) => ({ ...prev, build: "running" }));
      const build = await api.buildGraph(upload.upload_id);
      setStages((prev) => ({ ...prev, build: build.status }));
      if (build.status !== "SUCCEEDED") {
        throw new ApiError(0, "BUILD_FAILED", "Graph build did not succeed.");
      }
      setStages((prev) => ({ ...prev, analytics: "running" }));
      await api.runAnalytics(upload.upload_id);
      setStages((prev) => ({ ...prev, analytics: "done" }));
      await loadStats();
    } catch (error) {
      setStages((prev) => ({ ...prev, failed: true }));
      setPipelineError(error instanceof ApiError ? error.message : "Pipeline failed.");
    } finally {
      setBusy(false);
    }
  }

  async function refreshScores() {
    setRefreshing(true);
    setRefreshError("");
    setReceipt("");
    try {
      const summary = await api.runAnalytics();
      const when = new Date().toLocaleString();
      setReceipt(
        `Scores refreshed ${when} — run ${(summary.run_id || "").slice(0, 8)} ` +
        `scored ${summary.entities_scored ?? "?"} entities.`
      );
      await loadStats();
    } catch (error) {
      setRefreshError(error instanceof ApiError ? error.message : "Refresh failed.");
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-400">
            ARGUS Node // Overview
          </p>
          <h1 className="text-3xl font-extrabold text-ink"><T k="overview_title" /></h1>
          <p className="text-sm text-slate-500">
            <T k="overview_sub" /> <Term k="priority" /> orders
            what to review first — hover any underlined term for its meaning.
          </p>
        </div>
        {canRunAnalytics ? (
          <div className="text-right">
            <button
              className="rounded-xl border border-argus-300 bg-white px-4 py-2 text-sm font-bold text-argus-700 shadow-card hover:border-argus-500 disabled:opacity-50"
              type="button"
              onClick={refreshScores}
              disabled={refreshing || busy}
              title="Re-score every processed upload from the current graph"
            >
              {refreshing ? t(STRINGS.refreshing) : t(STRINGS.refresh_scores)}
            </button>
            {receipt ? <p className="mt-1 text-xs text-green-700">{receipt}</p> : null}
            {refreshError ? <p className="mt-1 text-xs text-red-600">{refreshError}</p> : null}
          </div>
        ) : null}
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Loading dashboard…</p>
      ) : statsError ? (
        <p className="text-sm text-red-600">{statsError}</p>
      ) : stats ? (
        <>
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            <StatCard icon="database" label={t(STRINGS.kpi_entities)} value={stats.entities} />
            <StatCard
              icon="share"
              label={t(STRINGS.kpi_relationships)}
              value={stats.relationships ?? "—"}
              sub={t(STRINGS.needs_analytics)}
              tone="bg-sky-50 text-sky-600"
            />
            <StatCard
              icon="warning"
              label={t(STRINGS.kpi_anomalies)}
              value={stats.anomalies}
              tone="bg-red-50 text-red-500"
            />
            <StatCard
              icon="groups"
              label={t(STRINGS.kpi_communities)}
              value={stats.communities}
              tone="bg-emerald-50 text-emerald-600"
            />
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <Card title={t(STRINGS.top_entities)}>
              {stats.top.length === 0 ? (
                <p className="text-sm text-slate-500">No analytics yet — run the pipeline below.</p>
              ) : (
                <ul className="divide-y divide-slate-100 text-sm">
                  {stats.top.map((row) => (
                    <li key={row.entity_id} className="flex items-center justify-between py-2">
                      <Link
                        className="font-mono text-[13px] font-bold text-argus-700 hover:underline"
                        to={`/investigation/${encodeURIComponent(row.entity_id)}`}
                      >
                        {row.entity_id}
                      </Link>
                      <span className="font-mono text-xs text-slate-500">
                        pagerank {formatScore(row.pagerank)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title={t(STRINGS.ingest_title)}>
              <p className="text-xs text-slate-500">Upload → process → graph → analytics</p>
              <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={runPipeline}>
                <label className="text-sm">
                  <span className="font-semibold text-slate-600"><T k="file_label" /></span>
                  <input
                    className="mt-1 block text-sm"
                    type="file"
                    accept=".csv,.json,.txt"
                    onChange={(event) => setFile(event.target.files?.[0] || null)}
                  />
                </label>
                <label className="text-sm">
                  <span className="font-semibold text-slate-600"><T k="dataset_label" /></span>
                  <select
                    className="mt-1 block rounded-xl border border-slate-300 bg-white px-2 py-2"
                    value={datasetType}
                    onChange={(event) => setDatasetType(event.target.value)}
                  >
                    {["FIR", "CDR", "TRANSACTION", "VEHICLE", "LOCATION"].map((type) => (
                      <option key={type} value={type}>{type}</option>
                    ))}
                  </select>
                </label>
                <button
                  className="rounded-xl bg-argus-600 px-4 py-2 text-sm font-bold text-white hover:bg-argus-700 disabled:opacity-50"
                  type="submit"
                  disabled={busy}
                >
                  {busy ? t(STRINGS.running) : t(STRINGS.upload_process)}
                </button>
              </form>
              <div className="mt-3 flex flex-wrap gap-2">
                <Stage label="upload" state={stages.upload} />
                <Stage label="process" state={stages.process} />
                <Stage label="graph" state={stages.build} />
                <Stage label="analytics" state={stages.analytics} />
              </div>
              {pipelineError ? <p className="mt-2 text-sm text-red-600">{pipelineError}</p> : null}
            </Card>
          </div>
        </>
      ) : null}
    </div>
  );
}
