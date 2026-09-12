export default function Timeline({ events }) {
  if (!events || events.length === 0) {
    return <p className="text-sm text-gray-500">No timeline events available.</p>;
  }
  const ordered = [...events].sort((a, b) =>
    String(a.timestamp).localeCompare(String(b.timestamp))
  );
  return (
    <ol className="space-y-3">
      {ordered.map((event, index) => (
        <li key={`${event.timestamp}-${event.source_id}-${index}`} className="rounded border border-gray-200 bg-white p-3 shadow-sm">
          <div className="flex items-center justify-between gap-2 text-sm">
            <span className="font-mono text-gray-600">{event.timestamp || "unknown time"}</span>
            <span className="rounded bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700">
              {event.type || "EVENT"}
            </span>
          </div>
          <p className="mt-1 text-sm text-gray-900">{event.description || "—"}</p>
          {event.source_id ? (
            <p className="mt-1 font-mono text-xs text-gray-500">source: {event.source_id}</p>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
