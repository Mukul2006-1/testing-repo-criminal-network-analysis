import { useState } from "react";
import { ApiError, api } from "../services/api.js";
import { isValidId } from "../utils/validate.js";
import Card from "../components/Card.jsx";
import NameId from "../components/NameId.jsx";
import { TypeBadge } from "../components/Badges.jsx";
import NetworkGraph from "../components/NetworkGraph.jsx";

const MAX_IDS = 4;

export default function Compare() {
  const [inputs, setInputs] = useState(["", ""]);
  const [depth, setDepth] = useState(1);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function setInput(index, value) {
    setInputs((prev) => prev.map((v, i) => (i === index ? value : v)));
  }

  async function compare(event) {
    event.preventDefault();
    const ids = inputs.map((v) => v.trim()).filter(Boolean);
    const unique = [...new Set(ids)];
    if (unique.length < 2) {
      setError("Enter at least two different entity IDs.");
      return;
    }
    const bad = unique.find((id) => !isValidId(id));
    if (bad) {
      setError(`Invalid entity ID "${bad}" (letters, digits, _ and - only).`);
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const graphs = await Promise.all(
        unique.map((id) =>
          api.graph(id, { depth, limit_nodes: 100, limit_edges: 300 })
        )
      );
      const details = await Promise.all(
        unique.map((id) => api.entity(id).catch(() => null))
      );
      const idSet = new Set(unique);

      // Union of nodes/edges for the combined view.
      const nodeMap = new Map();
      const edgeMap = new Map();
      graphs.forEach((g) => {
        for (const n of g.nodes || []) if (!nodeMap.has(n.id)) nodeMap.set(n.id, n);
        for (const e of g.edges || []) {
          const key = e.id || `${e.source}-${e.type}-${e.target}`;
          if (!edgeMap.has(key)) edgeMap.set(key, e);
        }
      });

      // Direct edges with both ends in the queried set.
      const direct = [...edgeMap.values()].filter(
        (e) => idSet.has(e.source) && idSet.has(e.target)
      );

      // Shared contacts: non-queried nodes adjacent to 2+ queried ids.
      const adjacency = new Map(); // nodeId -> Set(queryId)
      graphs.forEach((g, gi) => {
        const qid = unique[gi];
        for (const e of g.edges || []) {
          const contact = e.source === qid ? e.target : e.target === qid ? e.source : null;
          if (!contact || idSet.has(contact)) continue;
          if (!adjacency.has(contact)) adjacency.set(contact, new Set());
          adjacency.get(contact).add(qid);
        }
      });
      const shared = [...adjacency.entries()]
        .filter(([, owners]) => owners.size >= 2)
        .map(([contactId, owners]) => ({
          node: nodeMap.get(contactId),
          owners: [...owners],
        }))
        .sort((a, b) => b.owners.length - a.owners.length);

      setResult({
        ids: unique,
        details,
        direct,
        shared,
        nodes: [...nodeMap.values()],
        edges: [...edgeMap.values()],
        truncated: graphs.some((g) => g.truncated),
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Comparison failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-400">
          ARGUS Node // Link check
        </p>
        <h1 className="text-3xl font-extrabold text-ink">Relationship check</h1>
        <p className="text-sm text-slate-500">
          Direct links and shared contacts between two or more entities. Leads for
          investigation — not findings.
        </p>
      </div>

      <Card title="Entities to compare">
        <form onSubmit={compare} className="flex flex-wrap items-end gap-3">
          {inputs.map((value, i) => (
            <label key={i} className="text-sm">
              <span className="font-semibold text-slate-600">
                {i === 0 ? "First entity" : i === 1 ? "Second entity" : `Entity ${i + 1} (optional)`}
              </span>
              <input
                className="mt-1 block w-52 rounded-xl border border-slate-300 px-3 py-2 font-mono text-sm focus:border-argus-500 focus:outline-none"
                value={value}
                onChange={(e) => setInput(i, e.target.value)}
                placeholder="person_001"
              />
            </label>
          ))}
          <label className="text-sm">
            <span className="font-semibold text-slate-600">Depth</span>
            <select
              className="mt-1 block rounded-xl border border-slate-300 bg-white px-2 py-2"
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
            >
              <option value={1}>1 hop</option>
              <option value={2}>2 hops</option>
            </select>
          </label>
          {inputs.length < MAX_IDS ? (
            <button
              type="button"
              className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-bold text-slate-600"
              onClick={() => setInputs((prev) => [...prev, ""])}
            >
              + Add
            </button>
          ) : null}
          <button
            type="submit"
            disabled={loading}
            className="rounded-xl bg-argus-600 px-4 py-2 text-sm font-bold text-white hover:bg-argus-700 disabled:opacity-50"
          >
            {loading ? "Checking…" : "Check relationship"}
          </button>
        </form>
        {error ? <p className="mt-2 text-sm text-red-600">{error}</p> : null}
      </Card>

      {result ? (
        <>
          <div className="grid gap-4 xl:grid-cols-2">
            <Card title="Verdict">
              {result.direct.length === 0 && result.shared.length === 0 ? (
                <p className="text-sm text-slate-600">
                  No direct link and no shared contacts within {depth} hop
                  {depth > 1 ? "s" : ""}. They may still connect through longer
                  paths — try depth 2 or explore each profile.
                </p>
              ) : (
                <div className="space-y-3 text-sm">
                  {result.direct.length > 0 ? (
                    <div>
                      <p className="font-bold text-ink">
                        Directly linked ({result.direct.length})
                      </p>
                      <ul className="mt-1 space-y-1">
                        {result.direct.map((e, i) => (
                          <li key={e.id || i} className="font-mono text-xs text-slate-700">
                            {e.source} —[{e.type}]→ {e.target}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {result.shared.length > 0 ? (
                    <div>
                      <p className="font-bold text-ink">
                        Shared contacts ({result.shared.length})
                      </p>
                      <ul className="mt-1 space-y-1.5">
                        {result.shared.slice(0, 20).map(({ node, owners }) => (
                          <li key={node?.id} className="flex flex-wrap items-center gap-2 text-xs">
                            <NameId name={node?.label} id={node?.id} />
                            <TypeBadge type={node?.type} />
                            <span className="text-slate-500">
                              connects {owners.join(", ")}
                            </span>
                          </li>
                        ))}
                      </ul>
                      {result.shared.length > 20 ? (
                        <p className="mt-1 text-xs text-slate-500">
                          +{result.shared.length - 20} more — see the graph.
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              )}
            </Card>
            <Card title="Checked entities">
              <ul className="space-y-2 text-sm">
                {result.ids.map((id, i) => {
                  const d = result.details[i];
                  return (
                    <li key={id} className="rounded-xl bg-slate-50 px-3 py-2">
                      <NameId name={d?.name} id={id} />
                      {d ? (
                        <span className="ml-2">
                          <TypeBadge type={d.type} />
                        </span>
                      ) : (
                        <span className="ml-2 text-xs text-red-600">not found</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </Card>
          </div>
          <Card title="Combined graph">
            <NetworkGraph
              nodes={result.nodes}
              edges={result.edges}
              height={440}
              highlightIds={result.ids}
            />
            {result.truncated ? (
              <p className="mt-2 text-xs text-amber-700">
                Results truncated — narrow depth for a cleaner view.
              </p>
            ) : null}
          </Card>
        </>
      ) : null}
    </div>
  );
}
