import type { Series } from "./contracts";
import { speedValue } from "./presentation";
import type { SpeedUnit } from "./presentation";

export type Point = { index: number; ms: number; value: number };
export function withPace(series: Series[]): Series[] {
  const result = series.flatMap(s => {
    if (s.metric_key !== "speed_kmh") return [s];
    const values = s.values.map(v => v !== null && v > 0 && Number.isFinite(3600 / v) ? 3600 / v : null);
    const valid = values.filter(v => v !== null).length;
    return [s, { ...s, id: s.id + "-pace", metric_key: "pace_sec_km" as const, unit: "perc/km", values,
      derived: true, valid_sample_count: valid, missing_sample_count: values.length - valid }];
  });
  // Both simultaneous crank measurements are needed for a measured total.
  const left = series.filter(s => s.metric_key === "left_power_w"), right = series.filter(s => s.metric_key === "right_power_w");
  if (left.length === 1 && right.length === 1 && left[0].exercise_index === right[0].exercise_index &&
      left[0].interval_ms !== null && left[0].interval_ms === right[0].interval_ms && left[0].values.length === right[0].values.length) {
    const a = left[0], b = right[0];
    const values = a.values.map((v, i) => v !== null && b.values[i] !== null && Number.isFinite(v + b.values[i]!) ? v + b.values[i]! : null);
    const valid = values.filter(v => v !== null).length;
    result.push({ ...a, id: a.id + "+" + b.id, metric_key: "power_w", source_type: "LEFT_PLUS_RIGHT_POWER", source_path: a.source_path + " + " + b.source_path,
      values, derived: true, valid_sample_count: valid, missing_sample_count: values.length - valid });
  }
  return result;
}
export function extent(series: Series[]): number {
  return Math.max(0, ...series.filter(s => s.interval_ms !== null && s.values.length > 0)
    .map(s => (s.values.length - 1) * s.interval_ms!));
}
/** Source slots retain their index. Each null closes a run before reduction. */
export function segments(s: Series, from: number, to: number, budget = 800): { runs: Point[][]; reduced: boolean } {
  if (s.interval_ms === null || from > to || !Number.isFinite(from + to)) return { runs: [], reduced: false };
  const first = Math.max(0, Math.ceil(from / s.interval_ms)), last = Math.min(s.values.length - 1, Math.floor(to / s.interval_ms));
  const width = Math.max(1, Math.ceil((last - first + 1) / Math.max(1, Math.floor(budget / 4))));
  const runs: Point[][] = []; let run: Point[] = [], bucket: Point[] = [], reduced = false;
  function flush() {
    if (!bucket.length) return;
    let low = bucket[0], high = bucket[0];
    for (const p of bucket) { if (p.value < low.value) low = p; if (p.value > high.value) high = p; }
    const selected = [bucket[0], low, high, bucket[bucket.length - 1]];
    const unique = [...new Map(selected.map(p => [p.index, p])).values()].sort((a, b) => a.index - b.index);
    if (unique.length < bucket.length) reduced = true;
    run.push(...unique); bucket = [];
  }
  for (let i = first; i <= last; i++) {
    const value = s.values[i];
    if (value === null) { flush(); if (run.length) runs.push(run); run = []; }
    else { bucket.push({ index: i, ms: i * s.interval_ms, value }); if (bucket.length >= width) flush(); }
  }
  flush(); if (run.length) runs.push(run);
  return { runs, reduced };
}
export function atCursor(s: Series, ms: number): Point | null {
  if (s.interval_ms === null || ms < 0 || ms > (s.values.length - 1) * s.interval_ms) return null;
  const index = Math.round(ms / s.interval_ms), value = s.values[index];
  return value === null || value === undefined ? null : { index, ms: index * s.interval_ms, value };
}
export function clock(ms: number) {
  const rounded = Math.max(0, Math.round(ms)), total = Math.floor(rounded / 1000), fraction = rounded % 1000;
  const h = Math.floor(total / 3600), m = Math.floor(total % 3600 / 60), s = total % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : String(m)) + ":" + String(s).padStart(2, "0") +
    (fraction ? "," + String(fraction).padStart(3, "0").replace(/0+$/, "") : "");
}
export function displayValue(s: Series, value: number | null, speedUnit: SpeedUnit = "km/h") {
  if (value === null) return "Nincs minta";
  return s.metric_key === "pace_sec_km" ? paceValue(value) + " perc/km" :
    new Intl.NumberFormat("hu-HU", { maximumFractionDigits: 2 }).format(s.metric_key === "speed_kmh" ? speedValue(value, speedUnit) : value) + " " + (s.metric_key === "speed_kmh" ? speedUnit : s.unit);
}
export function paceValue(seconds: number) {
  return seconds <= Number.MAX_SAFE_INTEGER / 1000 ? clock(seconds * 1000) :
    new Intl.NumberFormat("hu-HU", { maximumFractionDigits: 2, notation: "scientific" }).format(seconds / 60);
}
