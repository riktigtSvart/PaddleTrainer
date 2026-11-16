// Same NOAA/Meeus calculation as the API; seconds since the Unix epoch.
// Independent replay rejects a changed light-window claim even after rehashing.
import type { Coordinates, DaylightRule } from "./daylight-rules";
export const SOLAR_METHOD = "noaa-meeus-light-v1";
const rad = (v: number) => v * Math.PI / 180, deg = (v: number) => v * 180 / Math.PI;
const mod = (a: number, b: number) => ((a % b) + b) % b;
export function solarPosition(timestamp: number): [number, number] {
  const t = (timestamp / 86400 + 2440587.5 - 2451545) / 36525;
  const longitude = mod(280.46646 + t * (36000.76983 + t * .0003032), 360);
  const anomaly = rad(357.52911 + t * (35999.05029 - .0001537 * t));
  const e = .016708634 - t * (.000042037 + .0000001267 * t);
  const centre = Math.sin(anomaly) * (1.914602 - t * (.004817 + .000014 * t)) + Math.sin(2 * anomaly) * (.019993 - .000101 * t) + Math.sin(3 * anomaly) * .000289;
  const omega = rad(125.04 - 1934.136 * t);
  const apparent = rad(longitude + centre - .00569 - .00478 * Math.sin(omega));
  const obliquity = rad(23 + (26 + (21.448 - t * (46.815 + t * (.00059 - t * .001813))) / 60) / 60 + .00256 * Math.cos(omega));
  const declination = Math.asin(Math.sin(obliquity) * Math.sin(apparent));
  const y = Math.tan(obliquity / 2) ** 2, l = rad(longitude);
  const eq = 4 * deg(y * Math.sin(2 * l) - 2 * e * Math.sin(anomaly) + 4 * e * y * Math.sin(anomaly) * Math.cos(2 * l) - .5 * y * y * Math.sin(4 * l) - 1.25 * e * e * Math.sin(2 * anomaly));
  return [declination, eq];
}
export function solarAltitude(timestamp: number, lat: number, lon: number) {
  const [decl, eq] = solarPosition(timestamp), hour = rad((mod(timestamp, 86400) / 60 + eq + 4 * lon) / 4 - 180), phi = rad(lat);
  return deg(Math.asin(Math.max(-1, Math.min(1, Math.sin(phi) * Math.sin(decl) + Math.cos(phi) * Math.cos(decl) * Math.cos(hour)))));
}
function extremum(low: number, high: number, lat: number, lon: number, maximum: boolean) {
  for (let i = 0; i < 40; i++) {
    const a = (2 * low + high) / 3, b = (low + 2 * high) / 3;
    if ((solarAltitude(a, lat, lon) < solarAltitude(b, lat, lon)) === maximum) low = a; else high = b;
  }
  return (low + high) / 2;
}
const cache = new Map<string, { windows: [number, number][]; rising: number[]; setting: number[] }>();
export function solarWindows(first: number, last: number, lat: number, lon: number, mode: "daylight" | "civil_twilight") {
  const key = [first, last, lat, lon, mode].join("|");
  if (cache.has(key)) return cache.get(key)!;
  const low = (first - 2) * 86400, high = (last + 3) * 86400, points = [low, high];
  for (let day = first - 3; day < last + 4; day++) {
    let noon = day * 86400 + 43200 - lon * 240;
    for (let i = 0; i < 3; i++) noon = day * 86400 + 43200 - lon * 240 - solarPosition(noon)[1] * 60;
    for (const [centre, max] of [[noon, true], [noon + 43200, false]] as [number, boolean][]) {
      const value = extremum(centre - 7200, centre + 7200, lat, lon, max);
      if (low < value && value < high) points.push(value);
    }
  }
  points.sort((a, b) => a - b);
  const threshold = mode === "daylight" ? -.833 : -6, boundaries = [low], rising: number[] = [], setting: number[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const above = solarAltitude(points[i], lat, lon) >= threshold;
    if (above === (solarAltitude(points[i + 1], lat, lon) >= threshold)) continue;
    let left = points[i], right = points[i + 1];
    for (let j = 0; j < 45; j++) {
      const mid = (left + right) / 2;
      if ((solarAltitude(mid, lat, lon) >= threshold) === above) left = mid; else right = mid;
    }
    const crossing = (left + right) / 2;
    boundaries.push(crossing);(above ? setting : rising).push(crossing);
  }
  boundaries.push(high);
  const windows: [number, number][] = [];
  for (let i = 0; i < boundaries.length - 1; i++) if (solarAltitude((boundaries[i] + boundaries[i + 1]) / 2, lat, lon) >= threshold) windows.push([boundaries[i], boundaries[i + 1]]);
  const result = { windows, rising, setting };
  if (cache.size >= 1024) cache.clear();
  cache.set(key, result);return result;
}
export function lightIntervals(start: number, end: number, point: Coordinates, rule: DaylightRule): [number, number][] {
  if (rule.mode === "none") return [[start, end]];
  return solarWindows(Math.floor(start / 86400), Math.floor(end / 86400), Number(point.latitude), Number(point.longitude), rule.mode).windows
    .map(([a, b]): [number, number] => [Math.max(start, Math.ceil(a + rule.start_buffer_minutes * 60)), Math.min(end, Math.floor(b - rule.end_buffer_minutes * 60))]).filter(([a, b]) => a < b);
}
