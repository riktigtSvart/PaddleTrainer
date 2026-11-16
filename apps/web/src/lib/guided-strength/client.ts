import { object } from "@/lib/planning-cycles/contracts";
import { readContext, readReceipt } from "./contracts";
import type { Pending } from "./contracts";
export class GuidedError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
const messages: Record<string, string> = {
  CALIBRATION_UNCONFIRMED_RESULT: "Egy próba adatai még piszkozatban vannak. Rögzítsd elvégzettként vagy vesd el a piszkozatpróbát a lezárás előtt.",
  CALIBRATION_PROTOCOL_CHANGED: "A felmérési menet változata eltér. Frissítsd az oldalt; a már mentett eredmények megmaradnak.",
  CALIBRATION_METRIC_INVALID: "Ehhez a gyakorlathoz más mérési egység tartozik. Ellenőrizd az ismétlés-, idő- és távmezőket.",
  CALIBRATION_COMPLETION_REQUIRED: "Jelöld és rögzítsd a ténylegesen elvégzett próbát, vagy hagyd a gyakorlatot függőben.",
  CALIBRATION_REPEATABILITY_UNSUPPORTED: "Az ismételt sorozatok módja dinamikus erőgyakorlathoz használható.",
  GUIDED_REVISION_CONFLICT:
    "Közben újabb állapotot mentettél. Frissítsd a szerverállapotot, és nézd át az eltérést.",
  GUIDED_PREPARATION_CHANGED:
    "A mentett kiindulóadatok megváltoztak. Frissítsd, majd ellenőrizd őket.",
  GUIDED_RECORDING_REQUIRED:
    "Válaszd ki a már rögzített teljes erőedzésedet. Órás felvételnél előbb szinkronizálj. Az eddigi sorozateredmények menthetők és folytathatók.",
  GUIDED_MANUAL_CLOCK_INVALID:
    "A valós kezdő- és záróidő legyen az alkalom kezdetétől mostanáig, legfeljebb hat órán belül.",
  GUIDED_RECORDING_ALREADY_USED:
    "Ez az órás felvétel már egy másik felméréshez tartozik.",
  GUIDED_APPLICATION_PENDING:
    "Az előző alkalom eredményeit előbb át kell venni a friss kiindulóadatokhoz.",
};
async function request(init: RequestInit = {}, suffix = "") {
  const r = await fetch("/api/goal-workflow/guided-strength" + suffix, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  let v: unknown;
  try {
    v = await r.json();
  } catch {
    throw Error("A szerver válasza nem olvasható. A függő kérés megmaradt.");
  }
  if (!r.ok) {
    const d = object(v).detail,
      code = d && typeof d === "object" ? String(object(d).code) : "";
    throw new GuidedError(
      messages[code] ??
        `A felmérés művelete nem sikerült (${code || r.status}).`,
      r.status,
    );
  }
  return v;
}
export async function loadGuided(signal?: AbortSignal) {
  return readContext(await request({ signal }));
}
export async function sendGuided(p: Pending) {
  return readReceipt(
    await request({ method: "POST", body: p.body }),
    p.owner,
    p.body,
  );
}
export async function loadGuidedRevision(id: string, owner: string) {
  const prefix = `pt-guided-strength:${owner.replaceAll("-", "")}:`;
  if (!id.startsWith(prefix) || !/^[a-f0-9]{32}$/.test(id.slice(prefix.length))) throw Error("A mentett eredmény azonosítója nem megfelelő.");
  const token = id.slice(prefix.length), uuid = `${token.slice(0, 8)}-${token.slice(8, 12)}-${token.slice(12, 16)}-${token.slice(16, 20)}-${token.slice(20)}`;
  return readReceipt(await request({}, `/revisions/${uuid}`), owner);
}
