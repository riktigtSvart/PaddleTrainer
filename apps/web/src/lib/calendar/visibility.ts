import type { Span } from "./contracts";

export const visibilityLayers = ["availability", "commitments", "planned", "sessions", "preparation", "state"] as const;
export type VisibilityLayer = typeof visibilityLayers[number];
export type WeekStart = "monday" | "microcycle";
export type Visibility = { layers: Record<VisibilityLayer, boolean>; fullDay: boolean; cycleLoad: boolean; weekStart?: WeekStart };
export function defaultVisibility(): Visibility {
  return { layers: { availability: true, commitments: true, planned: true, sessions: true, preparation: true, state: false }, fullDay: false, cycleLoad: false };
}
export function visibilityKey(owner: string | null, span: Span) {
  return owner && [1, 7, 28, 168].includes(span) ? `paddletrainer.calendar.visibility.v1:${owner}:${span}` : null;
}
export function readVisibility(raw: string | null, owner: string, span: Span): Visibility {
  if (raw === null) return defaultVisibility();
  const value = JSON.parse(raw);
  if (!value || value.schema_version !== "calendar-visibility-v0.1" || value.owner !== owner || value.span !== span ||
      !value.layers || typeof value.layers !== "object" || Array.isArray(value.layers) ||
      visibilityLayers.some(key => typeof value.layers[key] !== "boolean") || typeof value.fullDay !== "boolean" || (value.cycleLoad !== undefined && typeof value.cycleLoad !== "boolean") || (value.weekStart!==undefined&&!["monday","microcycle"].includes(value.weekStart)))
    throw Error("A naptári nézet mentett beállítása nem olvasható.");
  return { layers: Object.fromEntries(visibilityLayers.map(key => [key, value.layers[key]])) as Visibility["layers"], fullDay: value.fullDay, cycleLoad: value.cycleLoad ?? false, ...(value.weekStart!==undefined?{weekStart:value.weekStart}:{}) };
}
export function writeVisibility(owner: string, span: Span, value: Visibility) {
  return JSON.stringify({ schema_version: "calendar-visibility-v0.1", owner, span, ...value });
}
