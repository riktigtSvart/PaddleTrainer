import { object } from "./contracts";

type Row = Record<string, unknown>;
const check = (condition: unknown) => { if (!condition) throw Error("A futás kezdőutasításának forrása nem ellenőrizhető."); };
const at = (v: unknown) => {
  check(typeof v === "string" && /(Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v)));
  return Date.parse(String(v));
};
function valid(s: Row, cutoff: number) {
  return Number.isSafeInteger(s.duration_sec) && Number(s.duration_sec) > 0 && s.ended_at !== null &&
    at(s.started_at) <= at(s.ended_at) && at(s.ended_at) <= cutoff &&
    Number(s.duration_sec) * 1000 <= at(s.ended_at) - at(s.started_at);
}
export function runningReference(inputs: Row) {
  const cutoff = at(inputs.captured_at), boundary = at(object(inputs.recent_window).start_at);
  const recentIds = new Set<string>();
  const sessions = (inputs.recent_sessions as unknown[]).map(object);
  for (const s of sessions) {
    check(typeof s.id === "string" && !recentIds.has(s.id) && at(s.started_at) >= boundary && at(s.started_at) <= cutoff);
    recentIds.add(String(s.id));
  }
  const recent = sessions.filter(s => s.sport === "RUNNING" && s.reference_occasion !== true && valid(s, cutoff))
    .sort((a, b) => String(b.started_at).localeCompare(String(a.started_at)) || String(b.id).localeCompare(String(a.id)));
  const refs = recent.filter(s => Number(s.duration_sec) >= 1200).slice(0, 3);
  const cap = refs.length ? Math.min(...refs.map(s => Number(s.duration_sec))) : null;
  const background = object(inputs.running_background);
  check(background.schema_version === "running-background-v0.1" && at(background.before_at) === boundary &&
    background.current_capacity_inferred === false && typeof background.has_more === "boolean" &&
    Array.isArray(background.sessions) && background.sessions.length <= 24);
  const older = (background.sessions as unknown[]).map(object), ids = new Set<string>();
  for (const s of older) {
    check(typeof s.id === "string" && !recentIds.has(s.id) && !ids.has(s.id) && s.sport === "RUNNING" &&
      at(s.started_at) < boundary && at(s.ended_at) <= cutoff && Number.isSafeInteger(s.duration_sec) && Number(s.duration_sec) > 0);
    ids.add(String(s.id));
  }
  const historical = older.filter(s => valid(s, cutoff));
  const profile = inputs.profile ? object(object(inputs.profile).data) : {};
  const declarations: number[] = [], performances: { sport_index: number; result_id: unknown }[] = [];
  ((profile.sport_history ?? []) as unknown[]).map(object).forEach((row, index) => {
    if (!["futás", "futas", "run", "running"].includes(String(row.sport).trim().toLocaleLowerCase("hu"))) return;
    if ([row.level, row.current_level].some(v => ["recreational", "competitive", "professional"].includes(String(v))) ||
      ["independent", "experienced"].includes(String(object(row.planning ?? {}).proficiency))) declarations.push(index);
    ((row.performances ?? []) as unknown[]).map(object).forEach(r => {
      if (["distance_time", "cooper_12min"].includes(String(r.protocol ?? "distance_time")) && r.time && r.distance_m)
        performances.push({ sport_index: index, result_id: r.result_id });
    });
  });
  const mode = refs.length ? "recent_duration" : recent.length || historical.length || declarations.length || performances.length ? "experience_start" : "run_walk_start";
  return { refs, cap, running: { policy_version: "running-start-v0.1", mode,
    recent_session_ids: recent.map(s => s.id), historical_session_ids: historical.map(s => s.id),
    declared_sport_indexes: declarations, performance_references: performances, current_capacity_inferred: false } };
}

export function runningPresentation(mode: string, seconds: number) {
  let name: string, title: string, description: string;
  if (mode === "run_walk_start") {
    name = "4 × (1 perc könnyű kocogás + 90 másodperc séta)";
    title = "Kezdő futás–séta";
    description = "5 perc séta; 4 × (1 perc könnyű kocogás + 90 másodperc séta); 5 perc levezető séta. Ez egy 20 perces kezdő időkeret, nem maximális felmérés.";
  } else if (mode === "experience_start") {
    name = "10 perc könnyű futás, szükség szerint sétával";
    title = "Tájékozódó könnyű futás";
    description = "5 perc séta és könnyű bemelegítés; 10 perc könnyű futás, bármikor sétára váltva; 5 perc levezető séta. A korábbi futás vagy önbevallás tapasztalatot jelez, nem igazolja a mai terhelhetőséget. Ez 20 perces kezdő időkeret, nem kötelező folyamatosan végigfutni.";
  } else {
    check(mode === "recent_duration");
    name = "Könnyű, beszélgetős futás";
    title = "Könnyű aerob futás";
    description = `5 perc könnyű bemelegítés; ${(seconds - 600) / 60} perc könnyű, beszélgetős futás; 5 perc levezetés. Az időkeret a legutóbbi legfeljebb három, legalább 20 perces saját futás legrövidebbikéhez és az elérhető időhöz igazodik. A rövid tesztek nem csökkentik ezt a keretet.`;
  }
  description += " RPE 2–3/10, beszélgetős erőfeszítés, tempó- és pulzuskényszer nélkül. Ha ez nehéz, válts sétára vagy rövidíts; panasz esetén állj meg. Az edzés után rögzítsd a tényleges futás és séta idejét, az erőfeszítést és az esetleges panaszt. Általános aerob támogatás; a kajakspecifikus technikai edzést nem helyettesíti.";
  return { title: `${title} · ${seconds / 60} perc`, description,
    names: ["Séta és könnyű bemelegítés", name, "Levezető séta"] };
}
