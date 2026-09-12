/** Labeled score bar (0..1) used for PageRank / Betweenness / Anomaly. */
export default function ScoreBar({ label, value, display, barClass }) {
  const pct = Math.max(0, Math.min(1, Number(value) || 0)) * 100;
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="font-semibold text-slate-600">{label}</span>
        <span className="font-mono font-semibold text-ink">{display}</span>
      </div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full ${barClass || "bg-argus-500"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
