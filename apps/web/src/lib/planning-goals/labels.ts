import type { Criterion, GoalRole, Resource } from "./types";

export const roleLabels: Record<GoalRole, string> = {
  primary_development: "Fő fejlesztési cél",
  secondary_development: "Másodlagos fejlesztés",
  maintenance: "Szinten tartás",
  permitted_decline: "Megengedett átmeneti visszaesés",
};
export const resourceLabels: Record<Resource, string> = {
  "macrocycle-plans": "Makrocikluscélok",
  "mesocycle-protocols": "Mérési protokollok",
  measurements: "Mérési eredmények",
  assessments: "Célértékelések",
};
export const capabilityLabels: Record<string, string> = {
  VO2_CAPACITY: "Aerob kapacitás / VO₂max",
  PERIPHERAL_OXIDATIVE_CAPACITY: "Izom oxidatív kapacitása",
  PADDLING_ECONOMY: "Evezés gazdaságossága",
  MAX_STRENGTH: "Maximális erő",
  POWER_RFD: "Teljesítmény és erőkifejtési sebesség",
  MUSCULOSKELETAL_ROBUSTNESS: "Mozgásszervi terhelhetőség",
  TECHNICAL_SKILL: "Technikai készség",
  TECHNICAL_STABILITY_UNDER_FATIGUE: "Technika megtartása fáradás alatt",
  LONG_DURATION_DURABILITY: "Hosszú terhelés tűrése",
  PACING_COMPETENCE: "Tempóbeosztás",
  SPRINT_SPEED_AND_START: "Sprintsebesség és rajt",
  MUSCULAR_ENDURANCE: "Erő-állóképesség",
  HIGH_INTENSITY_AND_ANAEROBIC_PROFILE: "Nagy intenzitású és anaerob profil",
};
export const metricLabels: Record<string, string> = {
  VO2MAX_ABSOLUTE: "Mért abszolút VO₂max",
  VO2MAX_RELATIVE: "Mért relatív VO₂max",
  VO2MAX_ESTIMATED_RELATIVE: "Becsült relatív VO₂max",
  SUBMAXIMAL_OUTPUT: "Szubmaximális teljesítmény",
  PADDLING_OXYGEN_COST: "Oxigénigény rögzített teljesítménynél",
  STRENGTH_1RM: "Közvetlenül mért 1RM",
  STRENGTH_REFERENCE_LOAD: "Referencia-erőterhelés",
  STRENGTH_ESTIMATED_1RM: "Becsült 1RM",
  PEAK_POWER: "Csúcsteljesítmény",
  RATE_OF_FORCE_DEVELOPMENT: "Erőkifejtés sebessége (RFD)",
  FUNCTIONAL_TASK_REPETITIONS: "Funkcionális feladat ismétlései",
  PAIN_RATING: "Fájdalomértékelés",
  TECHNICAL_ERROR_COUNT: "Technikai hibák száma",
  TECHNICAL_ERROR_INCREASE: "Technikai hibák növekedése",
  POWER_RETENTION: "Teljesítménymegtartás",
  HEART_RATE_DRIFT: "Pulzusdrift",
  PACING_PROFILE_ERROR: "Eltérés a céltempótól",
  STANDING_START_TIME: "Állórajtos sprint ideje",
  FLYING_START_SPEED: "Repülőrajtos sebesség",
  FIXED_LOAD_REPETITIONS: "Ismétlések rögzített terheléssel",
  LACTATE_THRESHOLD_POWER: "Laktátküszöbhöz tartozó teljesítmény",
  VENTILATORY_THRESHOLD_POWER: "Ventilációs küszöbhöz tartozó teljesítmény",
  CRITICAL_POWER: "Kritikus teljesítmény",
  SPRINT_MEAN_POWER: "Sprint átlagteljesítménye",
  ANAEROBIC_CAPACITY_ESTIMATE: "Anaerob kapacitás becslése",
};
export const evidenceLabels: Record<string, string> = {
  physiological_measurement: "Élettani mérés",
  task_performance: "Feladatteljesítmény",
  estimate: "Becslés",
  indirect_indicator: "Közvetett jelző",
  subjective_context: "Szubjektív háttéradat",
};
const metricLimits: Record<string, string> = {
  VO2MAX_ABSOLUTE:
    "Az oxigénfelvétel az adott eljárásra és mozgásformára vonatkozik.",
  VO2MAX_RELATIVE: "A méréshez tartozó testtömeget is meg kell őrizni.",
  VO2MAX_ESTIMATED_RELATIVE:
    "Nem cserélhető fel a közvetlenül mért VO₂max-szal.",
  SUBMAXIMAL_OUTPUT: "Nem különíti el az izom oxidatív alkalmazkodását.",
  PADDLING_OXYGEN_COST: "Azonos külső teljesítmény és mozgásforma szükséges.",
  STRENGTH_1RM:
    "A gyakorlatnak, eszköznek és mozgástartománynak egyeznie kell.",
  STRENGTH_REFERENCE_LOAD:
    "Az ismétlésszámnak, az ismétléstartaléknak és a technikának egyeznie kell.",
  STRENGTH_ESTIMATED_1RM: "A becslőeljárás verziója a protokoll része.",
  PEAK_POWER: "Nem méri az erőkifejtés sebességét (RFD).",
  RATE_OF_FORCE_DEVELOPMENT:
    "Erő–idő adatrögzítés és rögzített feldolgozási eljárás szükséges.",
  FUNCTIONAL_TASK_REPETITIONS:
    "A feladat tűrése önmagában nem igazol sérüléssel szembeni ellenállást.",
  PAIN_RATING: "Háttéradat; nem képességmérő vagy diagnosztikai mérési cél.",
  TECHNICAL_ERROR_COUNT:
    "Rögzített megfigyelési idő és értékelési szabályrendszer szükséges.",
  TECHNICAL_ERROR_INCREASE:
    "Rögzített terhelés és összehasonlítható friss, illetve terhelt megfigyelés szükséges.",
  POWER_RETENTION:
    "A friss és terhelt feladatoknak, valamint az előzetes terhelésnek egyezniük kell.",
  HEART_RATE_DRIFT:
    "A körülmények is befolyásolják; önmagában nem diagnosztizál fáradtságot.",
  PACING_PROFILE_ERROR: "Az előírt tempóstratégiához viszonyítva értékelendő.",
  STANDING_START_TIME: "Rögzített táv, rajt és időmérési eljárás szükséges.",
  FLYING_START_SPEED: "Nem cserélhető fel állórajtos eredményekkel.",
  FIXED_LOAD_REPETITIONS:
    "Rögzített terhelés, mozdulat és befejezési szabály szükséges.",
  LACTATE_THRESHOLD_POWER:
    "A küszöb meghatározását előre rögzíteni kell; nem az anaerob kapacitás mértéke.",
  VENTILATORY_THRESHOLD_POWER:
    "Nem cserélhető fel a laktátküszöbbel vagy a kritikus teljesítménnyel.",
  CRITICAL_POWER:
    "A modellt, a próbákat és az illesztési eljárást előre rögzíteni kell.",
  SPRINT_MEAN_POWER:
    "Több energiarendszer közös teljesítménye; nem tisztán az anaerob kapacitás mértéke.",
  ANAEROBIC_CAPACITY_ESTIMATE:
    "Eljárásfüggő becslés; önmagában a sprintteljesítményből nem következtethető ki.",
};
export function metricLimit(key: string, original: string): string {
  return metricLimits[key] ?? original;
}
export const criterionLabels: Record<Criterion, string> = {
  met_under_declared_error: "Teljesül a megadott mérési hiba mellett",
  not_met_under_declared_error: "Nem teljesül a megadott mérési hiba mellett",
  withheld: "Az értékelés visszatartva",
  descriptive_only: "Csak leíró eredmény",
};
const reasons: Record<string, string> = {
  METRIC_MISMATCH: "Más mérőszám.",
  UNIT_MISMATCH: "Eltérő mértékegység.",
  OUTSIDE_ENDPOINT_WINDOWS: "A mérési időablakokon kívül esik.",
  EXECUTION_OR_NUMERIC_RESULT_UNRESOLVED:
    "A végrehajtás vagy a számérték nem tisztázott.",
  PROCEDURE_MODALITY_TASK_OR_PROCESSING_MISMATCH:
    "Eltérő protokoll, mozgásforma, feladat vagy feldolgozás.",
  EVIDENCE_KIND_MISMATCH: "Eltérő adattípus.",
  INCOMPLETE_PROTOCOL_RESULT: "A protokoll végrehajtása nem teljes.",
  WITHIN_PROTOCOL_TRIAL_IS_NOT_A_COMPLETE_RESULT:
    "Részpróba nem helyettesít teljes teszteredményt.",
  COMPLETE_EXECUTION_OUTSIDE_WINDOW:
    "A teljes végrehajtás nem fér az időablakba.",
  SOURCE_INTERVAL_MISMATCH: "Eltérő forrásidőszak.",
  COMPLETE_RESULT_RECORDED_BEFORE_EXECUTION_END:
    "Az eredményt a végrehajtás vége előtt rögzítették.",
  CONDITION_CENSUS_UNRESOLVED: "Hiányosak az összehasonlíthatóság feltételei.",
  COMPARABILITY_CONDITION_NOT_MET:
    "Egy összehasonlíthatósági feltétel nem teljesült.",
  EXECUTION_OR_CONDITIONS_UNKNOWN:
    "A végrehajtás vagy egy feltétel állapota ismeretlen.",
  BODY_MASS_NOT_RETAINED: "Hiányzik a testtömeg.",
  PERCENT_CHANGE_REQUIRES_POSITIVE_BASELINE:
    "Százalékos változáshoz pozitív kiinduló érték kell.",
  CHANGE_UNCERTAINTY_UNQUANTIFIED:
    "Nincs számszerűsített mérési hiba és hozzá tartozó forrás.",
  DECLARED_ERROR_RANGE_CROSSES_ACCEPTANCE_BOUNDARY:
    "A megadott hibával számolt tartomány metszi a cél határát.",
  ALL_PRIMARY_ENDPOINTS_REQUIRED_NO_COMPOSITE_SCORE:
    "Minden elsődleges mérési célnak teljesülnie kell; nincs összevont pontszám.",
};
export function reasonLabel(code: string): string {
  if (reasons[code]) return reasons[code];
  for (const [prefix, window] of [
    ["BASELINE_", "A kiinduló"],
    ["FOLLOWUP_", "A záró"],
  ]) {
    if (code === prefix + "WINDOW_NOT_CLOSED")
      return `${window} mérési időablak még nem zárult le.`;
    if (code === prefix + "CANDIDATE_UNRESOLVED")
      return `${window} időablakban tisztázatlan mérési adat van.`;
    if (code === prefix + "RESULT_MISSING")
      return `${window} időablakból hiányzik az értékelhető eredmény.`;
    if (code === prefix + "RESULT_AMBIGUOUS")
      return `${window} időablakban több megfelelő teljes eredmény van.`;
  }
  return `További indok: ${code}`;
}
export function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Ismeretlen időpont"
    : new Intl.DateTimeFormat("hu-HU", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "UTC",
      }).format(date) + " UTC";
}
