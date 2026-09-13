/** Pure helpers for the two heatmaps (unit-tested). */

export const FEATURE_KEYS = [
  "calls_per_day",
  "unique_contacts",
  "average_call_duration",
  "night_calls",
  "transaction_count",
  "transaction_amount",
  "unique_locations",
  "location_changes",
];

export const FEATURE_LABELS = {
  calls_per_day: "Calls/day",
  unique_contacts: "Contacts",
  average_call_duration: "Avg call (s)",
  night_calls: "Night calls",
  transaction_count: "Transactions",
  transaction_amount: "Txn amount",
  unique_locations: "Locations",
  location_changes: "Location changes",
};

/** Max-normalize each feature column to [0,1] across items. */
export function normalizeFeatureColumns(items) {
  const maxes = {};
  for (const key of FEATURE_KEYS) {
    let max = 0;
    for (const item of items || []) {
      const value = Number(item?.features?.[key]);
      if (Number.isFinite(value) && value > max) max = value;
    }
    maxes[key] = max;
  }
  return (items || []).map((item) => {
    const cells = {};
    for (const key of FEATURE_KEYS) {
      const value = Number(item?.features?.[key]);
      cells[key] = maxes[key] > 0 && Number.isFinite(value) ? value / maxes[key] : 0;
    }
    return { entity_id: item?.entity_id, severity: item?.severity, cells };
  });
}

/** Bin timestamps into a weeks×days grid (default last 12 weeks). */
export function weeklyActivityGrid(timestamps, weeks = 12) {
  const days = [];
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const today = now.getTime();
  const start = today - (weeks * 7 - 1) * 86400000;
  for (let i = 0; i < weeks * 7; i += 1) {
    days.push({ date: new Date(start + i * 86400000), count: 0 });
  }
  for (const ts of timestamps || []) {
    const t = new Date(ts);
    if (Number.isNaN(t.getTime())) continue;
    t.setHours(0, 0, 0, 0);
    const idx = Math.floor((t.getTime() - start) / 86400000);
    if (idx >= 0 && idx < days.length) days[idx].count += 1;
  }
  const max = Math.max(0, ...days.map((d) => d.count));
  return { days, max };
}
