import { canonical, day, object, sha } from "@/lib/planning-cycles/contracts";
import { readDetails } from "@/lib/calendar/constraints";

export const sportLabels = {
  KAYAK: "Kajak",
  RUNNING: "Futás",
  SWIMMING: "Úszás",
  STRENGTH: "Kondi",
  CYCLING: "Kerékpár",
  GYMNASTICS: "Gimnasztika",
  STRETCHING: "Nyújtás",
} as const;
export type Sport = keyof typeof sportLabels;
export type Location = {
  id: string;
  name: string;
  kind: "fixed" | "mobile";
  sports: Sport[];
  resources: string[];
  combine_allowed: boolean;
  boat_transport: boolean;
  notes: string;
  archived: boolean;
};
export type SlotDetails = {
  start_time: string;
  end_time: string;
  ends_next_day: boolean;
  start_fold: 0 | 1 | null;
  end_fold: 0 | 1 | null;
  max_minutes: number;
  location_ids: string[];
  effort_cap: "easy" | "moderate" | "any";
  combine_allowed: boolean;
  notes: string;
};
export type WeeklySlot = {
  id: string;
  start_date: string;
  end_date: string | null;
  weekdays: number[];
  details: SlotDetails;
};
export type SlotException = {
  slot_id: string;
  date: string;
  replacement: SlotDetails | null;
};
export type LocationRestriction = {
  id: string;
  location_id: string;
  start_date: string;
  end_date: string;
  unavailable_sports: Sport[];
  reason: string;
};
export type OptionsData = {
  timezone_name: string;
  schedule_start_date: string | null;
  schedule_end_date: string | null;
  locations: Location[];
  weekly_slots: WeeklySlot[];
  exceptions: SlotException[];
  restrictions: LocationRestriction[];
};
export type OptionsReference = { artifact_id: string; content_hash: string };
export type OptionsProposal = {
  request_id: string;
  previous_reference: OptionsReference | null;
  data: OptionsData;
};
export type OptionsReceipt = {
  identity_scope: "APPLICATION_DEMO_USER";
  artifact: {
    schema_version: "training-options-v0.1";
    artifact_id: string;
    athlete_id: string;
    created_at: string;
    revision: number;
    content_hash: string;
    proposal: OptionsProposal;
    planning_authorized: false;
    workouts_changed: false;
  };
  durable_available_at: string;
  committed: true;
  reused: boolean;
  planning_authorized: false;
  workouts_changed: false;
};
export type ResolvedGroup = {
  key: string;
  slot_id: string;
  date: string;
  overridden: boolean;
  details: SlotDetails | null;
  alternatives: {
    location_id: string;
    name: string;
    sports: Sport[];
    resources: string[];
    combine_allowed: boolean;
    issues: string[];
    restrictions: LocationRestriction[];
  }[];
};
export type OptionsContext = {
  schema_version: "training-options-v0.1";
  athlete_id: string;
  timezone_name: string;
  local_today: string;
  start_date: string;
  end_date: string;
  data: OptionsData;
  saved: OptionsReceipt | null;
  reference: OptionsReference | null;
  groups: ResolvedGroup[];
  override_days: string[];
  timezone_review_required: boolean;
  workouts_changed: false;
  planning_authorized: false;
};
export type OptionsPending = {
  version: "training-options-pending-v0.1";
  owner: string;
  body: string;
};
export const PENDING_KEY = "paddletrainer.training-options.pending.v1";
export const OPTIONS_UPDATED = "paddletrainer:training-options-updated";
export const weekdayLabels = [
  "Hétfő",
  "Kedd",
  "Szerda",
  "Csütörtök",
  "Péntek",
  "Szombat",
  "Vasárnap",
];
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const identity = /^pt-training-options:[0-9a-f]{32}:[0-9a-f]{32}$/;
const hash = /^[0-9a-f]{64}$/;
function requireValue(value: unknown): asserts value {
  if (!value)
    throw Error(
      "Az edzési lehetőségek válasza hiányos vagy nem egyezik a mentett kéréssel.",
    );
}
function text(value: unknown, max: number): value is string {
  return typeof value === "string" && value.length <= max;
}
function validDay(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    day(value);
    return value >= "1900-01-01" && value <= "2100-12-31";
  } catch {
    return false;
  }
}
function unique(values: unknown, max: number): values is unknown[] {
  return (
    Array.isArray(values) &&
    values.length <= max &&
    new Set(values).size === values.length
  );
}
function slotDetails(value: unknown, locations: Set<string>): SlotDetails {
  const v = object(value);
  requireValue(
    unique(v.location_ids, 32) &&
      v.location_ids.length > 0 &&
      v.location_ids.every(
        (id) => typeof id === "string" && locations.has(id),
      ) &&
      ["easy", "moderate", "any"].includes(String(v.effort_cap)) &&
      typeof v.combine_allowed === "boolean" &&
      text(v.notes, 2000),
  );
  readDetails({
    ...v,
    kind: "available",
    category: "training",
    title: "Edzéslehetőség",
    firmness: "flexible",
    sport_scope: "any",
    sports: [],
    resources: [],
    location: "",
  });
  return v as SlotDetails;
}
export function readOptionsData(value: unknown): OptionsData {
  const v = object(value);
  requireValue(typeof v.timezone_name === "string");
  new Intl.DateTimeFormat("hu-HU", { timeZone: v.timezone_name });
  requireValue(
    (v.schedule_start_date === null || validDay(v.schedule_start_date)) &&
      (v.schedule_end_date === null ||
        (validDay(v.schedule_end_date) &&
          typeof v.schedule_start_date === "string" &&
          v.schedule_end_date >= v.schedule_start_date)),
  );
  requireValue(
    Array.isArray(v.locations) &&
      v.locations.length <= 64 &&
      Array.isArray(v.weekly_slots) &&
      v.weekly_slots.length <= 128 &&
      Array.isArray(v.exceptions) &&
      v.exceptions.length <= 1024 &&
      Array.isArray(v.restrictions) &&
      v.restrictions.length <= 256,
  );
  const ids = new Set<string>(),
    names = new Set<string>();
  for (const item of v.locations) {
    const location = object(item);
    requireValue(
      typeof location.id === "string" &&
        uuid.test(location.id) &&
        !ids.has(location.id) &&
        text(location.name, 100) &&
        !!location.name &&
        location.name.trim() === location.name &&
        ["fixed", "mobile"].includes(String(location.kind)) &&
        unique(location.sports, 7) &&
        location.sports.length > 0 &&
        location.sports.every(
          (s) => typeof s === "string" && s in sportLabels,
        ) &&
        unique(location.resources, 32) &&
        location.resources.every(
          (r) => text(r, 200) && !!r && r === r.trim(),
        ) &&
        typeof location.combine_allowed === "boolean" &&
        typeof location.boat_transport === "boolean" &&
        typeof location.archived === "boolean" &&
        text(location.notes, 2000),
    );
    ids.add(location.id);
    if (!location.archived) {
      const name = location.name.toLocaleLowerCase("hu");
      requireValue(!names.has(name));
      names.add(name);
    }
  }
  const slots = new Map<string, WeeklySlot>();
  requireValue(!v.weekly_slots.length || v.schedule_start_date !== null);
  for (const item of v.weekly_slots) {
    const s = object(item);
    requireValue(
      typeof s.id === "string" &&
        uuid.test(s.id) &&
        !slots.has(s.id) &&
        validDay(s.start_date) &&
        (s.end_date === null ||
          (validDay(s.end_date) && s.end_date >= s.start_date)) &&
        unique(s.weekdays, 7) &&
        s.weekdays.length > 0 &&
        s.weekdays.every(
          (d, i, values) =>
            Number.isInteger(d) &&
            Number(d) >= 0 &&
            Number(d) <= 6 &&
            (i === 0 || Number(values[i - 1]) < Number(d)),
        ),
    );
    slotDetails(s.details, ids);
    slots.set(s.id, s as WeeklySlot);
  }
  const seen = new Set<string>();
  for (const item of v.exceptions) {
    const e = object(item),
      s = slots.get(String(e.slot_id));
    requireValue(
      s &&
        validDay(e.date) &&
        e.date >= s.start_date &&
        (!s.end_date || e.date <= s.end_date) &&
        s.weekdays.includes(
          (new Date(e.date + "T12:00:00Z").getUTCDay() + 6) % 7,
        ) &&
        !seen.has(e.slot_id + ":" + e.date),
    );
    seen.add(e.slot_id + ":" + e.date);
    if (e.replacement !== null) slotDetails(e.replacement, ids);
  }
  const restrictions = new Set();
  for (const item of v.restrictions) {
    const r = object(item);
    requireValue(
      typeof r.id === "string" &&
        uuid.test(r.id) &&
        !restrictions.has(r.id) &&
        ids.has(String(r.location_id)) &&
        validDay(r.start_date) &&
        validDay(r.end_date) &&
        r.start_date <= r.end_date &&
        unique(r.unavailable_sports, 7) &&
        r.unavailable_sports.length > 0 &&
        r.unavailable_sports.every(
          (s) => typeof s === "string" && s in sportLabels,
        ) &&
        text(r.reason, 1000),
    );
    restrictions.add(r.id);
  }
  return v as OptionsData;
}
export function readProposal(value: unknown): OptionsProposal {
  const v = object(value);
  requireValue(typeof v.request_id === "string" && uuid.test(v.request_id));
  if (v.previous_reference !== null) {
    const r = object(v.previous_reference);
    requireValue(
      typeof r.artifact_id === "string" &&
        identity.test(r.artifact_id) &&
        typeof r.content_hash === "string" &&
        hash.test(r.content_hash),
    );
  }
  readOptionsData(v.data);
  return v as OptionsProposal;
}
export async function readOptionsReceipt(
  value: unknown,
  owner?: string,
  body?: string,
): Promise<OptionsReceipt> {
  const r = object(value),
    a = object(r.artifact);
  requireValue(
    r.identity_scope === "APPLICATION_DEMO_USER" &&
      r.committed === true &&
      typeof r.reused === "boolean" &&
      r.planning_authorized === false &&
      r.workouts_changed === false &&
      a.schema_version === "training-options-v0.1" &&
      typeof a.athlete_id === "string" &&
      uuid.test(a.athlete_id) &&
      (!owner || a.athlete_id === owner) &&
      typeof a.artifact_id === "string" &&
      identity.test(a.artifact_id) &&
      typeof a.content_hash === "string" &&
      hash.test(a.content_hash) &&
      Number.isInteger(a.revision) &&
      Number(a.revision) >= 1 &&
      a.planning_authorized === false &&
      a.workouts_changed === false &&
      typeof a.created_at === "string" &&
      Number.isFinite(Date.parse(a.created_at)) &&
      typeof r.durable_available_at === "string" &&
      Number.isFinite(Date.parse(r.durable_available_at)),
  );
  const p = readProposal(a.proposal);
  requireValue(
    a.artifact_id ===
      "pt-training-options:" +
        a.athlete_id.replaceAll("-", "") +
        ":" +
        p.request_id.replaceAll("-", "") &&
      (Number(a.revision) === 1) === (p.previous_reference === null),
  );
  const { content_hash, ...raw } = a;
  requireValue(
    (await sha(raw)) === content_hash &&
      (!body || canonical(p) === canonical(readProposal(JSON.parse(body)))),
  );
  return r as OptionsReceipt;
}
export async function readOptionsContext(
  value: unknown,
): Promise<OptionsContext> {
  const c = object(value);
  requireValue(
    c.schema_version === "training-options-v0.1" &&
      typeof c.athlete_id === "string" &&
      uuid.test(c.athlete_id) &&
      typeof c.timezone_name === "string" &&
      validDay(c.local_today) &&
      validDay(c.start_date) &&
      validDay(c.end_date) &&
      c.start_date <= c.end_date &&
      typeof c.timezone_review_required === "boolean" &&
      c.planning_authorized === false &&
      c.workouts_changed === false &&
      Array.isArray(c.groups) &&
      unique(c.override_days, 367) &&
      c.override_days.every(validDay),
  );
  const data = readOptionsData(c.data);
  if (c.saved !== null) {
    const saved = await readOptionsReceipt(c.saved, c.athlete_id);
    requireValue(
      canonical(c.reference) ===
        canonical({
          artifact_id: saved.artifact.artifact_id,
          content_hash: saved.artifact.content_hash,
        }) && canonical(data) === canonical(saved.artifact.proposal.data),
    );
  } else requireValue(c.reference === null);
  const locations = new Map(data.locations.map((l) => [l.id, l]));
  for (const item of c.groups) {
    const g = object(item);
    requireValue(
      typeof g.key === "string" &&
        typeof g.slot_id === "string" &&
        data.weekly_slots.some((s) => s.id === g.slot_id) &&
        validDay(g.date) &&
        typeof g.overridden === "boolean" &&
        Array.isArray(g.alternatives),
    );
    if (g.details !== null) slotDetails(g.details, new Set(locations.keys()));
    for (const item of g.alternatives) {
      const a = object(item),
        location = locations.get(String(a.location_id));
      requireValue(
        location &&
          a.name === location.name &&
          Array.isArray(a.sports) &&
          a.sports.every((s) => location.sports.includes(s as Sport)) &&
          canonical(a.resources) === canonical(location.resources) &&
          typeof a.combine_allowed === "boolean" &&
          Array.isArray(a.issues) &&
          a.issues.every((x) => typeof x === "string") &&
          Array.isArray(a.restrictions),
      );
    }
  }
  return c as OptionsContext;
}
export function readPending(value: string): OptionsPending {
  const p = object(JSON.parse(value));
  requireValue(
    p.version === "training-options-pending-v0.1" &&
      typeof p.owner === "string" &&
      uuid.test(p.owner) &&
      typeof p.body === "string",
  );
  readProposal(JSON.parse(p.body));
  return p as OptionsPending;
}
export function emptyLocation(): Location {
  return {
    id: crypto.randomUUID(),
    name: "",
    kind: "fixed",
    sports: [],
    resources: [],
    combine_allowed: false,
    boat_transport: false,
    notes: "",
    archived: false,
  };
}
export function defaultSlot(today: string): WeeklySlot {
  return {
    id: crypto.randomUUID(),
    start_date: today,
    end_date: null,
    weekdays: [0],
    details: {
      start_time: "18:00",
      end_time: "19:00",
      ends_next_day: false,
      start_fold: null,
      end_fold: null,
      max_minutes: 60,
      location_ids: [],
      effort_cap: "any",
      combine_allowed: false,
      notes: "",
    },
  };
}
