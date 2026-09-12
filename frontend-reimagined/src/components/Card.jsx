export default function Card({ title, action, children, className }) {
  return (
    <section
      className={`rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card ${className || ""}`}
    >
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500">{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
