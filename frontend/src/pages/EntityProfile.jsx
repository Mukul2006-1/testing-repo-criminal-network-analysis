import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, api } from "../services/api.js";
import { isValidId } from "../utils/validate.js";
import EntityCard from "../components/EntityCard.jsx";
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

  if (loading) return <p className="text-sm text-gray-500">Loading entity…</p>;
  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!entity) return <p className="text-sm text-gray-500">Entity not found.</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-gray-900">Entity profile</h1>
      <EntityCard entity={entity} />
      <section>
        <h2 className="mb-2 font-medium text-gray-900">Provenance</h2>
        {entity.source_refs?.length ? (
          <ul className="list-disc pl-5 text-sm text-gray-700">
            {entity.source_refs.map((ref, index) => (
              <li key={`${ref.document_id}-${index}`} className="font-mono text-xs">
                {ref.document_id}
                {ref.confidence != null ? ` (confidence ${ref.confidence})` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-500">No source references recorded.</p>
        )}
      </section>
      <section>
        <h2 className="mb-2 font-medium text-gray-900">Immediate graph</h2>
        {graph ? <NetworkGraph nodes={graph.nodes} edges={graph.edges} height={360} /> : null}
      </section>
      <section>
        <h2 className="mb-2 font-medium text-gray-900">Timeline</h2>
        <Timeline events={timeline?.events} />
      </section>
    </div>
  );
}
