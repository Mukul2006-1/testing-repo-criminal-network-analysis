import { severityTone, typeColor } from "../utils/validate.js";

export function SeverityBadge({ severity, score }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-bold ${severityTone(severity)}`}
    >
      {severity || "—"}
      {score !== undefined && score !== null ? <span className="font-mono">{score}</span> : null}
    </span>
  );
}

export function TypeBadge({ type }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-bold text-slate-700"
    >
      <span
        className="inline-block h-2 w-2 rounded-full"
        style={{ backgroundColor: typeColor(type) }}
      />
      {type || "UNKNOWN"}
    </span>
  );
}
