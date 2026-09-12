import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../services/api.js";
import AnomalyCard from "../components/AnomalyCard.jsx";
import Term from "../components/Glossary.jsx";

const SEVERITIES = ["", "CRITICAL", "HIGH", "MEDIUM", "LOW"];

export default function Anomalies() {
  const [severity, setSeverity] = useState("");
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.anomalies({
        page: 1,
        page_size: 50,
        ...(severity ? { severity } : {}),
      });
      setItems(data.items || []);
      setTotal(data.pagination?.total ?? 0);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Load failed.");
    } finally {
      setLoading(false);
    }
  }, [severity]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-400">
            ARGUS Node // Signals
          </p>
          <h1 className="text-3xl font-extrabold text-ink">Anomaly dashboard</h1>
          <p className="text-sm text-slate-500">
            <Term k="anomaly" /> instances for triage — not evidence of guilt. Showing{" "}
            {items.length} of {total}. <Term k="severity" /> filters the list.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {SEVERITIES.map((level) => (
          <button
            key={level || "ALL"}
            type="button"
            onClick={() => setSeverity(level)}
            className={`rounded-full px-4 py-1.5 text-xs font-bold transition-colors ${
              severity === level
                ? "bg-argus-600 text-white shadow-card"
                : "border border-slate-200 bg-white text-slate-600 hover:border-argus-300"
            }`}
          >
            {level || "All"}
          </button>
        ))}
      </div>

      {loading ? <p className="text-sm text-slate-500">Loading anomalies…</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {!loading && !error && items.length === 0 ? (
        <p className="text-sm text-slate-500">No anomalies found. Run analytics after ingesting data.</p>
      ) : null}
      <div className="grid gap-4 xl:grid-cols-2">
        {items.map((item) => (
          <AnomalyCard key={item.entity_id} item={item} />
        ))}
      </div>
    </div>
  );
}
