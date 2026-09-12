import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../services/api.js";
import { formatScore } from "../utils/validate.js";
import { countByType, filterEntities, mergeScores, paginateRows, sortEntities } from "../utils/atlas.js";
import Card from "../components/Card.jsx";
import NameId from "../components/NameId.jsx";
import { SeverityBadge, TypeBadge } from "../components/Badges.jsx";

const PAGE_SIZE = 20;
const TYPES = ["", "PERSON", "PHONE", "LOCATION", "VEHICLE", "ORGANIZATION", "ACCOUNT", "DATE"];

async function fetchAllEntities() {
  const all = [];
  let page = 1;
  for (;;) {
    const data = await api.entities({ page, page_size: 100 });
    const items = data.items || [];
    all.push(...items);
    const total = data.pagination?.total ?? all.length;
    if (all.length >= total || items.length === 0 || page >= 50) break;
    page += 1;
  }
  return all;
}

export default function Atlas() {
  const [entities, setEntities] = useState([]);
  const [scores, setScores] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [sortKey, setSortKey] = useState("pagerank");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchAllEntities(),
      api.pagerank({ page: 1, page_size: 100 }).catch(() => ({ items: [] })),
      api.anomalies({ page: 1, page_size: 100 }).catch(() => ({ items: [] })),
    ])
      .then(([ents, pr, an]) => {
        setEntities(ents);
        setScores(pr.items || []);
        const sev = new Map((an.items || []).map((a) => [a.entity_id, a]));
        setAnomalies(sev);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Load failed."))
      .finally(() => setLoading(false));
  }, []);

  const counts = useMemo(() => countByType(entities), [entities]);
  const rows = useMemo(() => {
    const merged = mergeScores(entities, scores);
    const withFlags = merged.map((row) => ({ ...row, anomaly: anomalies.get(row.id) || null }));
    return paginateRows(sortEntities(filterEntities(withFlags, query, typeFilter), sortKey), page, PAGE_SIZE);
  }, [entities, scores, anomalies, query, typeFilter, sortKey, page]);

  useEffect(() => {
    setPage(1);
  }, [query, typeFilter, sortKey]);

  return (
    <div className="space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-400">
          ARGUS Node // Atlas
        </p>
        <h1 className="text-3xl font-extrabold text-ink">Entity directory</h1>
        <p className="text-sm text-slate-500">
          Every canonical entity in one place — {entities.length} total. Select any row
          for its profile or investigation report.
        </p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {Object.entries(counts).map(([type, count]) => (
          <button
            key={type}
            type="button"
            onClick={() => setTypeFilter((prev) => (prev === type ? "" : type))}
            className={`rounded-full px-3 py-1 text-xs font-bold transition-colors ${
              typeFilter === type
                ? "bg-argus-600 text-white"
                : "border border-slate-200 bg-white text-slate-600 hover:border-argus-300"
            }`}
          >
            {type} · {count}
          </button>
        ))}
      </div>

      <Card title="Browse">
        <div className="mb-3 flex flex-wrap gap-3">
          <input
            className="w-64 rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-argus-500 focus:outline-none"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by name, alias or ID…"
          />
          <select
            className="rounded-xl border border-slate-300 bg-white px-2 py-2 text-sm"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            {TYPES.map((t) => (
              <option key={t} value={t}>{t || "All types"}</option>
            ))}
          </select>
          <select
            className="rounded-xl border border-slate-300 bg-white px-2 py-2 text-sm"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value)}
          >
            <option value="pagerank">Sort: influence</option>
            <option value="name">Sort: name</option>
          </select>
        </div>

        {loading ? <p className="text-sm text-slate-500">Loading directory…</p> : null}
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        {!loading && !error && rows.total === 0 ? (
          <p className="text-sm text-slate-500">No entities match. Ingest data first.</p>
        ) : null}

        {!loading && !error && rows.total > 0 ? (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                    <th className="px-3 py-2">Entity</th>
                    <th className="px-3 py-2">Type</th>
                    <th className="px-3 py-2">Influence</th>
                    <th className="px-3 py-2">Flag</th>
                    <th className="px-3 py-2">Open</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.items.map((row) => (
                    <tr key={row.id} className="border-b border-slate-100 hover:bg-argus-50/50">
                      <td className="px-3 py-2">
                        <NameId name={row.name} id={row.id} />
                        {row.aliases?.length ? (
                          <span className="ml-2 text-xs text-slate-400">
                            aka {row.aliases.slice(0, 2).join(", ")}
                            {row.aliases.length > 2 ? "…" : ""}
                          </span>
                        ) : null}
                      </td>
                      <td className="px-3 py-2"><TypeBadge type={row.type} /></td>
                      <td className="px-3 py-2 font-mono text-xs">
                        {formatScore(row.scores?.pagerank)}
                      </td>
                      <td className="px-3 py-2">
                        {row.anomaly ? (
                          <SeverityBadge severity={row.anomaly.severity} />
                        ) : (
                          <span className="text-xs text-slate-400">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs font-semibold">
                        <Link className="mr-3 text-argus-700 hover:underline" to={`/entities/${encodeURIComponent(row.id)}`}>
                          Profile
                        </Link>
                        <Link className="text-argus-700 hover:underline" to={`/investigation/${encodeURIComponent(row.id)}`}>
                          Report
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-center justify-between text-sm">
              <p className="text-xs text-slate-500">
                Page {rows.page} of {rows.totalPages} · {rows.total} entities
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={rows.page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                  className="rounded-xl border border-slate-300 px-3 py-1.5 text-xs font-bold disabled:opacity-40"
                >
                  ← Prev
                </button>
                <button
                  type="button"
                  disabled={rows.page >= rows.totalPages}
                  onClick={() => setPage((p) => p + 1)}
                  className="rounded-xl border border-slate-300 px-3 py-1.5 text-xs font-bold disabled:opacity-40"
                >
                  Next →
                </button>
              </div>
            </div>
          </>
        ) : null}
      </Card>
    </div>
  );
}
