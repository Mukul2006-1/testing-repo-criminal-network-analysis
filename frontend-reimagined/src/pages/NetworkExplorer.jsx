import { useCallback, useState } from "react";
import { ApiError, api } from "../services/api.js";
import { isValidId } from "../utils/validate.js";
import Card from "../components/Card.jsx";
import EntityCard from "../components/EntityCard.jsx";
import NetworkGraph from "../components/NetworkGraph.jsx";

const ENTITY_TYPES = ["PERSON", "PHONE", "LOCATION", "VEHICLE", "ORGANIZATION", "ACCOUNT"];

export default function NetworkExplorer() {
  const [entityId, setEntityId] = useState("");
  const [depth, setDepth] = useState(1);
  const [relTypes, setRelTypes] = useState("");
  const [graph, setGraph] = useState(null);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const explore = useCallback(
    async (id, overrideDepth) => {
      if (!isValidId(id)) {
        setError("Enter a valid entity ID (letters, digits, _ and -).");
        return;
      }
      setLoading(true);
      setError("");
      try {
        const params = { depth: overrideDepth ?? depth, limit_nodes: 100, limit_edges: 300 };
        if (relTypes.trim()) params.rel_types = relTypes.trim();
        const data = await api.graph(id, params);
        setGraph(data);
        setSelected(null);
        setDetail(null);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Graph load failed.");
        setGraph(null);
      } finally {
        setLoading(false);
      }
    },
    [depth, relTypes]
  );

  async function selectNode(id) {
    setSelected(id);
    try {
      setDetail(await api.entity(id));
    } catch {
      setDetail(null);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-400">
          ARGUS Node // Graph
        </p>
        <h1 className="text-3xl font-extrabold text-ink">Network Explorer</h1>
      </div>

      <Card title="Graph constraints">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            explore(entityId.trim());
          }}
        >
          <label className="text-sm">
            <span className="font-semibold text-slate-600">Entity ID</span>
            <input
              className="mt-1 block w-56 rounded-xl border border-slate-300 px-3 py-2 font-mono text-sm focus:border-argus-500 focus:outline-none"
              value={entityId}
              onChange={(event) => setEntityId(event.target.value)}
              placeholder="person_001"
            />
          </label>
          <label className="text-sm">
            <span className="font-semibold text-slate-600">Depth (1–3)</span>
            <input
              className="mt-1 block w-20 rounded-xl border border-slate-300 px-3 py-2 text-sm"
              type="number"
              min={1}
              max={3}
              value={depth}
              onChange={(event) => setDepth(Number(event.target.value))}
            />
          </label>
          <label className="text-sm">
            <span className="font-semibold text-slate-600">Relationship types (optional)</span>
            <input
              className="mt-1 block w-60 rounded-xl border border-slate-300 px-3 py-2 font-mono text-sm"
              value={relTypes}
              onChange={(event) => setRelTypes(event.target.value)}
              placeholder="CALLED,MENTIONED_IN"
            />
          </label>
          <button
            className="rounded-xl bg-argus-600 px-4 py-2 text-sm font-bold text-white hover:bg-argus-700 disabled:opacity-50"
            type="submit"
            disabled={loading}
          >
            {loading ? "Loading…" : "Explore"}
          </button>
        </form>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {ENTITY_TYPES.map((type) => (
            <span key={type} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-bold text-slate-600">
              {type}
            </span>
          ))}
        </div>
        {error ? <p className="mt-2 text-sm text-red-600">{error}</p> : null}
      </Card>

      {graph ? (
        <div className="grid gap-4 xl:grid-cols-3">
          <Card title="Entity graph" className="xl:col-span-2">
            <NetworkGraph nodes={graph.nodes} edges={graph.edges} onSelect={selectNode} />
            {graph.truncated ? (
              <p className="mt-2 text-xs text-amber-700">Results truncated — narrow depth or filters.</p>
            ) : null}
          </Card>
          <div>
            <Card title="Inspector">
              {selected ? (
                <>
                  <button
                    className="mb-3 w-full rounded-xl bg-argus-600 px-3 py-2 font-mono text-xs font-bold text-white hover:bg-argus-700"
                    type="button"
                    onClick={() => {
                      setEntityId(selected);
                      explore(selected);
                    }}
                  >
                    Center on {selected}
                  </button>
                  {detail ? <EntityCard entity={detail} /> : <p className="text-sm text-slate-500">Loading details…</p>}
                </>
              ) : (
                <p className="text-sm text-slate-500">Select a node to inspect it.</p>
              )}
            </Card>
          </div>
        </div>
      ) : null}
    </div>
  );
}
