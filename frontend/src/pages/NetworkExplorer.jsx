import { useCallback, useState } from "react";
import { ApiError, api } from "../services/api.js";
import { isValidId } from "../utils/validate.js";
import EntityCard from "../components/EntityCard.jsx";
import NetworkGraph from "../components/NetworkGraph.jsx";

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
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-gray-900">Network Explorer</h1>
      <form
        className="flex flex-wrap items-end gap-3 rounded border border-gray-200 bg-white p-4 shadow-sm"
        onSubmit={(event) => {
          event.preventDefault();
          explore(entityId.trim());
        }}
      >
        <label className="text-sm">
          <span className="text-gray-600">Entity ID</span>
          <input
            className="mt-1 block w-64 rounded border border-gray-300 px-3 py-2 font-mono"
            value={entityId}
            onChange={(event) => setEntityId(event.target.value)}
            placeholder="person_001"
          />
        </label>
        <label className="text-sm">
          <span className="text-gray-600">Depth (1–3)</span>
          <input
            className="mt-1 block w-20 rounded border border-gray-300 px-3 py-2"
            type="number"
            min={1}
            max={3}
            value={depth}
            onChange={(event) => setDepth(Number(event.target.value))}
          />
        </label>
        <label className="text-sm">
          <span className="text-gray-600">Relationship types (optional, comma list)</span>
          <input
            className="mt-1 block w-64 rounded border border-gray-300 px-3 py-2 font-mono"
            value={relTypes}
            onChange={(event) => setRelTypes(event.target.value)}
            placeholder="CALLED,MENTIONED_IN"
          />
        </label>
        <button
          className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          type="submit"
          disabled={loading}
        >
          {loading ? "Loading…" : "Explore"}
        </button>
      </form>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {graph ? (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <NetworkGraph nodes={graph.nodes} edges={graph.edges} onSelect={selectNode} />
            {graph.truncated ? (
              <p className="mt-1 text-xs text-amber-700">Results truncated — narrow depth or filters.</p>
            ) : null}
          </div>
          <div>
            {selected ? (
              <>
                <div className="mb-2 flex gap-2">
                  <button
                    className="rounded border border-gray-300 px-3 py-1.5 text-sm"
                    type="button"
                    onClick={() => {
                      setEntityId(selected);
                      explore(selected);
                    }}
                  >
                    Center on {selected}
                  </button>
                </div>
                {detail ? <EntityCard entity={detail} /> : <p className="text-sm text-gray-500">Loading details…</p>}
              </>
            ) : (
              <p className="text-sm text-gray-500">Select a node to inspect it.</p>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
