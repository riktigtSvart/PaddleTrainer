import type { HeartRateZones, MetricKey, MetricZones, Plan } from "./contracts";

export const speedUnits = ["km/h", "m/s", "knots"] as const;
export type SpeedUnit = typeof speedUnits[number];
export const speedUnitKey = "paddletrainer:speed-unit:v1";
export const isSpeedUnit = (value: unknown): value is SpeedUnit => speedUnits.some(unit => unit === value);
// Stored speeds remain in km/h. One nautical mile is exactly 1.852 km.
export const speedValue = (kmh: number, unit: SpeedUnit) => kmh / (unit === "m/s" ? 3.6 : unit === "knots" ? 1.852 : 1);

export type PulseTarget = { id: string; label: string; low: number | null; high: number | null; zoneLabel: string | null };
export function pulseTargets(plan: Plan | null, zones: HeartRateZones | null): PulseTarget[] {
  if (!plan) return [];
  const parents = new Set(plan.blocks.map(b => b.parent_block_id).filter(Boolean));
  return plan.blocks.filter(b => !parents.has(b.id)).flatMap<PulseTarget>(b => {
    const low = b.intensity_min, high = b.intensity_max;
    if (low === null || high === null || !Number.isFinite(low + high) || low > high) return [];
    const label = b.name || b.block_type;
    if (b.intensity_type === "HR_BPM" && low > 0 && high < 1000) return [{ id: b.id, label, low, high, zoneLabel: null }];
    if (!["HEART_RATE_ZONES", "HR_ZONE"].includes(b.intensity_type ?? "") || !Number.isInteger(low) || !Number.isInteger(high) || low < 1 || high > 5) return [];
    const selected = zones?.zones.filter(z => z.index >= low && z.index <= high);
    const complete = selected?.length === high - low + 1;
    return [{ id: b.id, label, low: complete ? selected[0].low : null, high: complete ? selected.at(-1)!.high : null,
      zoneLabel: low === high ? `Z${low}` : `Z${low}–Z${high}` }];
  });
}

export type TargetFamily = "heart_rate" | "speed" | "power";
export type GraphTarget = PulseTarget & { family: TargetFamily };
export function graphTargets(plan: Plan | null, zones: { heart_rate: HeartRateZones | null; speed: MetricZones | null; power: MetricZones | null }): GraphTarget[] {
  const result: GraphTarget[] = pulseTargets(plan, zones.heart_rate).map(t => ({ ...t, family: "heart_rate" }));
  if (!plan) return result;
  const parents = new Set(plan.blocks.map(b => b.parent_block_id).filter(Boolean));
  for (const block of plan.blocks.filter(b => !parents.has(b.id))) {
    const a = block.intensity_min, b = block.intensity_max, type = block.intensity_type;
    if (a === null || b === null || !Number.isFinite(a + b) || a < 0 || a > b) continue;
    const common = { id: block.id, label: block.name || block.block_type, zoneLabel: null };
    if (type === "POWER_W") result.push({ ...common, family: "power", low: a, high: b });
    else if (type === "SPEED_KMH" || type === "SPEED_MPS") {
      const factor = type === "SPEED_MPS" ? 3.6 : 1;
      if (Number.isFinite(b * factor)) result.push({ ...common, family: "speed", low: a * factor, high: b * factor });
    } else if (type === "PACE_SEC_KM" && a > 0) {
      const low = 3600 / b, high = 3600 / a;
      if (Number.isFinite(low + high)) result.push({ ...common, family: "speed", low, high });
    } else if (["SPEED_ZONES", "SPEED_ZONE", "POWER_ZONES", "POWER_ZONE"].includes(type ?? "") && Number.isInteger(a) && Number.isInteger(b) && a >= 1 && b <= 5) {
      const family = type!.startsWith("SPEED") ? "speed" : "power", definition = zones[family];
      const selected = definition?.zones.filter(z => z.index >= a && z.index <= b);
      const complete = selected?.length === b - a + 1;
      result.push({ ...common, family, low: complete ? selected[0].low : null, high: complete ? selected.at(-1)!.high : null,
        zoneLabel: a === b ? `Z${a}` : `Z${a}–Z${b}` });
    }
  }
  return result;
}
export function targetOnChart(target: GraphTarget | null, metric: MetricKey, unit: SpeedUnit): PulseTarget | null {
  if (!target || target.low === null || target.high === null) return null;
  if (target.family === "heart_rate") return metric === "heart_rate_bpm" ? target : null;
  if (target.family === "power") return metric === "power_w" ? target : null;
  if (metric === "speed_kmh") return { ...target, low: speedValue(target.low, unit), high: speedValue(target.high, unit) };
  if (metric === "pace_sec_km" && target.low > 0) {
    const low = 3600 / target.high, high = 3600 / target.low;
    return Number.isFinite(low + high) ? { ...target, low, high } : null;
  }
  return null;
}
export function zonesOnChart(zones: MetricZones | null, metric: MetricKey, unit: SpeedUnit): MetricZones | null {
  if (!zones) return null;
  if (metric === "heart_rate_bpm") return zones.unit === "bpm" ? zones : null;
  if (metric === "power_w") return zones.unit === "W" ? zones : null;
  if (zones.unit !== "km/h") return null;
  if (metric === "speed_kmh") return { ...zones, unit, zones: zones.zones.map(z => ({ ...z, low: speedValue(z.low, unit), high: speedValue(z.high, unit) })) };
  if (metric === "pace_sec_km") return { ...zones, unit: "perc/km", zones: zones.zones.flatMap(z => {
    const low = 3600 / z.high, high = z.low > 0 ? 3600 / z.low : Infinity;
    return Number.isFinite(low + high) ? [{ ...z, low, high }] : [];
  }) };
  return null;
}

export type Axis = { low: number; high: number; ticks: number[] };
/** Bounded, round ticks in displayed units. The normalized fallback handles finite extremes. */
export function valueAxis(minimum: number, maximum: number, pace = false): Axis {
  let low = minimum, high = maximum;
  if (!Number.isFinite(low) || !Number.isFinite(high)) { low = 0; high = 1; }
  if (low === high) {
    const padding = Math.max(1, Math.abs(low) * .05);
    if (Number.isFinite(low - padding)) low -= padding;
    if (Number.isFinite(high + padding)) high += padding;
  }
  const span = high - low;
  if (!Number.isFinite(span) || span <= 0) return { low, high, ticks: [low, low / 2 + high / 2, high] };
  const raw = span / 7;
  let step: number;
  if (pace && raw >= 5 && raw <= 3600) {
    step = [5, 10, 15, 20, 30, 60, 120, 180, 300, 600, 900, 1800, 3600].find(s => s >= raw)!;
  } else {
    const power = 10 ** Math.floor(Math.log10(raw));
    step = [1, 2, 2.5, 5, 10].map(n => n * power).find(n => n >= raw) ?? power * 10;
  }
  if (!Number.isFinite(step) || step <= 0) return { low, high, ticks: [low, high] };
  const first = Math.floor(low / step), last = Math.ceil(high / step);
  const paddedLow = first * step, paddedHigh = last * step;
  if (!Number.isFinite(paddedLow) || !Number.isFinite(paddedHigh) || !Number.isFinite(paddedHigh - paddedLow)) {
    return { low, high, ticks: [low, low / 2 + high / 2, high] };
  }
  const ticks: number[] = [];
  for (let i = first; i <= last && ticks.length < 16; i++) ticks.push(Number((i * step).toPrecision(14)) || 0);
  return { low: paddedLow, high: paddedHigh, ticks };
}

export function timeTicks(from: number, to: number): number[] {
  if (from === to) return [from];
  const span = to - from;
  const step = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000,
    300000, 600000, 900000, 1800000, 3600000, 7200000, 14400000, 28800000, 86400000, 604800000, 2592000000].find(n => n >= span / 6) ?? span / 6;
  const ticks: number[] = [from];
  for (let t = Math.ceil(from / step) * step; t < to && ticks.length < 9; t += step) if (t - from >= span / 20 && to - t >= span / 20) ticks.push(t);
  ticks.push(to);
  return ticks;
}

export function axisNumber(value: number) {
  return new Intl.NumberFormat("hu-HU", { maximumFractionDigits: Math.abs(value) > 0 && Math.abs(value) < .01 ? 5 : 2,
    ...(Math.abs(value) >= 1e6 || Math.abs(value) > 0 && Math.abs(value) < 1e-5 ? { notation: "scientific" as const } : {}) }).format(value);
}
