import { object } from "@/lib/planning-cycles/contracts";
import type { Sport } from "./contracts";

export type Coordinates = { latitude: string; longitude: string; timezone_name: string };
export type GeographicArea = { schema_version: "training-area-v0.1"; south: string; north: string; west: string; east: string; timezone_name: string };
export type LightMode = "none" | "daylight" | "civil_twilight";
export type DaylightRule = { sport: Sport; mode: LightMode; start_buffer_minutes: number; end_buffer_minutes: number };
export const lightModeLabels = { none: "Nincs napfénykorlát", daylight: "Napkelte és napnyugta között", civil_twilight: "Polgári hajnal és alkonyat között" };
export const daylightReasons = {
  DAYLIGHT_COORDINATES_REQUIRED: "A napfénykorláthoz adj meg egy konkrét helyet vagy edzési körzetet, időzónával.",
  DAYLIGHT_NO_ALLOWED_INTERVAL: "Az időablak a megadott napfénykorláton kívül esik.",
  DAYLIGHT_SESSION_DOES_NOT_FIT: "A teljes edzés nem fér a napfénykorlát és az időráhagyás után megmaradó időbe.",
};
const invalid = () => Error("A földrajzi hely vagy a napfénykorlát hibás.");
export function readCoordinates(raw: unknown): Coordinates {
  const v = object(raw), pattern = /^-?(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,7})?$/;
  if (Object.keys(v).sort().join("|") !== "latitude|longitude|timezone_name" ||
      typeof v.latitude !== "string" || typeof v.longitude !== "string" ||
      !pattern.test(v.latitude) || !pattern.test(v.longitude) ||
      Math.abs(Number(v.latitude)) > 90 || Math.abs(Number(v.longitude)) > 180 ||
      typeof v.timezone_name !== "string" || !v.timezone_name || v.timezone_name.length > 64) throw invalid();
  new Intl.DateTimeFormat("hu", { timeZone: v.timezone_name });
  return v as Coordinates;
}
export function readDaylightRules(raw: unknown, sports?: string[]): DaylightRule[] {
  if (!Array.isArray(raw) || raw.length > 7) throw invalid();
  const seen = new Set();
  for (const item of raw) {
    const v = object(item);
    if (Object.keys(v).sort().join("|") !== "end_buffer_minutes|mode|sport|start_buffer_minutes" ||
        !["KAYAK", "RUNNING", "SWIMMING", "STRENGTH", "CYCLING", "GYMNASTICS", "STRETCHING"].includes(String(v.sport)) ||
        (sports && !sports.includes(String(v.sport))) || seen.has(v.sport) ||
        !Object.keys(lightModeLabels).includes(String(v.mode)) ||
        ![v.start_buffer_minutes, v.end_buffer_minutes].every(n => typeof n === "number" && Number.isInteger(n) && n >= 0 && n <= 120) ||
        (v.mode === "none" && (v.start_buffer_minutes !== 0 || v.end_buffer_minutes !== 0))) throw invalid();
    seen.add(v.sport);
  }
  return raw as DaylightRule[];
}
export function readGeographicArea(raw: unknown): GeographicArea {
  const a = object(raw), pattern = /^-?(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,7})?$/;
  if (Object.keys(a).sort().join() !== "east,north,schema_version,south,timezone_name,west" ||
    a.schema_version !== "training-area-v0.1" || ![a.south,a.north,a.west,a.east].every(v => typeof v === "string" && pattern.test(v)) ||
    !(Number(a.south) >= -90 && Number(a.north) <= 90 && Number(a.south) < Number(a.north) && Number(a.north)-Number(a.south) <= 20 &&
      Number(a.west) >= -180 && Number(a.east) <= 180 && Number(a.west) < Number(a.east) && Number(a.east)-Number(a.west) <= 20) ||
    typeof a.timezone_name !== "string" || !a.timezone_name || a.timezone_name.length > 64) throw invalid();
  new Intl.DateTimeFormat("hu", { timeZone: a.timezone_name });
  return a as GeographicArea;
}
export function decimalCoordinate(value: string): string { return value.trim().replace(",", "."); }
