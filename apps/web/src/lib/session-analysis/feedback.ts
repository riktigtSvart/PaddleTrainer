import { canonical, object, sha } from "@/lib/planning-cycles/contracts";
export const FEEDBACK_SCHEMA = "session-feedback-v0.1";
export const scoreKeys = ["rpe", "fatigue", "soreness", "recovery", "energy"] as const;
export const timings = ["IMMEDIATE", "NEXT_MORNING"] as const;
export type Timing = typeof timings[number];
export type Scores = Record<typeof scoreKeys[number], number | null>;
export type Proposal = Scores & {request_id: string; timing: Timing; expected_revision: number; observed_at: string; comment: string};
export type Artifact = {schema_version: string; artifact_id: string; athlete_id: string; session_id: string; proposal: Proposal; revision: number; previous_hash: string | null; submitted_at: string; timezone_name: string; content_hash: string; planning_authorized: false; provider_writeback: false};
export type Context = {schema_version: string; athlete_id: string; session_id: string; history: Artifact[]; current: Record<Timing, Artifact | null>};
export type Pending = {owner: string; session: string; body: string};
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
function requireValue(ok: unknown): asserts ok {if (!ok) throw Error("A visszajelzés válasza nem ellenőrizhető. Mentés esetén próbáld újra ugyanazt a kérést.");}
export function proposal(value: unknown): Proposal {
  const p = object(value);
  requireValue(typeof p.request_id === "string" && uuid.test(p.request_id));
  requireValue(timings.includes(p.timing as Timing) && Number.isSafeInteger(p.expected_revision) && Number(p.expected_revision) >= 0);
  requireValue(typeof p.observed_at === "string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(p.observed_at) && Number.isFinite(Date.parse(p.observed_at)));
  requireValue(typeof p.comment === "string" && Array.from(p.comment).length <= 2000);
  for (const key of scoreKeys) requireValue(p[key] === null || typeof p[key] === "number" && Number.isFinite(p[key]) && p[key] >= 0 && p[key] <= 10);
  requireValue(scoreKeys.some(k => p[k] !== null) || p.comment.trim());
  requireValue(Object.keys(p).sort().join() === [...scoreKeys, "request_id", "timing", "expected_revision", "observed_at", "comment"].sort().join());
  return p as Proposal;
}
export const storageKey = (owner: string, session: string) => `paddletrainer:feedback:v1:${owner}:${session}`;
export function readPending(raw: string, owner: string, session: string): Pending {
  const p = object(JSON.parse(raw));
  requireValue(p.owner === owner && p.session === session && typeof p.body === "string");
  proposal(JSON.parse(p.body)); return p as Pending;
}
export async function artifact(value: unknown, owner: string, session: string): Promise<Artifact> {
  const a = object(value), p = proposal(a.proposal);
  requireValue(a.schema_version === FEEDBACK_SCHEMA && a.athlete_id === owner && a.session_id === session);
  requireValue(a.revision === p.expected_revision + 1 && a.planning_authorized === false && a.provider_writeback === false);
  requireValue(typeof a.submitted_at === "string" && Number.isFinite(Date.parse(a.submitted_at)) && typeof a.timezone_name === "string");
  requireValue(a.previous_hash === null || typeof a.previous_hash === "string" && /^[a-f0-9]{64}$/.test(a.previous_hash));
  requireValue(a.artifact_id === "pt-session-feedback:" + await sha({athlete_id: owner, request_id: p.request_id}));
  const {content_hash, ...raw} = a;
  requireValue(content_hash === await sha(raw));
  return a as Artifact;
}
export async function readContext(value: unknown, owner: string, session: string): Promise<Context> {
  const x = object(value);
  requireValue(x.schema_version === FEEDBACK_SCHEMA && x.athlete_id === owner && x.session_id === session && x.planning_authorized === false && x.provider_writeback === false && Array.isArray(x.history) && x.history.length <= 2000);
  const history = await Promise.all(x.history.map(a => artifact(a, owner, session))), current = object(x.current);
  for (const timing of timings) {
    const chain = history.filter(a => a.proposal.timing === timing).sort((a,b) => a.revision-b.revision);
    chain.forEach((a,i) => requireValue(a.revision === i+1 && a.previous_hash === (i ? chain[i-1].content_hash : null)));
    requireValue(canonical(current[timing]) === canonical(chain.at(-1) ?? null));
  }
  return {...x, history} as Context;
}
export class FeedbackError extends Error {constructor(public status: number, public code: string) {super(messages[code] ?? `A visszajelzés nem menthető (${code || status}).`);}}
const messages: Record<string,string> = {
  CALENDAR_FEEDBACK_REVISION_CONFLICT: "Közben másik értékelés mentődött. Az adataid megmaradtak; olvasd újra az előzményeket, majd ellenőrzés után mentsd új javításként.",
  CALENDAR_FEEDBACK_NEXT_DAY_REQUIRED: "A másnapi értékelés megfigyelési napja az edzés befejezését követő nap legyen a profilod időzónájában.",
  CALENDAR_FEEDBACK_OBSERVATION_TIME_INVALID: "A megfigyelés az edzés vége és a jelenlegi időpont közé essen.",
  CALENDAR_FEEDBACK_HISTORY_LIMIT: "A visszajelzések előzménykorlátját elérted.",
  CALENDAR_INPUT_INVALID: "Ellenőrizd a pontszámokat, az időpontot és a megjegyzés hosszát.",
};
async function request(session: string, body?: string, signal?: AbortSignal) {
  requireValue(uuid.test(session));
  const r = await fetch(`/api/calendar/sessions/${session}/feedback`, {method: body ? "POST" : "GET", body, signal, cache:"no-store", headers:{Accept:"application/json", ...(body ? {"Content-Type":"application/json"} : {})}});
  let value: unknown; try {value = await r.json();} catch {throw Error("A válasz nem olvasható; a mentés eredménye még nem ismert.");}
  if (!r.ok) {let code=""; try {code=String(object(object(value).detail).code ?? "");} catch {} throw new FeedbackError(r.status,code);}
  return value;
}
export async function loadFeedback(owner: string, session: string, signal?: AbortSignal) {return readContext(await request(session,undefined,signal),owner,session);}
export async function sendFeedback(p: Pending) {
  const x=object(await request(p.session,p.body)), a=await artifact(x.artifact,p.owner,p.session);
  requireValue(x.committed === true && typeof x.reused === "boolean" && typeof x.durable_available_at === "string" && Number.isFinite(Date.parse(x.durable_available_at)));
  requireValue(canonical(a.proposal) === canonical(proposal(JSON.parse(p.body))));
  return a;
}
export function score(value: string): number | null {
  if (value === "") return null;
  if (!/^(?:\d(?:[.,]\d)?|10(?:[.,]0)?)$/.test(value)) throw Error("A pontszám 0–10 közötti szám legyen, legfeljebb egy tizedessel.");
  return Number(value.replace(",","."));
}
