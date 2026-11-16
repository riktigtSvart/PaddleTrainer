import { object } from "@/lib/planning-cycles/contracts";
import { gateLabels, reasonLabels } from "@/lib/athlete-setup/contracts";
import type { Context, Preparation } from "./contracts";
export type StartIssue = {
  code: string;
  title: string;
  details: string[];
  href: string;
  action: string;
};
export const entryReasons: Record<string, string> = {
  GUIDED_EXERCISE_REQUIRED:
    "Válassz konkrét, ismert gyakorlatot a kezdeti felmérés 4. lépésében.",
  GUIDED_EQUIPMENT_MISSING:
    "Ehhez a gyakorlathoz nincs megadva minden szükséges felszerelés ezen a helyszínen.",
  GUIDED_INSTRUCTION_REQUIRED:
    "Ehhez a gyakorlathoz még betanulást vagy nem tisztázott jártasságot jelöltél.",
  GUIDED_COMFORT_REVIEW:
    "Ennél a gyakorlatnál a panaszmentes végrehajtás még nincs tisztázva.",
  GUIDED_REPORTED_SYMPTOMS:
    "Ennél a gyakorlatnál panaszt rögzítettél; a kiválasztás előtt ezt kell tisztázni.",
};
export function startIssues(c: Context): StartIssue[] {
  const d = c.intake.data;
  return c.preparation.issues.map((code) => {
    const issue: StartIssue = {
      code,
      title: code,
      details: [],
      href: "/initial-assessment",
      action: "Kezdeti felmérés megnyitása",
    };
    if (code === "GUIDED_INTAKE_REQUIRED")
      issue.title = "Még nincs szerverre mentett kezdeti felmérés.";
    if (code === "GUIDED_SOURCES_CHANGED") {
      issue.title =
        "A kezdeti felmérés még a korábbi profilhoz vagy helyszíni adatokhoz tartozik.";
      issue.details = [
        "A kezdeti felmérésnél válaszd a „Friss források és mentési alap átvétele” gombot, nézd át a válaszokat, majd mentsd őket.",
      ];
      issue.href = "/initial-assessment?step=6";
    }
    if (code === "GUIDED_INTAKE_REVIEW_REQUIRED") {
      issue.title = "A kezdeti felmérés átnézése még nincs mentve.";
      issue.details = [
        "A 6. Összegzés és mentés lépésben nézd át, jelöld az átnézést, és mentsd a felmérést.",
      ];
      issue.href = "/initial-assessment?step=6";
    }
    if (code === "GUIDED_STRENGTH_ROLE_REQUIRED") {
      const role = d?.sports.find((s) => s.sport_key === "STRENGTH")?.role;
      const label = role
        ? {
            unknown: "még nem tisztázott",
            primary: "fő sportág",
            secondary: "kiegészítő sportág",
            recreation: "szabadidős",
            paused: "szüneteltetett",
          }[role]
        : "nincs kiválasztva";
      issue.title =
        "Az Erősítés / kondi fő vagy kiegészítő szerepe még nincs mentve.";
      issue.details = [
        `3. Sportágak, cél és helyszín: az Erősítés / kondi jelenlegi szerepe: ${label}.`,
        "Ha a felkészülésed része, ott válaszd ki fő vagy kiegészítő sportágként, majd mentsd a felmérést.",
      ];
      issue.href = "/initial-assessment?step=3";
      issue.action = "Sportági szerepek ellenőrzése";
    }
    if (code === "GUIDED_HISTORY_OR_SUPERVISION_REVIEW") {
      issue.title =
        "Az erőedzés-előzmények vagy a segítség kerete még nem megfelelő az indításhoz.";
      if (d?.experience === "unknown")
        issue.details.push(
          "Az erőedzésben szerzett tapasztalat még „Még nem tudom”. A korábbi edzés hiánya is érvényes válasz.",
        );
      if (d?.strength_frequency === "unknown")
        issue.details.push(
          "Az elmúlt három hónap erőedzési gyakorisága még „Még nem tudom”. A „Nem végeztem erőedzést” is érvényes válasz.",
        );
      if (d?.supervision === "unknown")
        issue.details.push(
          "A „Hogyan végezted / végeznéd az erősítést?” kérdés még nincs megválaszolva.",
        );
      if (d?.supervision === "needed")
        issue.details.push(
          "„Betanuláshoz segítségre van szükségem” választ mentettél. A felmérőfelület nem pótolja a betanítást; az önálló végrehajtás vagy a tényleges segítség keretét előbb tisztázni kell.",
        );
      issue.href = "/initial-assessment?step=2";
      issue.action = "Előzmények és segítség ellenőrzése";
    }
    if (code === "GUIDED_STATE_REVIEW") {
      issue.title =
        "A mentett állapot vagy a sportolói profil akadályozza az indítást.";
      if (d?.state_change !== "unchanged")
        issue.details.push(
          `1. Állapot és keretek: ${{ unknown: "a változás még nincs tisztázva", changed: "változást jelöltél", review_needed: "egyeztetést kértél", unchanged: "változatlan" }[d?.state_change ?? "unknown"]}.`,
        );
      const review = c.intake.sources.profile_review;
      if (review?.global_entry_gate !== "OPEN") {
        issue.details.push(
          review
            ? `Sportolói profil: ${gateLabels[review.global_entry_gate] ?? review.global_entry_gate}.`
            : "Még nincs mentett sportolói profil.",
        );
        if (review?.global_entry_gate === "OPEN_WITH_CONSTRAINTS")
          issue.details.push(
            "A profil alkalmazkodást igénylő kereteit ez az általános felmérő még nem kezeli. Ez nem hiányzó pipa; a valós korlátozásokat tartsd meg.",
          );
        const codes = review ? object(review).reasons : [];
        if (Array.isArray(codes))
          issue.details.push(
            ...codes
              .filter((v): v is string => typeof v === "string")
              .map((v) => reasonLabels[v] ?? v),
          );
        issue.href = "/athlete-setup";
        issue.action = "Sportolói profil és mozgáskeretek megnyitása";
      } else {
        issue.href = "/initial-assessment?step=1";
        issue.action = "Állapot és keretek ellenőrzése";
      }
    }
    return issue;
  });
}
export function choiceState(
  entry: Preparation["locations"][number]["entries"][number],
  entries: Preparation["locations"][number]["entries"],
  selected: string[],
) {
  const samePattern =
    !selected.includes(entry.entry_id) &&
    entries.some(
      (e) => selected.includes(e.entry_id) && e.pattern === entry.pattern,
    );
  return { selectable: entry.issues.length === 0 && !samePattern, samePattern };
}
export function requestedStep(search: string): number | null {
  const raw = new URLSearchParams(search).get("step");
  return raw !== null && /^[1-6]$/.test(raw) ? Number(raw) - 1 : null;
}
export function preparationLocation(c: Context, current?: string): string {
  const places = c.preparation.locations;
  return (
    places.find((p) => p.location_id === current)?.location_id ??
    places.find((p) => p.location_id === c.intake.data?.default_location_id)
      ?.location_id ??
    places[0]?.location_id ??
    ""
  );
}
export function retainedChoices(
  entries: Preparation["locations"][number]["entries"],
  selected: string[],
): string[] {
  const patterns = new Set<string>();
  return selected.filter((id) => {
    const e = entries.find((e) => e.entry_id === id);
    if (!e || e.issues.length || patterns.has(e.pattern)) return false;
    patterns.add(e.pattern);
    return true;
  });
}
