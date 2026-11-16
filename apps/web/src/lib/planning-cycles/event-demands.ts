import data from "./event-demand-data.json";
import type { EventProfile, Program } from "./contracts";
export const demandVersion = "paddling-event-demands-v0.1";
export const demandSources = data.sources;
export function demandSuggestion(profile: EventProfile, sport = "") {
  if (profile.distance_status !== "specified" || profile.distance_value === null || !["m", "km"].includes(profile.distance_unit ?? "")) return null;
  const words = `${profile.discipline} ${sport}`.toLocaleLowerCase();
  if (/slalom|szlalom|polo|póló|wildwater|vadvíz|surfski|sárkány|dragon/.test(words) || (!/kajak|kayak|kenu|canoe/.test(words) && !/\b[kc]\s?-?\s?[124]\b/.test(words))) return null;
  const distance = Number(profile.distance_value.trim().replace(",", ".")) * (profile.distance_unit === "km" ? 1000 : 1);
  let key: keyof typeof data.values | null = null;
  if ([200, 500, 1000].includes(distance) && ["sprint", "other"].includes(profile.event_type) && !/maraton|marathon/.test(words)) key = `paddling_${distance}` as keyof typeof data.values;
  if (distance >= 5000 && distance <= 50000 && ["endurance", "mixed", "other"].includes(profile.event_type)) key = "paddling_long_distance";
  if (!key) return null;
  return { version: demandVersion, template_key: key, weights: Object.fromEntries(data.keys.map((k, i) => [k, data.values[key!][i]])) as Record<string, number> };
}
export function autoEventProfile(profile: EventProfile, sport = ""): EventProfile {
  if (profile.capability_basis === "coach_declared") return profile;
  const suggested = demandSuggestion(profile, sport);
  if (!suggested) {
    if (profile.capability_basis !== "paddling_demands_v0_1") return profile;
    const next = { ...profile, capability_basis: "unassessed" as const, capability_keys: [] }; delete next.capability_weights; return next;
  }
  return { ...profile, capability_basis: "paddling_demands_v0_1", capability_keys: Object.keys(suggested.weights), capability_weights: suggested.weights };
}
export function withEventDemands(program: Program): Program {
  return { ...program, competitions: program.competitions.map((event) => event.profile ? { ...event, profile: autoEventProfile(event.profile, program.sport) } : event) };
}
