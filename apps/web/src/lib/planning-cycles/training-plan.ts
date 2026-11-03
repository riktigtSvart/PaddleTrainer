import { object, sha } from "./contracts";
import type { Reference } from "./contracts";
import { request } from "./client";
import type { Constraint } from "@/lib/athlete-setup/contracts";

export type Candidate = {
  candidate_key: string;
  template_key: string;
  date: string;
  start_at: string;
  end_at: string;
  duration_sec: number;
  title: string;
  description: string;
  capability_key: string;
  role: string;
  rationale: string;
  sport?: string;
  location?: string;
  location_id?: string;
  opportunity_key?: string;
  blocks?: {
    position: number;
    block_type: string;
    name: string;
    duration_sec: number | null;
    distance_m: number | null;
  }[];
};
export type AlternativeGroup = {
  date: string;
  recommended_candidate_key: string;
  selected_candidate_key: string | null;
  candidates: Candidate[];
};
export type TrainingEvent = {
  kind: string;
  workout_id: string | null;
  session_id?: string;
  title?: string;
  sport?: string;
  started_at?: string | null;
  date?: string;
  workout_hash?: string;
  can_confirm_missed?: boolean;
};
export type EntryReview = {
  global_entry_gate: string;
  participation_status: string;
  reasons: string[];
  constraints?: Constraint[];
};
export type EventSource = {
  id: string;
  name?: string | null;
  sport?: string;
  started_at?: string | null;
  date?: string;
};
export type Preparation = {
  version: "training-preparation-v0.1";
  available_days_per_week: number | null;
  available_minutes_per_week: number | null;
  max_sessions_per_7_days: number;
  max_minutes_per_7_days: number;
  equipment_declared: boolean;
  available_day_count: number;
  strategy_ready?: boolean;
  reference_templates: string[];
  selection_issues: { date: string; codes: string[] }[];
  unknown_duration_workout_ids: string[];
  estimated_duration_workout_ids: string[];
};
export type TrainingReview = {
  artifact_id: string;
  content_hash: string;
  athlete_id: string;
  program_id: string;
  created_at: string;
  start_date: string;
  end_date: string;
  timezone_name: string;
  program_reference: Reference;
  inputs?: {
    recent_sessions?: EventSource[];
    periods?: {
      id: string;
      period_type: string;
      title: string;
      start_date: string;
      end_date: string;
      parent_id?: string | null;
    }[];
    days?: { date: string; availability_state: string }[];
  };
  selection_preferences?: Record<
    string,
    { template_key: string; opportunity_key: string }
  >;
  plan_snapshots: {
    workout: {
      id: string;
      title: string;
      sport?: string;
      planned_start_time?: string | null;
      date?: string;
      duration_sec?: number | null;
      description?: string | null;
      status?: string;
      blocks?: Candidate["blocks"];
    };
    candidate_key?: string | null;
    replaceable?: boolean;
    linked?: boolean;
    duration_estimate?: { duration_sec: number; upper_sec: number } | null;
  }[];
  result: {
    preparation?: Preparation;
    entry_review?: EntryReview | null;
    blockers: string[];
    events: TrainingEvent[];
    proposals: Candidate[];
    alternatives?: AlternativeGroup[];
    unavailable_alternatives?: {
      date: string;
      opportunity_key: string;
      location_id: string;
      location: string;
      codes: string[];
    }[];
    create: Candidate[];
    keep: string[];
    cancel: string[];
    protected_workout_ids: string[];
    days_without_proposal: { date: string; reason: string }[];
    uncovered_capabilities: string[];
    personal_model_applied: false;
    automatic_plan_mutation: false;
  };
};
export type Acceptance = {
  artifact_id: string;
  content_hash: string;
  program_id: string;
  athlete_id: string;
  start_date: string;
  end_date: string;
  review_reference: Reference;
  created_workouts: Record<string, unknown>;
  cancelled_workout_ids: string[];
  kept_workout_ids: string[];
  proposal: Record<string, unknown>;
};
export type TrainingPending = {
  owner: string;
  program: string;
  operation: "accept" | "missed";
  body: string;
};
export const trainingReasons: Record<string, string> = {
  SELECTED_ALTERNATIVE_NO_LONGER_AVAILABLE:
    "Egy korábban választott változat a friss keretek között már nem használható. Válassz új lehetőséget az érintett napon.",
  PROFILE_REVIEW_REQUIRED:
    "A sportolói felmérést előbb ki kell egészíteni vagy felül kell vizsgálni.",
  RETURNING_ATHLETE_REVIEW:
    "Visszatéréshez még egyéni kezdőterhelést kell meghatározni.",
  PROGRAM_SPORT_NOT_SUPPORTED:
    "Ehhez a sporthoz még nincs bekötött edzésminta. Jelenleg kajakos felkészüléshez készülhet terv.",
  CURRENT_ILLNESS_REVIEW:
    "A friss betegségjelzés miatt előbb állapotfelülvizsgálat szükséges.",
  ACCEPTED_WINDOW_ENDED:
    "Az elfogadott tervidőszak véget ért. Új időszakra külön készíthetsz javaslatot.",
  NO_KNOWN_OPPORTUNITY: "Nincs ismert, használható időlehetőség.",
  CAPABILITY_ROLES_REQUIRED: "Előbb mentsd el a mezociklus képességszerepeit.",
  EXISTING_TRAINING_PRESERVED:
    "Meglévő terv vagy teljesítés mellett nem teszünk ide új edzést.",
  RECENT_EXECUTION_REVIEW:
    "Egy közelmúltbeli edzés teljesítése még nem tisztázott.",
  RECOVERY_REVIEW:
    "A friss visszajelzés alapján a közeli edzések felülvizsgálandók.",
  EVENT_PHASE_REVIEW:
    "Verseny előtti vagy átvezető szakasz: külön napi tervfelülvizsgálat szükséges.",
  COMPETITION_DAY_PRESERVED: "Erre a napra verseny van megadva.",
  NO_SUPPORTED_SAMPLE_FITS:
    "Nem illeszkedik támogatott minta az ismert célhoz, eszközhöz, sporthoz vagy terhelési és időkerethez.",
  PROGRAM_TIMEZONE_REVIEW:
    "A felkészülés és a jelenlegi naptár időzónáját egyeztetni kell.",
  GOAL_SOURCE_SNAPSHOT_CHANGED:
    "A ciklusadatok a célmentés óta megváltoztak; a célokat felül kell vizsgálni.",
};
export const eventLabels: Record<string, string> = {
  planned_completed: "Tervezett és teljesített edzés",
  unplanned_completed: "Nem tervezett, teljesített edzés",
  confirmed_missed: "Megerősített kihagyás",
  reported_completed:
    "Teljesítettnek jelölt terv; a mért teljesítés külön adat",
  execution_unknown: "Lejárt terv; a teljesítés még nem igazolt",
  execution_incomplete: "A teljesítés adatai még hiányosak",
};

async function verify(value: unknown, owner: string, program: string) {
  const v = object(value),
    { content_hash, ...body } = v;
  if (
    v.schema_version !== "training-plan-v0.1" ||
    v.athlete_id !== owner ||
    v.program_id !== program ||
    typeof v.artifact_id !== "string" ||
    !/^pt-training-plan:[0-9a-f]{64}$/.test(v.artifact_id) ||
    typeof content_hash !== "string" ||
    (await sha(body)) !== content_hash
  )
    throw Error(
      "A tervváltozat tulajdonosa, hivatkozása vagy tartalomlenyomata eltér.",
    );
  return v;
}

export async function readTrainingReview(
  value: unknown,
  expected: { owner: string; reference: Reference; zone: string },
) {
  const v = await verify(value, expected.owner, expected.reference.artifact_id),
    r = object(v.result),
    p = object(v.program_reference);
  if (
    v.timezone_name !== expected.zone ||
    p.artifact_id !== expected.reference.artifact_id ||
    p.content_hash !== expected.reference.content_hash ||
    v.committed_plan !== false ||
    v.requires_explicit_acceptance !== true ||
    r.personal_model_applied !== false ||
    r.automatic_plan_mutation !== false ||
    !Array.isArray(v.plan_snapshots) ||
    typeof v.start_date !== "string" ||
    typeof v.end_date !== "string" ||
    typeof v.created_at !== "string" ||
    !Number.isFinite(Date.parse(v.created_at))
  )
    throw Error("A tervjavaslat hatásköre vagy programja eltér.");
  for (const key of [
    "proposals",
    "create",
    "keep",
    "cancel",
    "blockers",
    "events",
    "days_without_proposal",
    "uncovered_capabilities",
    "protected_workout_ids",
  ])
    if (!Array.isArray(r[key]))
      throw Error("A tervjavaslat felsorolása hiányos.");
  if (r.entry_review !== undefined && r.entry_review !== null) {
    const entry = object(r.entry_review);
    if (
      typeof entry.global_entry_gate !== "string" ||
      typeof entry.participation_status !== "string" ||
      !Array.isArray(entry.reasons) ||
      entry.reasons.some((reason) => typeof reason !== "string") ||
      (entry.constraints !== undefined && !Array.isArray(entry.constraints))
    )
      throw Error("A profil felülvizsgálati indokai hiányosak.");
  }
  const days =
    (Date.parse(String(v.end_date)) - Date.parse(String(v.start_date))) /
      86400000 +
    1;
  if (!Number.isInteger(days) || days < 1 || days > 366)
    throw Error("A tervjavaslat dátumtartománya hibás.");
  const known = new Set(
    (v.plan_snapshots as unknown[]).map((item) =>
      String(object(object(item).workout).id),
    ),
  );
  if (r.preparation !== undefined) {
    const prep = object(r.preparation);
    if (
      prep.version !== "training-preparation-v0.1" ||
      typeof prep.equipment_declared !== "boolean" ||
      (prep.strategy_ready !== undefined &&
        typeof prep.strategy_ready !== "boolean") ||
      !Number.isInteger(prep.available_day_count) ||
      Number(prep.available_day_count) < 0 ||
      Number(prep.available_day_count) > days ||
      !Number.isInteger(prep.max_sessions_per_7_days) ||
      Number(prep.max_sessions_per_7_days) < 0 ||
      Number(prep.max_sessions_per_7_days) > 3 ||
      !Number.isInteger(prep.max_minutes_per_7_days) ||
      Number(prep.max_minutes_per_7_days) < 0 ||
      Number(prep.max_minutes_per_7_days) > 180 ||
      (prep.available_days_per_week !== null &&
        (!Number.isInteger(prep.available_days_per_week) ||
          Number(prep.available_days_per_week) < 0 ||
          Number(prep.available_days_per_week) > 7)) ||
      (prep.available_minutes_per_week !== null &&
        (!Number.isInteger(prep.available_minutes_per_week) ||
          Number(prep.available_minutes_per_week) < 0 ||
          Number(prep.available_minutes_per_week) > 10080))
    )
      throw Error("A terv előkészítési állapota hibás.");
    for (const key of [
      "reference_templates",
      "unknown_duration_workout_ids",
      "estimated_duration_workout_ids",
    ]) {
      const values = prep[key];
      if (
        !Array.isArray(values) ||
        new Set(values).size !== values.length ||
        values.some(
          (x) =>
            typeof x !== "string" ||
            (key !== "reference_templates" && !known.has(x)),
        )
      )
        throw Error("Az előkészítés forrásai hiányosak.");
    }
    if (
      !Array.isArray(prep.selection_issues) ||
      prep.selection_issues.some((value) => {
        const issue = object(value);
        return (
          typeof issue.date !== "string" ||
          issue.date < String(v.start_date) ||
          issue.date > String(v.end_date) ||
          !Array.isArray(issue.codes) ||
          issue.codes.some((code) => typeof code !== "string")
        );
      })
    )
      throw Error("Az edzéskiválasztás részletes indokai hibásak.");
  }
  for (const key of ["keep", "cancel", "protected_workout_ids"]) {
    const ids = r[key] as unknown[];
    if (
      new Set(ids).size !== ids.length ||
      ids.some((id) => typeof id !== "string" || !known.has(id))
    )
      throw Error("A tervváltoztatás ismeretlen vagy ismételt edzést érint.");
  }
  if ((r.keep as string[]).some((id) => (r.cancel as string[]).includes(id)))
    throw Error("Ugyanaz az edzés nem tartható meg és törölhető egyszerre.");
  const candidates = r.proposals as unknown[];
  const keys = new Set<string>();
  for (const item of candidates) {
    const c = object(item);
    if (
      typeof c.candidate_key !== "string" ||
      keys.has(c.candidate_key) ||
      typeof c.title !== "string" ||
      typeof c.description !== "string" ||
      typeof c.duration_sec !== "number" ||
      c.duration_sec <= 0 ||
      typeof c.date !== "string" ||
      c.date < v.start_date ||
      c.date > v.end_date ||
      typeof c.start_at !== "string" ||
      typeof c.end_at !== "string" ||
      !Number.isFinite(Date.parse(c.start_at)) ||
      Date.parse(c.end_at) - Date.parse(c.start_at) !== c.duration_sec * 1000
    )
      throw Error("Egy edzésjavaslat időkerete vagy azonosítója hibás.");
    const { candidate_key, ...body } = c;
    if ((await sha(body)) !== candidate_key)
      throw Error("Egy edzésjavaslat tartalomlenyomata eltér.");
    keys.add(c.candidate_key);
  }
  if (
    (r.create as unknown[]).some(
      (c) => !keys.has(String(object(c).candidate_key)),
    ) ||
    (r.cancel as unknown[]).some((id) =>
      (r.protected_workout_ids as unknown[]).includes(id),
    )
  )
    throw Error("A tervváltoztatások védett vagy ismeretlen edzést érintenek.");
  if (r.unavailable_alternatives !== undefined) {
    if (!Array.isArray(r.unavailable_alternatives))
      throw Error("A helyszíni visszajelzések listája hibás.");
    for (const item of r.unavailable_alternatives) {
      const rejected = object(item);
      if (
        typeof rejected.date !== "string" ||
        rejected.date < v.start_date ||
        rejected.date > v.end_date ||
        typeof rejected.location !== "string" ||
        typeof rejected.location_id !== "string" ||
        typeof rejected.opportunity_key !== "string" ||
        !Array.isArray(rejected.codes) ||
        !rejected.codes.length ||
        rejected.codes.some((code) => typeof code !== "string")
      )
        throw Error("Egy helyszíni visszajelzés hiányos.");
    }
  }
  if (r.alternatives !== undefined) {
    if (!Array.isArray(r.alternatives))
      throw Error("Az edzésváltozatok listája hibás.");
    const dates = new Set<string>();
    for (const item of r.alternatives) {
      const group = object(item);
      if (
        typeof group.date !== "string" ||
        group.date < v.start_date ||
        group.date > v.end_date ||
        dates.has(group.date) ||
        !Array.isArray(group.candidates) ||
        !group.candidates.length
      )
        throw Error("Az edzésváltozatok napja hibás.");
      dates.add(group.date);
      const groupKeys = new Set<string>();
      for (const item of group.candidates) {
        const c = object(item),
          { candidate_key, ...raw } = c;
        if (
          typeof candidate_key !== "string" ||
          groupKeys.has(candidate_key) ||
          c.date !== group.date ||
          typeof c.title !== "string" ||
          typeof c.description !== "string" ||
          typeof c.rationale !== "string" ||
          typeof c.template_key !== "string" ||
          typeof c.opportunity_key !== "string" ||
          typeof c.duration_sec !== "number" ||
          c.duration_sec <= 0 ||
          typeof c.start_at !== "string" ||
          typeof c.end_at !== "string" ||
          !Number.isFinite(Date.parse(c.start_at)) ||
          Date.parse(c.end_at) - Date.parse(c.start_at) !==
            c.duration_sec * 1000 ||
          (await sha(raw)) !== candidate_key
        )
          throw Error("Egy edzésváltozat tartalma nem ellenőrizhető.");
        groupKeys.add(candidate_key);
      }
      if (
        !groupKeys.has(String(group.recommended_candidate_key)) ||
        (group.selected_candidate_key !== null &&
          !groupKeys.has(String(group.selected_candidate_key)))
      )
        throw Error("A kiválasztott vagy ajánlott edzésváltozat ismeretlen.");
      if (
        group.selected_candidate_key !== null &&
        !keys.has(String(group.selected_candidate_key))
      )
        throw Error("A kiválasztott változat eltér a tervjavaslattól.");
    }
  }
  if (
    (r.blockers as unknown[]).length &&
    ((r.create as unknown[]).length || (r.cancel as unknown[]).length)
  )
    throw Error(
      "Felülvizsgálati akadály mellett nem alkalmazható tervváltoztatás.",
    );
  return v as unknown as TrainingReview;
}

export async function loadTrainingStatus(
  expected: { owner: string; reference: Reference; zone: string },
  signal?: AbortSignal,
) {
  const v = object(
    await request(
      `programs/${encodeURIComponent(expected.reference.artifact_id)}/training-plan`,
      undefined,
      signal,
    ),
  );
  if (v.automatic_review_interval_seconds !== 60)
    throw Error("A felülvizsgálat beállítása eltér.");
  return {
    review:
      v.review === null ? null : await readTrainingReview(v.review, expected),
    acceptance:
      v.acceptance === null
        ? null
        : ((await verify(
            v.acceptance,
            expected.owner,
            expected.reference.artifact_id,
          )) as unknown as Acceptance),
  };
}
export async function reviewTraining(
  expected: { owner: string; reference: Reference; zone: string },
  first: string,
  last: string,
  signal?: AbortSignal,
) {
  const v = object(
    await request(
      `programs/${encodeURIComponent(expected.reference.artifact_id)}/training-plan/review`,
      JSON.stringify({ start_date: first, end_date: last }),
      signal,
    ),
  );
  const review = await readTrainingReview(v.review, expected);
  if (review.start_date !== first || review.end_date !== last)
    throw Error("Másik időszak tervjavaslata érkezett.");
  return review;
}
export async function chooseTraining(
  expected: { owner: string; reference: Reference; zone: string },
  review: TrainingReview,
  date: string,
  candidateKey: string,
  signal?: AbortSignal,
) {
  const value = object(
    await request(
      `programs/${encodeURIComponent(expected.reference.artifact_id)}/training-plan/choose`,
      JSON.stringify({
        review_reference: {
          artifact_id: review.artifact_id,
          content_hash: review.content_hash,
        },
        date,
        candidate_key: candidateKey,
      }),
      signal,
    ),
  );
  const next = await readTrainingReview(value.review, expected);
  if (
    next.start_date !== review.start_date ||
    next.end_date !== review.end_date
  )
    throw Error("Az edzéscsere másik időszak tervét adta vissza.");
  return next;
}
export async function sendTraining(pending: TrainingPending) {
  const v = object(
    await request(
      `programs/${encodeURIComponent(pending.program)}/training-plan/${pending.operation}`,
      pending.body,
    ),
  );
  const a = await verify(v.artifact, pending.owner, pending.program);
  if (
    v.committed !== true ||
    typeof v.reused !== "boolean" ||
    (await sha(a.proposal)) !==
      (await sha({ ...JSON.parse(pending.body), program_id: pending.program }))
  )
    throw Error(
      "A mentés bizonylata nem ehhez a kéréshez tartozik. Ugyanaz a kérés újraküldhető.",
    );
  return a;
}

export function readTrainingPending(
  raw: string,
  owner: string,
  program: string,
): TrainingPending {
  const v = object(JSON.parse(raw));
  if (
    v.owner !== owner ||
    v.program !== program ||
    !["accept", "missed"].includes(String(v.operation)) ||
    typeof v.body !== "string"
  )
    throw Error("A függő tervmentés nem ehhez a felkészüléshez tartozik.");
  const body = object(JSON.parse(v.body));
  if (
    typeof body.request_id !== "string" ||
    !/^[0-9a-f-]{36}$/.test(body.request_id)
  )
    throw Error("A függő tervmentés kérésazonosítója hiányzik.");
  return v as TrainingPending;
}
