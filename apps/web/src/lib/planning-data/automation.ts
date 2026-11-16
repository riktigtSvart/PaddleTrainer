import { canonical, object, sha, day } from "@/lib/planning-cycles/contracts";
import type { Reference } from "@/lib/planning-cycles/contracts";
import type { PlanPeriod } from "@/lib/planning-cycles/plan-view";
import { readSportAvailability } from "@/lib/planning-cycles/sport-availability";
import type { SportAvailability } from "@/lib/planning-cycles/sport-availability";

export type Setting = {
  request_id: string; previous_reference: Reference | null; program_reference: Reference | null;
  enabled: boolean; onboarding_completed: boolean;
};
export type AutomaticPolicy = Reference & {
  schema_version: "automatic-planning-v0.1"; athlete_id: string; created_at: string; revision: number;
  proposal: Setting; authority_scope: "bounded_application_training_plans" | "disabled";
  provider_writeback: false; nutrition_planning: false; personal_response_model_applied: false;
};
export type AutomaticRun = Reference & {
  sport_availability?: SportAvailability;
  athlete_id: string; created_at: string; policy_reference: Reference;
  state: "applied" | "current" | "blocked" | "completed"; blockers: string[];
  start_date: string | null; end_date: string | null;
  review_reference: Reference | null; application_reference: Reference | null;
  created_count: number; cancelled_count: number;
};
export type AutomaticContext = {
  schema_version: "automatic-planning-v0.1"; athlete_id: string; timezone_name: string;
  policy: AutomaticPolicy | null; last_run: AutomaticRun | null;
  program: { reference: Reference; title: string; start_date: string; end_date: string | null; timezone_name: string; periods: PlanPeriod[] } | null;
  automatic_review_interval_seconds: 60; supported_training_sports: string[];
  nutrition_planning_available: false; fatigue_prediction_available: false; content_hash: string;
};
export type AutomaticPending = { owner: string; body: string };
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const hash = /^[a-f0-9]{64}$/;
const check = (v: unknown) => { if (!v) throw Error("Az automatikus tervezés válasza nem ellenőrizhető."); };
export const autoKey = (owner: string) => `paddletrainer.automatic-planning.pending.v1:${owner}`;
export const ref = (v: Reference): Reference => ({ artifact_id: v.artifact_id, content_hash: v.content_hash });
function reference(value: unknown, prefix: string) {
  const v = object(value); check(typeof v.artifact_id === "string" && new RegExp(`^${prefix}:[a-f0-9]{64}$`).test(v.artifact_id) && typeof v.content_hash === "string" && hash.test(v.content_hash));
}
async function verified(value: unknown, owner: string) {
  const v = object(value), { content_hash, ...body } = v;
  check(v.schema_version === "automatic-planning-v0.1" && v.athlete_id === owner && content_hash === await sha(body));
  return v;
}
export function readSetting(value: unknown): Setting {
  const p = object(value);
  check(Object.keys(p).sort().join("|") === "enabled|onboarding_completed|previous_reference|program_reference|request_id" && typeof p.request_id === "string" && uuid.test(p.request_id) && typeof p.enabled === "boolean" && typeof p.onboarding_completed === "boolean");
  if (p.previous_reference !== null) reference(p.previous_reference, "pt-automatic");
  if (p.program_reference !== null) reference(p.program_reference, "pt-cycle");
  check(!p.enabled || p.program_reference !== null && p.onboarding_completed === true);
  return p as Setting;
}
export async function readPolicy(value: unknown, owner: string): Promise<AutomaticPolicy> {
  const p = await verified(value, owner), setting = readSetting(p.proposal);
  reference(p, "pt-automatic");
  check(p.authority_scope === (setting.enabled ? "bounded_application_training_plans" : "disabled") && p.provider_writeback === false && p.nutrition_planning === false && p.personal_response_model_applied === false && Number.isInteger(p.revision) && Number(p.revision) > 0 && typeof p.created_at === "string" && Number.isFinite(Date.parse(p.created_at)));
  return p as AutomaticPolicy;
}
export async function readAutomaticContext(value: unknown, owner: string): Promise<AutomaticContext> {
  const v = await verified(value, owner);
  check(v.automatic_review_interval_seconds === 60 && v.nutrition_planning_available === false && v.fatigue_prediction_available === false &&
    [["KAYAK", "RUNNING", "STRENGTH"], ["KAYAK", "RUNNING", "STRENGTH", "SWIMMING"]].some(sports => canonical(v.supported_training_sports) === canonical(sports)));
  new Intl.DateTimeFormat("hu", { timeZone: String(v.timezone_name) }).format();
  const policy = v.policy === null ? null : await readPolicy(v.policy, owner);
  if (v.program !== null) {
    const p = object(v.program); reference(p.reference, "pt-cycle");
    check(policy && canonical(policy.proposal.program_reference) === canonical(p.reference) && p.timezone_name === v.timezone_name && typeof p.title === "string" && Array.isArray(p.periods));
    day(String(p.start_date)); if (p.end_date !== null) { day(String(p.end_date)); check(String(p.start_date) <= String(p.end_date)); }
    for (const item of p.periods as unknown[]) { const period = object(item); check(typeof period.id === "string" && uuid.test(period.id)); day(String(period.start_date)); day(String(period.end_date)); check(String(period.start_date) <= String(period.end_date)); }
  } else check(policy === null || policy.proposal.program_reference === null);
  if (v.last_run !== null) {
    const r = await verified(v.last_run, owner); reference(r, "pt-automatic");
    if (r.sport_availability !== undefined) readSportAvailability(r.sport_availability);
    check(policy && canonical(r.policy_reference) === canonical(ref(policy)) && ["applied", "current", "blocked", "completed"].includes(String(r.state)) && Array.isArray(r.blockers) && r.blockers.every((x) => typeof x === "string") && Number.isInteger(r.created_count) && Number(r.created_count) >= 0 && Number.isInteger(r.cancelled_count) && Number(r.cancelled_count) >= 0);
    if (r.review_reference !== null) reference(r.review_reference, "pt-training-plan");
    if (r.application_reference !== null) reference(r.application_reference, "pt-training-plan");
    check(r.state !== "applied" || r.application_reference !== null);
    check(r.state !== "blocked" || (r.blockers as string[]).length > 0);
    if (r.start_date !== null || r.end_date !== null) {
      day(String(r.start_date)); day(String(r.end_date)); check(String(r.start_date) <= String(r.end_date));
      const p = object(v.program); check(String(r.start_date) >= String(p.start_date) && (p.end_date === null || String(r.end_date) <= String(p.end_date)));
    }
  }
  return v as AutomaticContext;
}
export function readAutomaticPending(raw: string, owner: string): AutomaticPending {
  const p = object(JSON.parse(raw)); check(p.owner === owner && typeof p.body === "string"); readSetting(JSON.parse(String(p.body))); return p as AutomaticPending;
}
export class AutomaticError extends Error { constructor(message: string, public status: number, public code = "") { super(message); } }
async function request(path = "", init: RequestInit = {}) {
  const response = await fetch(`/api/goal-workflow/automation${path}`, { ...init, cache: "no-store", headers: { Accept: "application/json", ...(init.body ? { "Content-Type": "application/json" } : {}) } });
  let value: unknown;
  try { value = await response.json(); } catch { throw Error("Az automatikus tervezés válasza nem olvasható; ellenőrizd a mentett állapotot."); }
  if (!response.ok) {
    const code = String(object(object(value).detail).code ?? response.status);
    const message = code === "GOAL_API_TIMEOUT" ? "A tervfrissítés visszajelzése nem érkezett meg időben. A szerver még dolgozhat; ellenőrizzük a mentett állapotot." : code === "GOAL_API_UNAVAILABLE" ? "A tervezési API nem érhető el. A legutóbbi mentett állapotot próbáljuk újraolvasni." : `Az automatikus tervezés művelete nem sikerült (${code}).`;
    throw new AutomaticError(message, response.status, code);
  }
  return value;
}
export async function loadAutomatic(owner: string, signal?: AbortSignal) { return readAutomaticContext(await request("", { signal }), owner); }
export async function saveAutomatic(pending: AutomaticPending) {
  const response = object(await request("", { method: "POST", body: pending.body }));
  check(response.committed === true && typeof response.reused === "boolean");
  const policy = await readPolicy(response.artifact, pending.owner);
  check(canonical(policy.proposal) === canonical(readSetting(JSON.parse(pending.body))));
  return policy;
}
export async function runAutomatic(owner: string) {
  const v = object(await request("/run", { method: "POST", body: "{}" }));
  const context = await readAutomaticContext(v.context, owner);
  check(v.run === null || canonical(v.run) === canonical(context.last_run));
  return context;
}
