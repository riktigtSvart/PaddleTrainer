import type { MetricKey, Series, RoutePoint } from "./contracts";
import { atCursor, segments } from "./chart-data";
import { speedValue } from "./presentation";
import type { SpeedUnit } from "./presentation";
export type AxisMode = "time" | "distance";
export const explorerKey = (owner: string) =>
  `paddletrainer:session-explorer:v1:${owner}`;
export type Choices = {
  left: MetricKey | "none";
  right: MetricKey | "none";
  x: AxisMode;
  boundaries: boolean;
  zones: boolean;
  targets: boolean;
};
export const defaultChoices: Choices = {
  left: "speed_kmh",
  right: "heart_rate_bpm",
  x: "time",
  boundaries: true,
  zones: false,
  targets: true,
};
export function readChoices(raw: string): Choices {
  const x = JSON.parse(raw);
  const metrics = [
    "none",
    "speed_kmh",
    "pace_sec_km",
    "heart_rate_bpm",
    "power_w",
    "left_power_w",
    "right_power_w",
    "cadence_per_min",
    "altitude_m",
    "temperature_c",
    "distance_m",
  ];
  if (
    !x ||
    !metrics.includes(x.left) ||
    !metrics.includes(x.right) ||
    !["time", "distance"].includes(x.x) ||
    ![x.boundaries, x.zones, x.targets].every((v) => typeof v === "boolean")
  )
    throw Error("Érvénytelen grafikonbeállítás.");
  return {
    left: x.left,
    right: x.right === x.left ? "none" : x.right,
    x: x.x,
    boundaries: x.boundaries,
    zones: x.zones,
    targets: x.targets,
  };
}
export function selectMetric(
  series: Series[],
  metric: Choices["left"],
): Series | null {
  const matches = series.filter(
    (s) =>
      s.metric_key === metric &&
      s.interval_ms !== null &&
      s.valid_sample_count > 0,
  );
  return matches.length === 1 ? matches[0] : null;
}
export function distanceSource(series: Series[]): Series | null {
  const s = selectMetric(series, "distance_m");
  if (!s || s.values[0] === null || !s.values.length) return null;
  let previous = -Infinity;
  for (const value of s.values)
    if (value !== null) {
      if (value < previous) return null;
      previous = value;
    }
  return previous > s.values[0] ? s : null;
}
export function distanceAt(s: Series | null, ms: number): number | null {
  if (
    !s ||
    s.interval_ms === null ||
    ms < 0 ||
    !Number.isInteger(ms / s.interval_ms)
  )
    return null;
  const v = s.values[ms / s.interval_ms],
    origin = s.values[0];
  return typeof v === "number" && origin !== null ? v - origin : null;
}
export function timeAtDistance(
  s: Series | null,
  meters: number,
): number | null {
  if (
    !s ||
    s.interval_ms === null ||
    s.values[0] === null ||
    !Number.isFinite(meters)
  )
    return null;
  let best: number | null = null,
    delta = Infinity;
  for (let i = 0; i < s.values.length; i++) {
    const v = s.values[i];
    if (v === null) continue;
    const diff = Math.abs(v - s.values[0] - meters);
    if (diff < delta) {
      delta = diff;
      best = i * s.interval_ms;
    }
  }
  return best;
}
export function plotRuns(
  s: Series | null,
  from: number,
  to: number,
  mode: AxisMode,
  distance: Series | null,
  unit: SpeedUnit,
) {
  if (!s) return [];
  const masked =
    mode === "distance" && s.interval_ms !== null
      ? {
          ...s,
          values: s.values.map((v, i) =>
            distanceAt(distance, i * s.interval_ms!) === null ? null : v,
          ),
        }
      : s;
  return segments(masked, from, to, 1200).runs.flatMap((run) => {
    const runs: { ms: number; x: number; y: number }[][] = [];
    let current: { ms: number; x: number; y: number }[] = [];
    for (const point of run) {
      const x = mode === "time" ? point.ms : distanceAt(distance, point.ms);
      if (x === null) {
        if (current.length) runs.push(current);
        current = [];
      } else
        current.push({
          ms: point.ms,
          x,
          y:
            s.metric_key === "speed_kmh"
              ? speedValue(point.value, unit)
              : point.value,
        });
    }
    if (current.length) runs.push(current);
    return runs;
  });
}
export function nearestRoute(
  points: RoutePoint[],
  ms: number,
): RoutePoint | null {
  let best: RoutePoint | null = null,
    delta = Infinity;
  for (const p of points)
    if (p.ms !== null && p.lat !== null && p.lon !== null) {
      const d = Math.abs(p.ms - ms);
      if (d < delta) {
        delta = d;
        best = p;
      }
    }
  return delta <= 5000 ? best : null;
}
export function valueAt(s: Series | null, ms: number) {
  return s ? atCursor(s, ms) : null;
}
export function mercator(lat: number, lon: number, z: number) {
  const n = 256 * 2 ** z,
    clamped =
      (Math.max(-85.05112878, Math.min(85.05112878, lat)) * Math.PI) / 180;
  return {
    x: ((lon + 180) / 360) * n,
    y:
      ((1 - Math.log(Math.tan(clamped) + 1 / Math.cos(clamped)) / Math.PI) /
        2) *
      n,
  };
}
export function routeRuns(points: RoutePoint[]) {
  const runs: RoutePoint[][] = [];
  let run: RoutePoint[] = [];
  for (const p of points) {
    const last = run.at(-1);
    if (
      p.lat === null ||
      p.lon === null ||
      Math.abs(p.lat) > 85.05112878 ||
      (last &&
        (Math.abs(p.lon - last.lon!) > 180 ||
          (last.ms !== null && p.ms !== null && p.ms - last.ms > 60000)))
    ) {
      if (run.length) runs.push(run);
      run = [];
    }
    if (p.lat !== null && p.lon !== null && Math.abs(p.lat) <= 85.05112878)
      run.push(p);
  }
  if (run.length) runs.push(run);
  return runs;
}
