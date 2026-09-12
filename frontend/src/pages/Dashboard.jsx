import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../services/api.js";
import StatsCard from "../components/StatsCard.jsx";

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
            ? "bg-blue-100 text-blue-800"
            : "bg-gray-100 text-gray-600";
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${tone}`}>
      {label}: {state || "pending"}
    </span>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [statsError, setStatsError] = useState("");
  const [loading, setLoading] = useState(true);
  const [file, setFile] = useState(null);
  const [datasetType, setDatasetType] = useState("FIR");
  const [stages, setStages] = useState({});
  const [pipelineError, setPipelineError] = useState("");
  const [busy, setBusy] = useState(false);

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

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-gray-900">Overview</h1>
      {loading ? (
        <p className="text-sm text-gray-500">Loading dashboard…</p>
      ) : statsError ? (
        <p className="text-sm text-red-600">{statsError}</p>
      ) : stats ? (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatsCard label="Entities" value={stats.entities} />
            <StatsCard label="Relationships (est.)" value={stats.relationships ?? "—"} sub="Requires an analytics run" />
            <StatsCard label="Anomalies" value={stats.anomalies} />
            <StatsCard label="Communities" value={stats.communities} />
          </div>
          <div className="rounded border border-gray-200 bg-white p-4 shadow-sm">
            <h2 className="font-medium text-gray-900">Top structural entities (PageRank)</h2>
            {stats.top.length === 0 ? (
              <p className="mt-2 text-sm text-gray-500">No analytics yet — run the pipeline below.</p>
            ) : (
              <ul className="mt-2 space-y-1 text-sm">
                {stats.top.map((row) => (
                  <li key={row.entity_id}>
                    <Link className="text-blue-700 underline" to={`/investigation/${encodeURIComponent(row.entity_id)}`}>
                      {row.entity_id}
                    </Link>
                    <span className="ml-2 text-gray-500">pagerank {row.pagerank}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      ) : null}

      <div className="rounded border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="font-medium text-gray-900">Ingest evidence (upload → process → graph → analytics)</h2>
        <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={runPipeline}>
          <label className="text-sm">
            <span className="text-gray-600">File (CSV/JSON/TXT)</span>
            <input
              className="mt-1 block text-sm"
              type="file"
              accept=".csv,.json,.txt"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
          </label>
          <label className="text-sm">
            <span className="text-gray-600">Dataset type</span>
            <select
              className="mt-1 block rounded border border-gray-300 px-2 py-1.5"
              value={datasetType}
              onChange={(event) => setDatasetType(event.target.value)}
            >
              {["FIR", "CDR", "TRANSACTION", "VEHICLE", "LOCATION"].map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
          </label>
          <button
            className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            type="submit"
            disabled={busy}
          >
            {busy ? "Running…" : "Upload & process"}
          </button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          <Stage label="upload" state={stages.upload} />
          <Stage label="process" state={stages.process} />
          <Stage label="graph" state={stages.build} />
          <Stage label="analytics" state={stages.analytics} />
        </div>
        {pipelineError ? <p className="mt-2 text-sm text-red-600">{pipelineError}</p> : null}
      </div>
    </div>
  );
}
