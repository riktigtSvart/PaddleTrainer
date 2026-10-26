import { canonical, object, sha } from "@/lib/planning-cycles/contracts";
import { send } from "@/lib/athlete-setup/client";
import { requireValue } from "./contracts";
import { readScheduleContext, readScheduleReceipt } from "./constraints";
import type { EditorPending, Proposal } from "./constraints";

export class ConstraintHTTPError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
const labels: Record<string, string> = {
  ATHLETE_WINDOW_DURATION_INVALID: "Az edzéspercek nem férnek az időablakba. Növeld az ablak hosszát, vagy csökkentsd az edzéskeretet.",
  ATHLETE_DAILY_BUDGET_INVALID: "A napi edzéskeret nagyobb a megmaradó ablakok kereténél. Pontosítsd a napi keretet.",
  ATHLETE_WINDOWS_OVERLAP: "A megadott edzésablakok átfedik egymást. Pontosítsd az időpontokat.",
  ATHLETE_TIME_DOES_NOT_EXIST: "Az óraátállítás miatt ez a helyi időpont nem létezik.",
  ATHLETE_TIME_IS_AMBIGUOUS: "Ismétlődő óra: válaszd ki az első vagy második előfordulást a részleteknél.",
  CALENDAR_CONSTRAINT_REVISION_CONFLICT: "A napirend közben megváltozott. Olvasd újra, és tekintsd át a módosítást.",
  CALENDAR_CONSTRAINT_AVAILABILITY_CHANGED: "Az edzéslehetőségek közben megváltoztak. Olvasd újra a naptárt.",
  CALENDAR_CONSTRAINT_TIMEZONE_CHANGED: "Megváltozott az időzóna. A helyi időpontokat felül kell vizsgálni.",
  CALENDAR_CONSTRAINT_RANGE_TOO_DENSE: "Túl sok esemény érinti ezt az időszakot. Válassz rövidebb nézetet.",
};
async function request(path: string, init?: RequestInit) {
  const response = await fetch("/api/calendar/constraints" + path, {
    ...init, cache: "no-store", headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
  });
  let value: unknown;
  try { value = await response.json(); }
  catch { throw new Error("A válasz nem olvasható. Mentés esetén az eredmény még nem ismert."); }
  if (!response.ok) {
    const d = object(value).detail;
    const code = d && typeof d === "object" ? String(object(d).code) : "";
    throw new ConstraintHTTPError(labels[code] ?? `A napirendi művelet nem sikerült (${code || response.status}).`, response.status);
  }
  return value;
}
export async function loadConstraints(range: { start: string; end: string } | null, signal?: AbortSignal) {
  const result = await readScheduleContext(await request(range ? "?" + new URLSearchParams({ start_date: range.start, end_date: range.end }) : "", { signal }));
  if (range) requireValue(result.start_date === range.start && result.end_date === range.end);
  requireValue(result.proposal_hash === null && result.availability_proposal_hash === null);
  return result;
}
export async function previewConstraints(proposal: Proposal, owner: string, first: string, last: string, availability?: unknown) {
  const result = await readScheduleContext(await request("/preview", {
    method: "POST", body: JSON.stringify({ proposal, start_date: first, end_date: last, availability_proposal: availability ?? null }),
  }));
  requireValue(result.athlete_id === owner && result.start_date === first && result.end_date === last &&
    result.proposal_hash === await sha(proposal) && canonical(result.data) === canonical(proposal.data) &&
    result.availability_proposal_hash === (availability ? await sha(availability) : null));
  return result;
}
export async function sendEditor(pending: EditorPending) {
  if (pending.operation === "constraints")
    return readScheduleReceipt(await request("", { method: "POST", body: pending.body }), pending.owner, pending.body);
  const receipt = await send({ schema_version: "athlete-pending-v0.1", operation: "availability", body: pending.body });
  requireValue(receipt.artifact.athlete_id === pending.owner, "A mentési bizonylat másik sportolóhoz tartozik.");
  return receipt;
}
