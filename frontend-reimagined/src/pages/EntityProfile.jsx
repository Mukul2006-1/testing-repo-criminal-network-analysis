import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, api } from "../services/api.js";
import { isValidId } from "../utils/validate.js";
import Card from "../components/Card.jsx";
import EntityCard from "../components/EntityCard.jsx";
import NameId from "../components/NameId.jsx";
import NetworkGraph from "../components/NetworkGraph.jsx";
import Timeline from "../components/Timeline.jsx";

export default function EntityProfile() {
  const { id } = useParams();
  const [entity, setEntity] = useState(null);
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
      api.entity(id),
      api.graph(id, { depth: 1 }).catch(() => null),
      api.timeline(id, { page_size: 50 }).catch(() => null),
    ])
      .then(([detail, neighborhood, events]) => {
        setEntity(detail);
        setGraph(neighborhood);
        setTimeline(events);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Load failed."))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p className="text-sm text-slate-500">Loading entity…</p>;
  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!entity) return <p className="text-sm text-slate-500">Entity not found.</p>;

  return (
    <div className="space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-400">
          ARGUS Node // Dossier
        </p>
        <h1 className="text-3xl font-extrabold text-ink">Entity profile</h1>
        {entity ? (
          <p className="mt-1 text-lg">
            <NameId name={entity.name} id={entity.id} />
          </p>
        ) : null}
      </div>

      <EntityCard entity={entity} />

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Provenance">
          {entity.source_refs?.length ? (
            <ul className="space-y-1.5 text-sm text-slate-700">
              {entity.source_refs.map((ref, index) => (
                <li key={`${ref.document_id}-${index}`} className="rounded-lg bg-slate-50 px-3 py-1.5 font-mono text-xs">
                  {ref.document_id}
                  {ref.confidence != null ? ` (confidence ${ref.confidence})` : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">No source references recorded.</p>
          )}
        </Card>
        <Card title="Immediate graph">
          {graph ? <NetworkGraph nodes={graph.nodes} edges={graph.edges} height={320} /> : (
            <p className="text-sm text-slate-500">Graph unavailable.</p>
          )}
        </Card>
      </div>

      <Card title="Timeline">
        <Timeline events={timeline?.events} />
      </Card>
    </div>
  );
}
