import { object } from "@/lib/planning-cycles/contracts";
import { readAssessmentReceipt, readContext } from "./contracts";
import type { Pending } from "./contracts";

export class AssessmentError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
const messages: Record<string, string> = {
  INITIAL_ASSESSMENT_REVISION_CONFLICT:
    "Közben új felmérés került mentésre. Olvasd újra, és nézd át a módosításokat.",
  INITIAL_ASSESSMENT_REQUEST_CONFLICT:
    "Ezzel a kérésazonosítóval már más tartalom került mentésre.",
  INITIAL_ASSESSMENT_SOURCES_CHANGED:
    "A profil, helyszínek vagy felkészülések megváltoztak. A friss forrásokkal újra át kell nézni a felmérést.",
  INITIAL_ASSESSMENT_DATE_OR_ZONE_INVALID:
    "A felmérés dátuma vagy időzónája nem megfelelő.",
};
async function request(init: RequestInit = {}, suffix = "") {
  const response = await fetch("/api/goal-workflow/initial-assessment" + suffix, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw Error("A válasz nem olvasható; a mentés eredménye még nem ismert.");
  }
  if (!response.ok) {
    const d = object(value).detail;
    const code =
      d && typeof d === "object" && !Array.isArray(d)
        ? String(object(d).code)
        : "";
    throw new AssessmentError(
      messages[code] ??
        `A felmérés művelete nem sikerült (${code || response.status}).`,
      response.status,
    );
  }
  return value;
}
export async function loadAssessment(signal?: AbortSignal) {
  return readContext(await request({ signal }));
}
export async function loadAssessmentRevision(owner: string, token: string, signal?: AbortSignal) {
  if (!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(token))
    throw Error("A korábbi felmérés azonosítója nem ellenőrizhető.");
  try {
    const receipt = await readAssessmentReceipt(await request({ signal }, "/revisions/" + token), owner);
    if (receipt.artifact.proposal.request_id !== token)
      throw Error("Másik felmérés visszaigazolása érkezett.");
    return receipt;
  } catch (e) {
    if (e instanceof AssessmentError && e.status === 404) return null;
    throw e;
  }
}
export async function sendAssessment(pending: Pending) {
  return readAssessmentReceipt(
    await request({ method: "POST", body: pending.body }),
    pending.owner,
    pending.body,
  );
}
