import { day } from "@/lib/planning-cycles/contracts";

export const trainingPurposes = {
  aerobic_substitution: "Állóképességi munka helyettesítése",
  strength: "Erőfejlesztés",
  muscular_endurance: "Erőállóképesség",
  speed_power: "Gyorsaság és robbanékonyság",
  technique: "Technika és koordináció",
  mobility: "Mobilitás",
  general_conditioning: "Általános felkészítés",
  recovery: "Regeneráció",
  other: "Más fejlesztési cél",
} as const;
export type SportPlanning = {
  version: "sport-planning-context-v0.1";
  supported_sports: string[];
  purposes: (keyof typeof trainingPurposes)[];
  proficiency: "unknown" | "learning" | "independent" | "experienced";
};
export type SportPerformance = {
  result_id: string;
  kind: "personal_best" | "recent";
  distance_m?: string;
  time?: string;
  protocol?: PerformanceProtocol;
  exercise?: string;
  repetitions?: number;
  load_kind?: "bodyweight" | "external_kg";
  load_kg?: string;
  load_basis?: "total_external" | "per_hand" | "additional_to_bodyweight" | "machine_display";
  recorded_on: string | null;
  year: number | null;
  conditions: string;
  source: "self_report" | "official" | "device";
};
export const emptySportPlanning = (): SportPlanning => ({ version: "sport-planning-context-v0.1", supported_sports: [], purposes: [], proficiency: "unknown" });
export function performanceSeconds(value: string): number {
  const match = /^(?:(\d{1,3}):)?(\d{1,3}):([0-5]\d(?:\.\d{1,3})?)$/.exec(value);
  if (!match || (match[1] !== undefined && Number(match[2]) > 59)) throw Error("Az időeredmény formája p:ss vagy ó:pp:ss legyen, legfeljebb három tizedesjeggyel.");
  const result = Number(match[1] ?? 0) * 3600 + Number(match[2]) * 60 + Number(match[3]);
  if (!(result > 0 && result <= 604800)) throw Error("Az időeredmény legyen pozitív és legfeljebb hét nap.");
  return result;
}
export const performanceProtocols = {
  distance_time: "Táv és időeredmény",
  cooper_12min: "Cooper-teszt · 12 perc alatt megtett táv",
  strength_1rm: "Korábban teljesített egyismétléses maximum (kg)",
  repetitions: "Legtöbb szabályos ismétlés",
  timed_repetitions: "Ismétlésszám adott idő alatt",
} as const;
export type PerformanceProtocol = keyof typeof performanceProtocols;
export function changePerformanceProtocol(row: SportPerformance, protocol: PerformanceProtocol): SportPerformance {
  const value: SportPerformance = { result_id: row.result_id, kind: row.kind, recorded_on: row.recorded_on, year: row.year, conditions: row.conditions, source: row.source, protocol };
  if (["distance_time", "cooper_12min"].includes(protocol)) return { ...value, distance_m: row.distance_m ?? "", time: protocol === "cooper_12min" ? "12:00" : row.time ?? "" };
  return { ...value, exercise: row.exercise ?? "", ...(protocol === "strength_1rm" ? { repetitions: 1 } : row.repetitions !== undefined ? { repetitions: row.repetitions } : {}),
    load_kind: protocol === "strength_1rm" ? "external_kg" : row.load_kind ?? "bodyweight",
    ...(protocol === "strength_1rm" || row.load_kind === "external_kg" ? { load_kg: row.load_kg ?? "", load_basis: row.load_basis ?? "total_external" } : {}),
    ...(protocol === "timed_repetitions" ? { time: row.protocol === "timed_repetitions" ? row.time ?? "" : "" } : {}) };
}
export function normalizePerformance(value: SportPerformance, today: string): SportPerformance {
  const protocol = value.protocol ?? "distance_time";
  if (!(protocol in performanceProtocols)) throw Error("Ismeretlen sporteredménytípus.");
  if (value.recorded_on) { day(value.recorded_on); if (value.recorded_on > today) throw Error("Az eredmény dátuma nem lehet jövőbeli."); }
  if (value.year !== null && (!Number.isInteger(value.year) || value.year < 1900 || value.year > Number(today.slice(0, 4)))) throw Error("Az eredmény évét ellenőrizd.");
  if (value.recorded_on && value.year !== null) throw Error("Az eredményhez pontos napot vagy évet adj meg.");
  const result = { ...value, conditions: value.conditions.trim() };
  const positive = (raw: string | undefined) => { const n = (raw ?? "").trim().replace(",", "."); if (!/^(?:0|[1-9][0-9]{0,14})(?:\.[0-9]{1,6})?$/.test(n) || Number(n) <= 0) throw Error("Pozitív értéket adj meg."); return n; };
  if (["distance_time", "cooper_12min"].includes(protocol)) {
    result.time = (value.time ?? "").trim().replace(",", "."); result.distance_m = positive(value.distance_m);
    const seconds = performanceSeconds(result.time);
    if (protocol === "cooper_12min" && seconds !== 720) throw Error("A Cooper-teszt ideje pontosan 12:00.");
    if ([value.exercise, value.repetitions, value.load_kind, value.load_kg, value.load_basis].some(v => v != null)) throw Error("A táv–idő eredményhez nem tartoznak erőeredmény-mezők.");
  } else {
    result.exercise = (value.exercise ?? "").trim();
    if (!result.exercise || result.exercise.length > 200 || !Number.isInteger(value.repetitions) || value.repetitions! < 0 || value.repetitions! > 100000 || value.distance_m != null) throw Error("Add meg a gyakorlatot és a tényleges egész ismétlésszámot. A nulla ismétlés is rögzíthető.");
    if (protocol === "timed_repetitions") { result.time = (value.time ?? "").trim().replace(",", "."); performanceSeconds(result.time); }
    else if (value.time != null) throw Error("Ehhez az erőeredményhez nem tartozik időeredmény.");
    if (value.load_kind === "bodyweight") { if (value.load_kg != null || value.load_basis != null) throw Error("Külső súly nélküli gyakorlatnál nincs hozzáadott kilogramm."); }
    else if (value.load_kind === "external_kg" && ["total_external", "per_hand", "additional_to_bodyweight", "machine_display"].includes(value.load_basis ?? "")) result.load_kg = positive(value.load_kg);
    else throw Error("Add meg a terhelés típusát és a súly értelmezését.");
    if (protocol === "strength_1rm" && (value.repetitions !== 1 || value.load_kind !== "external_kg")) throw Error("A rögzített egyismétléses maximumhoz egy teljesített ismétlés és súly tartozik.");
  }
  return result;
}
