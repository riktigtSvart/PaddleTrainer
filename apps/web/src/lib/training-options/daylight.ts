import { canonical, object, sha, day } from "@/lib/planning-cycles/contracts";
import { readOptionsReceipt } from "./contracts";
import type { OptionsData } from "./contracts";
import { readCoordinates } from "./daylight-rules";
import type { Coordinates, DaylightRule } from "./daylight-rules";
import { lightIntervals, solarWindows, SOLAR_METHOD } from "./solar";
import { areaLightIntervals, AREA_SOLAR_METHOD } from "./area-daylight";
import { readGeographicArea } from "./daylight-rules";
import type { GeographicArea } from "./daylight-rules";
export type SolarDay = { state: "all_day" | "no_light" | "crossings"; rises_at: string[]; sets_at: string[]; intervals: { start_at: string; end_at: string }[] };
export type DaylightPreview = { method: string; day_start_at: string; day_end_at: string; daylight: SolarDay; civil_twilight: SolarDay };
const invalid = () => Error("A napfényadatok forrása vagy számítása nem ellenőrizhető.");
function localDate(t: number, zone: string) {
  const parts = new Intl.DateTimeFormat("en", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(t * 1000));
  return ["year", "month", "day"].map(p => parts.find(v => v.type === p)?.value).join("-");
}
export type GeographyPreviewRequest = { date: string; coordinates: Coordinates; area?: never } | { date: string; area: GeographicArea; coordinates?: never };
export async function readDaylightPreview(raw: unknown, owner: string, proposal: GeographyPreviewRequest): Promise<DaylightPreview> {
  const geography = proposal.area ? readGeographicArea(proposal.area) : readCoordinates(proposal.coordinates);
  day(proposal.date);
  const v = object(raw), r = object(v.result), { content_hash, ...body } = v;
  if (v.schema_version !== "daylight-preview-v0.1" || v.athlete_id !== owner ||
      canonical(v.request) !== canonical(proposal) || v.request_hash !== await sha(proposal) ||
      v.workouts_changed !== false || v.planning_authorized !== false || content_hash !== await sha(body) || r.method !== (proposal.area ? AREA_SOLAR_METHOD : SOLAR_METHOD)) throw invalid();
  const start = Date.parse(String(r.day_start_at)) / 1000, end = Date.parse(String(r.day_end_at)) / 1000;
  if (![start, end].every(Number.isFinite) || end <= start || end - start > 90000 ||
      localDate(start, geography.timezone_name) !== proposal.date || localDate(end - 1, geography.timezone_name) !== proposal.date ||
      localDate(start - 1, geography.timezone_name) === proposal.date || localDate(end, geography.timezone_name) === proposal.date) throw invalid();
  for (const mode of ["daylight", "civil_twilight"] as const) {
    const actual = object(r[mode]);
    if (proposal.area) {
      const expected = areaLightIntervals(start, end, proposal.area, { sport: "KAYAK", mode, start_buffer_minutes: 0, end_buffer_minutes: 0 });
      if (actual.state !== (expected.length === 1 && expected[0][0] === start && expected[0][1] === end ? "all_day" : expected.length ? "crossings" : "no_light") ||
          canonical(actual.rises_at) !== canonical(expected.filter(([a])=>a>start).map(([a])=>new Date(a*1000).toISOString().replace(".000Z","+00:00"))) ||
          canonical(actual.sets_at) !== canonical(expected.filter(([,b])=>b<end).map(([,b])=>new Date(b*1000).toISOString().replace(".000Z","+00:00"))) ||
          !Array.isArray(actual.intervals) || canonical(actual.intervals.map(x=>{const v=object(x);return [Date.parse(String(v.start_at))/1000,Date.parse(String(v.end_at))/1000];})) !== canonical(expected)) throw invalid();
      continue;
    }
    const point = proposal.coordinates;
    const calculated = solarWindows(Math.floor(start / 86400), Math.floor(end / 86400), Number(point.latitude), Number(point.longitude), mode);
    const inside = (values: number[]) => values.filter(t => start <= t && t < end).map(t => Math.round(t));
    for (const [key, values] of [["rises_at", calculated.rising], ["sets_at", calculated.setting]] as const) {
      if (!Array.isArray(actual[key]) || canonical(actual[key].map(t => Date.parse(String(t)) / 1000)) !== canonical(inside(values))) throw invalid();
    }
    const expected = lightIntervals(start, end, point, { sport: "KAYAK", mode, start_buffer_minutes: 0, end_buffer_minutes: 0 });
    const full = calculated.windows.some(([a, b]) => a <= start && b >= end);
    if (actual.state !== (full ? "all_day" : expected.length ? "crossings" : "no_light") || !Array.isArray(actual.intervals) ||
        canonical(actual.intervals.map(x => { const v = object(x); return [Date.parse(String(v.start_at)) / 1000, Date.parse(String(v.end_at)) / 1000]; })) !== canonical(expected)) throw invalid();
  }
  return r as unknown as DaylightPreview;
}
export async function loadDaylightPreview(owner: string, proposal: GeographyPreviewRequest): Promise<DaylightPreview> {
  const response = await fetch("/api/goal-workflow/training-options/daylight/preview", { method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store", body: JSON.stringify(proposal) });
  if (!response.ok) throw Error("A napfényadatok nem tölthetők be. Ellenőrizd a dátumot, koordinátákat és az időzónát.");
  return readDaylightPreview(await response.json(), owner, proposal);
}
export async function readDaylightContext(inputs: Record<string, unknown>, owner: string): Promise<OptionsData | null> {
  if (inputs.daylight_context === undefined) return null;
  const c = object(inputs.daylight_context);
  if (c.method !== SOLAR_METHOD || Object.keys(c).sort().join("|") !== "method|options_receipt") throw invalid();
  const receipt = await readOptionsReceipt(c.options_receipt, owner), artifact = receipt.artifact;
  if (canonical(inputs.training_options_reference) !== canonical({ artifact_id: artifact.artifact_id, content_hash: artifact.content_hash }) ||
      !Number.isFinite(Date.parse(String(inputs.captured_at))) || Date.parse(receipt.durable_available_at) > Date.parse(String(inputs.captured_at))) throw invalid();
  return artifact.proposal.data;
}
export function effectiveLightRule(data: OptionsData, locationId: unknown, sport: unknown): { rule?: DaylightRule; point?: Coordinates; area?: GeographicArea } {
  const location = data.locations.find(l => l.id === locationId && !l.archived);
  return { rule: location?.daylight_overrides?.find(r => r.sport === sport) ?? data.daylight_rules?.find(r => r.sport === sport), point: location?.coordinates, area: location?.area };
}
export async function validateDaylightReview(review: Record<string, unknown>) {
  if (!review.inputs || object(review.inputs).daylight_context === undefined) return;
  const inputs = object(review.inputs), data = await readDaylightContext(inputs, String(review.athlete_id));
  if (!data) return;
  const result = object(review.result), candidates = [...result.proposals as unknown[], ...((result.alternatives ?? []) as unknown[]).flatMap(g => object(g).candidates as unknown[])];
  for (const raw of candidates) {
    const c = object(raw), { rule, point, area } = effectiveLightRule(data, c.location_id, c.sport);
    if (!rule || rule.mode === "none") continue;
    const start = Date.parse(String(c.start_at)) / 1000, end = Date.parse(String(c.end_at)) / 1000;
    const allowed = area ? areaLightIntervals(start,end,area,rule) : point ? lightIntervals(start,end,point,rule) : [];
    if (!allowed.some(([a, b]) => a <= start && b >= end)) throw invalid();
    const day = (inputs.days as unknown[]).map(object).find(d => d.date === c.date);
    const group = (day?.opportunities as unknown[] | undefined)?.map(object).find(g => g.key === c.opportunity_key);
    if (!group || object(group.constraints).location_id !== c.location_id) throw invalid();
  }
}
