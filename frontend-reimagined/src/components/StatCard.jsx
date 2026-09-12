export default function StatCard({ icon, label, value, sub, tone }) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-card">
      <div className="flex items-center justify-between">
        <p className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</p>
        {icon ? (
          <span
            className={`material-symbols-outlined rounded-lg px-1.5 py-1 text-[20px] ${tone || "bg-argus-50 text-argus-600"}`}
          >
            {icon}
          </span>
        ) : null}
      </div>
      <p className="mt-1 text-3xl font-extrabold tabular-nums text-ink">{value ?? "—"}</p>
      {sub ? <p className="mt-1 text-xs text-slate-500">{sub}</p> : null}
    </div>
  );
}
