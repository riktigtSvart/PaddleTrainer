import { object, readReceipt } from "./contracts";
import type {
  Catalog,
  Detail,
  Page,
  Pending,
  Preview,
  Receipt,
  Program,
  BoundaryArtifact,
} from "./contracts";

const reasons: Record<string, string> = {
  ATHLETE_CONTEXT_CHANGED_REVIEW_AGAIN:
    "A sportolói felmérés vagy a naptár időközben megváltozott. Frissítsd a felmérést, vedd át a szerkesztett tervbe, majd tekintsd át újra.",
  ATHLETE_PROFILE_REQUIRED: "Először mentsd el a sportolói felmérést.",
  CYCLE_GOAL_DIRECTION_REQUIRED:
    "Jelöld ki, hogy fejleszteni vagy szinten tartani szeretnéd a képességet.",
  CYCLE_WEIGHT_GOALS_CONFLICT:
    "A testsúlycsökkentést és a megtartást egymást követő célként add meg.",
  CYCLE_GOAL_EVENTS_DIFFER:
    "A célhoz kapcsolt verseny megváltozott. Ellenőrizd a célversenyek kijelölését.",
  CYCLE_BOUNDARY_PAIR:
    "Két egymást követő, közös makrociklushoz tartozó mezociklust válassz.",
  CYCLE_BOUNDARY_RANGE:
    "A közös határ a két mezociklus időkeretén belül maradjon, és mindkettőnek maradjon legalább egy napja.",
  CYCLE_BOUNDARY_UNCHANGED: "A megadott határ nem változott.",
  CYCLE_BOUNDARY_PAST:
    "Lezárt vagy múltba kerülő határ itt nem írható át. Válassz mai vagy jövőbeli közös határt.",
  CYCLE_BOUNDARY_SOURCE_CHANGED:
    "A ciklusok jelenlegi állapota eltér a rögzített változattól. Töltsd be újra és ellenőrizd a ciklusokat.",
  CYCLE_BOUNDARY_WORKOUT_REPLAN_REQUIRED:
    "A módosítás meglévő edzést tenne a hozzárendelt cikluson kívülre. Előbb felül kell vizsgálni az érintett edzéstervet.",
  CYCLE_BOUNDARY_CHILD_REPLAN_REQUIRED:
    "A módosítás egy már hozzárendelt alárendelt ciklust tenne a mezocikluson kívülre. Előbb annak időkeretét kell felülvizsgálni.",
  CYCLE_DATE_ORDER:
    "Egy megadott zárónap korábbi a kezdőnapnál. Ellenőrizd a felkészülés, a versenyek és a ciklusok dátumait; az adatokat megőriztük.",
  CYCLE_BODY_MASS_REQUIRED:
    "Testsúlycélhoz add meg a jelenlegi és a céltestsúlyt kilogrammban.",
  CYCLE_BODY_MASS_DIRECTION:
    "Testsúlycsökkentésnél a céltestsúly legyen kisebb a jelenleginél.",
  CYCLE_EVENT_PROFILE_REQUIRED:
    "A tervezett versenyekhez add meg a szakágat, a verseny jellegét és a távot, vagy jelezd, hogy az még ismeretlen / nem értelmezhető.",
  CYCLE_RACE_TOO_CLOSE:
    "A teljes versenyfelkészüléshez legalább 28 naptári napot adj meg. A közelebbi eseményt egy meglévő felkészülés versenyeként rögzítheted.",
  CYCLE_RACE_TOO_FAR:
    "Az aktuális versenyfelkészülés legfeljebb 12 hónapos lehet. Válassz közelebbi mérföldkövet; a távlati célt a cél leírásában megőrizheted.",
  CYCLE_FIRST_SEASON_MAIN_EVENT_REQUIRED:
    "Az első szezonhoz adj meg legalább egy főversenyt, akár közelítő időablakkal.",
  CYCLE_ONE_TARGET_RACE_REQUIRED:
    "A versenyre készüléshez pontosan egy aktív főversenyt jelölj ki.",
  CYCLE_EVENT_PRECISION:
    "Pontos versenynaphoz azonos kezdő- és zárónap, közelítő időablakhoz eltérő napok szükségesek.",
  CYCLE_RACE_END_DIFFERS:
    "A felkészülés vége egyezzen a célverseny napjával vagy időablakának végével.",
  CYCLE_EVENT_OUTSIDE_PROGRAM:
    "A verseny időablaka essen a felkészülés időkeretébe. A ciklusok dátumainak áttervezése külön döntést igényel.",
  CYCLE_EVENT_OUTSIDE_SEASON:
    "A verseny teljes időablaka férjen bele egy szezonba.",
  CYCLE_MESO_COVERAGE:
    "A mezociklusok fedjék le a makrociklust hézag és átfedés nélkül.",
  CYCLE_MACRO_COVERAGE:
    "A makrociklusok fedjék le a szezonjukat hézag és átfedés nélkül.",
  CYCLE_SEASON_COVERAGE:
    "A szezonok fedjék le a teljes időkeretet hézag és átfedés nélkül.",
  CYCLE_REQUEST_IDENTITY_CONFLICT:
    "Ehhez a mentési azonosítóhoz vagy folytatási helyhez már másik kérés tartozik. Ellenőrizd a mentett előzményeket.",
  CYCLE_EVENTS_CANNOT_DISAPPEAR:
    "A korábbi versenyeket őrizzük meg. A törlés helyett jelöld az elmaradt eseményt lemondottként.",
  CYCLE_REVISION_CHAIN:
    "A pontosítás nem a megadott előző változatot követi. Töltsd be újra a programot.",
  CYCLE_REFERENCE_DIFFERS:
    "A kiválasztott előzmény és a kérés hivatkozása eltér. Töltsd be újra a programot.",
  CYCLE_OLYMPIC_HORIZON_TOO_LONG:
    "Az olimpiai időkeret legfeljebb egy olimpiai ciklust fogjon át. Válassz közelebbi játékokat vagy későbbi kezdőnapot.",
  CYCLE_OLYMPIC_END_DIFFERS:
    "Az olimpiai időkeret vége egyezzen a kiválasztott játékok zárónapjával.",
  CYCLE_CONTINUATION_OVERLAP:
    "A következő rekreációs makrociklus kezdődjön az előző befejezése után.",
};
export class CycleHTTPError extends Error {
  constructor(
    public status: number,
    public code: string,
    write: boolean,
  ) {
    super(
      reasons[code] ??
        (status === 413
          ? "A kérés túl nagy. Csökkentsd a ciklusbontás vagy a leírások méretét."
          : status === 409
            ? "A megadott ciklusszerkezet nem fogadható el. Ellenőrizd az időhatárokat és a hivatkozásokat."
            : status === 422
              ? "Ellenőrizd az űrlap kötelező mezőit és dátumait."
              : status === 404
                ? "A kiválasztott program vagy az alkalmazás tulajdonosa nem található."
                : write
                  ? "A mentés eredménye nem igazolt. Ugyanazt a kérést újra lehet küldeni."
                  : "A ciklusadatok betöltése nem sikerült.") +
          (code && !reasons[code] ? ` (${code})` : ""),
    );
  }
}
export async function request(
  path: string,
  body?: string,
  signal?: AbortSignal,
): Promise<unknown> {
  const response = await fetch("/api/goal-workflow/cycles/" + path, {
    method: body === undefined ? "GET" : "POST",
    body,
    signal,
    cache: "no-store",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
  });
  const data: unknown = await response.json();
  if (!response.ok) {
    const detail = object(data).detail;
    const code =
      detail && !Array.isArray(detail) && typeof detail === "object"
        ? String(object(detail).code ?? "")
        : "";
    throw new CycleHTTPError(response.status, code, body !== undefined);
  }
  return data;
}
export async function loadCatalog(signal?: AbortSignal): Promise<Catalog> {
  const c = object(await request("catalog", undefined, signal));
  if (
    c.schema_version !== "cycle-creation-catalog-v0.1" ||
    c.planning_context_version !== "cycle-planning-basis-v0.1" ||
    c.boundary_revision_schema !== "cycle-mesocycle-boundary-revision-v0.1" ||
    c.rules_version !== "cycle-creation-rules-v0.1" ||
    typeof c.local_today !== "string" ||
    typeof c.timezone_name !== "string" ||
    !Array.isArray(c.olympics) ||
    c.limits_are_product_policy !== true ||
    c.race_min_days !== 28 ||
    c.race_max_calendar_months !== 12 ||
    c.default_recreation_weeks !== 12 ||
    c.default_mesocycle_days !== 28
  )
    throw new Error(
      "A cikluskatalógus verziója nem támogatott. Indítsd újra az API-t és a frontendet a frissített forrásból.",
    );
  return c as Catalog;
}
export async function loadPage(
  offset = 0,
  signal?: AbortSignal,
): Promise<Page> {
  const p = object(
    await request(`programs?limit=25&offset=${offset}`, undefined, signal),
  );
  if (
    !Array.isArray(p.items) ||
    p.limit !== 25 ||
    p.offset !== offset ||
    typeof p.has_more !== "boolean" ||
    p.items.length > 25 ||
    (p.has_more && p.items.length !== 25)
  )
    throw new Error("A programlista hiányos vagy eltérő lapot adott vissza.");
  return {
    ...p,
    items: await Promise.all(p.items.map((v) => readReceipt(v))),
  } as Page;
}
export async function loadDetail(
  id: string,
  signal?: AbortSignal,
): Promise<Detail> {
  if (!/^pt-cycle:[0-9a-f]{64}$/.test(id))
    throw new Error("Érvénytelen programhivatkozás.");
  const d = object(
    await request("programs/" + encodeURIComponent(id), undefined, signal),
  );
  if (
    !Array.isArray(d.competition_revisions) ||
    d.competition_revisions.length > 64
  )
    throw new Error("Hiányos versenyelőzmények.");
  const program = await readReceipt(d.program);
  if (program.artifact.artifact_id !== id)
    throw new Error("Másik program érkezett vissza.");
  const revisions = await Promise.all(
    d.competition_revisions.map((v) =>
      readReceipt<import("./contracts").RevisionArtifact>(v),
    ),
  );
  revisions.forEach((r, i) => {
    const p = r.artifact.proposal;
    if (
      p.revision !== i + 1 ||
      p.program_reference.artifact_id !== id ||
      p.program_reference.content_hash !== program.artifact.content_hash ||
      (i === 0
        ? p.previous_reference !== null
        : p.previous_reference?.artifact_id !==
            revisions[i - 1].artifact.artifact_id ||
          p.previous_reference?.content_hash !==
            revisions[i - 1].artifact.content_hash)
    )
      throw new Error("A versenyelőzmények lánca eltér.");
  });
  if (!Array.isArray(d.boundary_revisions) || d.boundary_revisions.length > 64)
    throw new Error("Hiányos ciklushatár-előzmények.");
  const boundaries = await Promise.all(
    d.boundary_revisions.map((v) => readReceipt<BoundaryArtifact>(v)),
  );
  const events = [program.artifact, ...revisions.map((r) => r.artifact)];
  boundaries.forEach((r, i) => {
    const p = r.artifact.proposal,
      before = i ? boundaries[i - 1].artifact : null;
    if (
      p.revision !== i + 1 ||
      p.program_reference.artifact_id !== id ||
      p.program_reference.content_hash !== program.artifact.content_hash ||
      (before
        ? p.previous_reference?.artifact_id !== before.artifact_id ||
          p.previous_reference?.content_hash !== before.content_hash
        : p.previous_reference !== null) ||
      !events.some(
        (e) =>
          e.artifact_id === p.competition_reference.artifact_id &&
          e.content_hash === p.competition_reference.content_hash,
      )
    )
      throw new Error("A ciklushatár-változatok lánca eltér.");
  });
  return {
    program,
    competition_revisions: revisions,
    boundary_revisions: boundaries,
  };
}
export async function preview(program: Program): Promise<Preview> {
  const p = object(await request("preview", JSON.stringify(program)));
  if (
    p.committed !== false ||
    p.planning_authorized !== false ||
    !Array.isArray(p.periods) ||
    !p.periods.some((v) => object(v).period_type === "MACROCYCLE")
  )
    throw new Error("A cikluselőnézet nem megfelelő.");
  const { sha } = await import("./contracts");
  if (p.proposal_hash !== (await sha(program)))
    throw new Error("Az előnézet másik kéréshez tartozik.");
  return p as Preview;
}
export async function send(pending: Pending): Promise<Receipt> {
  return readReceipt(await request(pending.operation, pending.body), pending);
}
