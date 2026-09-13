import { useMemo } from "react";
import { Link } from "react-router-dom";
import { FEATURE_KEYS, FEATURE_LABELS, normalizeFeatureColumns } from "../utils/heatmaps.js";

/** Anomaly feature-intensity heatmap: rows = entities, columns = signals. */
export default function FeatureHeat({ items }) {
  const rows = useMemo(
    () => normalizeFeatureColumns((items || []).slice(0, 20)),
    [items]
  );
  if (rows.length === 0) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            <th className="sticky left-0 bg-white px-2 py-1 text-left font-bold text-slate-500">
              Entity
            </th>
            {FEATURE_KEYS.map((key) => (
              <th key={key} className="px-1 py-1 text-center font-semibold text-slate-500">
                {FEATURE_LABELS[key]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.entity_id} className="border-t border-slate-100">
              <td className="sticky left-0 bg-white px-2 py-1 font-mono text-[11px]">
                <Link
                  className="font-bold text-argus-700 hover:underline"
                  to={`/entities/${encodeURIComponent(row.entity_id)}`}
                >
                  {row.entity_id}
                </Link>
              </td>
              {FEATURE_KEYS.map((key) => {
                const v = row.cells[key];
                return (
                  <td key={key} className="px-1 py-1">
                    <div
                      className="mx-auto h-5 min-w-8 rounded"
                      style={{ backgroundColor: `rgba(79, 70, 229, ${0.06 + v * 0.9})` }}
                      title={`${FEATURE_LABELS[key]}: relative intensity ${(v * 100).toFixed(0)}%`}
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-[11px] text-slate-500">
        Top {rows.length} flagged entities · darker = stronger signal relative to peers.
      </p>
    </div>
  );
}
