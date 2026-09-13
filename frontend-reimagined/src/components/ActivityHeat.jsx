import { useMemo } from "react";
import { weeklyActivityGrid } from "../utils/heatmaps.js";

/** GitHub-style weekly activity heatmap from event timestamps. */
export default function ActivityHeat({ timestamps }) {
  const { days, max } = useMemo(() => weeklyActivityGrid(timestamps), [timestamps]);
  const weeks = [];
  for (let w = 0; w < days.length / 7; w += 1) {
    weeks.push(days.slice(w * 7, w * 7 + 7));
  }
  return (
    <div>
      <div className="flex gap-1 overflow-x-auto pb-1">
        {weeks.map((week, wi) => (
          <div key={wi} className="grid grid-rows-7 gap-1">
            {week.map((day, di) => (
              <div
                key={di}
                className="h-3.5 w-3.5 rounded-sm"
                style={{
                  backgroundColor:
                    day.count === 0
                      ? "#eef1f6"
                      : `rgba(79, 70, 229, ${0.25 + 0.75 * (max ? day.count / max : 0)})`,
                }}
                title={`${day.date.toISOString().slice(0, 10)} — ${day.count} events`}
              />
            ))}
          </div>
        ))}
      </div>
      <p className="mt-1 text-[11px] text-slate-500">
        Case events per day, last 12 weeks · {max} busiest day
        {timestamps?.length ? ` · ${timestamps.length} timestamped events` : ""}.
      </p>
    </div>
  );
}
