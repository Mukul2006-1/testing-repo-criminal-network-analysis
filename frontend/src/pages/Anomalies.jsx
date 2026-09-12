import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../services/api.js";
import AnomalyCard from "../components/AnomalyCard.jsx";

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
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Anomaly dashboard</h1>
        <label className="text-sm text-gray-600">
          Severity{" "}
          <select
            className="rounded border border-gray-300 px-2 py-1.5"
            value={severity}
            onChange={(event) => setSeverity(event.target.value)}
          >
            <option value="">All</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>
        </label>
      </div>
      <p className="text-sm text-gray-500">
        Behavioral signals for triage — not evidence of guilt. Showing {items.length} of {total}.
      </p>
      {loading ? <p className="text-sm text-gray-500">Loading anomalies…</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {!loading && !error && items.length === 0 ? (
        <p className="text-sm text-gray-500">No anomalies found. Run analytics after ingesting data.</p>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2">
        {items.map((item) => (
          <AnomalyCard key={item.entity_id} item={item} />
        ))}
      </div>
    </div>
  );
}
