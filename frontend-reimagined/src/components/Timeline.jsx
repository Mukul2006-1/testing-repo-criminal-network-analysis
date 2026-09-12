export default function Timeline({ events }) {
  if (!events || events.length === 0) {
    return <p className="text-sm text-slate-500">No timeline events available.</p>;
  }
  const ordered = [...events].sort((a, b) =>
    String(a.timestamp).localeCompare(String(b.timestamp))
  );
  return (
    <ol className="relative space-y-3 border-l-2 border-argus-100 pl-4">
      {ordered.map((event, index) => (
        <li key={`${event.timestamp}-${event.source_id}-${index}`} className="relative">
          <span className="absolute -left-[22px] top-1 h-2.5 w-2.5 rounded-full bg-argus-500 ring-4 ring-argus-50" />
          <div className="rounded-xl border border-slate-200/80 bg-white p-3 shadow-card">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span className="font-mono text-xs text-slate-500">{event.timestamp || "unknown time"}</span>
              <span className="rounded-full bg-argus-50 px-2 py-0.5 text-[11px] font-bold text-argus-700">
                {event.type || "EVENT"}
              </span>
            </div>
            <p className="mt-1 text-sm text-ink">{event.description || "—"}</p>
            {event.source_id ? (
              <p className="mt-1 font-mono text-xs text-slate-500">source: {event.source_id}</p>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
