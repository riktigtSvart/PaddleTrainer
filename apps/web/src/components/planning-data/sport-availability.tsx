import type { SportAvailability } from "@/lib/planning-cycles/sport-availability";
import { sportLabels } from "@/lib/training-options/contracts";
import type { Sport } from "@/lib/training-options/contracts";
import { daylightReasons } from "@/lib/training-options/daylight-rules";
import { strengthReasons } from "@/lib/planning-cycles/strength-assessment";
import { capabilityLabels } from "@/lib/planning-goals/labels";
import { formatDay } from "@/lib/calendar/contracts";

const reasons: Record<string, string> = {
  ...daylightReasons, ...strengthReasons,
  NO_KNOWN_OPPORTUNITY: "Nincs ehhez a sportághoz megadott edzéslehetőség a vizsgált időszakban.",
  PERSONAL_DURATION_REFERENCE_MISSING: "Ehhez a változathoz nincs friss, befejezett saját edzéselőzmény. A kezdő futás már előzmény nélkül is tervezhető; korábbi eredmény esetén frissítsd a tervet.",
  PERSONAL_DURATION_REFERENCE_TOO_SHORT: "A saját edzéselőzmény rövidebb a jelenleg támogatott változat minimális idejénél.",
  MINIMUM_SPACING: "Egyes időpontok túl közel esnek más edzésekhez.",
  ROLLING_BUDGET_REVIEW: "A többi edzéssel együtt egyes lehetőségek már nem férnek a gördülő heti keretbe.",
  MICROCYCLE_BUDGET_RESERVED: "Az adott ciklusszakasz megadott időkerete elfogyott.",
  OPPORTUNITY_OR_DAILY_MINUTE_CAP: "Egyes időablakok vagy napi keretek rövidek a támogatott edzéshez.",
  INTERVAL_TOO_SHORT_OR_START_PASSED: "Egyes időablakok rövidek, vagy a kezdésük már elmúlt.",
  CAPABILITY_NOT_SUPPORTED_BY_AVAILABLE_SPORT: "A megadott fejlesztési célokhoz ebben a sportágban nincs illeszkedő edzésváltozat.",
  EQUIPMENT_NOT_DECLARED: "A szükséges felszerelés nincs megadva az érintett helyszínen.",
  SPORT_SCOPE_UNKNOWN: "Az időablak sportági beállítása még nincs megadva.",
  EFFORT_CAP_UNKNOWN: "Az időablak terhelési kerete még nincs megadva.",
  EFFORT_NOT_ALLOWED: "Az időablak megadott terhelési korlátja nem engedi ezt a változatot.",
  SWIMMING_ABILITY_REQUIRED: "Az úszás tervezéséhez add meg, hogy önállóan, biztonsággal tudsz úszni, és melyik úszásnemet választod.",
  SWIMMING_POOL_LENGTH_REQUIRED: "Az érintett úszóhelyszínnél az úszómedencét és a medence hosszát is meg kell adni.",
  SWIMMING_CONTINUOUS_LIMIT_BELOW_POOL_LENGTH: "A most megadott folyamatos úszástáv rövidebb egy medencehossznál; ehhez a tervező még nem ad önálló medencés edzést.",
  SWIMMING_POOL_REQUIRED: "Ehhez a változathoz az úszóhelyszínnél jelöld a medencét. A medence pontos hossza az időalapú mintához nem szükséges.",
  GOAL_NOT_SELECTED: "Van ehhez illeszkedő edzésváltozat, de a kiosztás ezt a célt fő célként nem képviseli. A napi alternatívák között ellenőrizhető és választható másik edzés.",
};
export default function SportAvailabilityDetails({ value }: { value: SportAvailability }) {
  const missing = value.goal_coverage?.filter(row => row.status !== "represented") ?? [];
  return <details className="pt-auto-sport-availability">
    <summary>Miért ezek az edzések? · sportágankénti indokok</summary>
    {missing.length > 0 && <section className="pt-goal-coverage-warning" role="status" aria-label="A tervből hiányzó célok">
    <strong>A terv nem képvisel minden megadott fejlesztési vagy fenntartási célt.</strong>
    <p>{[...new Set(missing.map(row => capabilityLabels[row.capability_key]))].join(" · ")}</p>
    <details><summary>Hiányzó célok, okok és teendők</summary>
    <p>Az alábbi célokhoz a legutóbbi kiosztásban nincs fő célként hozzárendelt edzés. Ez a javasolt minták ellenőrzése; a meglévő külső vagy külön szerkesztett edzések ezen felül számíthatnak.</p>
    <ul>{missing.map(row => <li key={`${row.mesocycle_id}:${row.capability_key}:${row.role}`}>
      <strong>{capabilityLabels[row.capability_key]}</strong> · {row.role === "maintenance" ? "fenntartás" : row.role === "primary_development" ? "kiemelt fejlesztés" : "kiegészítő fejlesztés"} · {formatDay(row.start_date)} – {formatDay(row.end_date)}
      <span>{row.status === "unsupported" ? "Ehhez a célhoz még nincs automatikus edzésminta." : [...new Set(row.reasons.map(code => reasons[code] ?? "A megadott korlátok mellett nincs ide illeszthető edzésváltozat."))].join(" ")}</span>
      <a href={`/training-periods/${row.mesocycle_id}`}>Mezociklus megnyitása</a>
      {row.reasons.some(code => code.startsWith("STRENGTH_ASSESSMENT_")) && <> · <a href="/initial-assessment">Erőfelmérés válaszainak felülvizsgálata</a></>}
      {row.reasons.some(code => code.startsWith("SWIMMING_")) && <> · <a href="/athlete-setup#sports">Úszástudás és jelenlegi terhelés</a> · <a href="/training-options/locations">Úszóhelyszín beállításai</a></>}
      {row.reasons.some(code => code.startsWith("DAYLIGHT_")) && <> · <a href="/training-options/locations">Helyszín és napfénykorlát ellenőrzése</a></>}
    </li>)}</ul>
    </details>
  </section>}
    <p>A legutóbbi tervezés javaslatai a teljes vizsgált időszakra. A külön szerkesztett és külső tervek ezen felül megmaradhatnak. A megfelelő időablak önmagában még nem garantál edzést: a célok, saját előzmények és a többi edzés kerete is számít.</p>
    {value.weekly_budget && <p>Gördülő 7 napos felső keret: {value.weekly_budget.max_sessions_per_7_days} edzés, {value.weekly_budget.max_minutes_per_7_days} perc. Alapja: {value.weekly_budget.mode === "declared_current_training" ? "a most megadott szokásos edzésmennyiség" : value.weekly_budget.mode === "observed_covered_weeks" ? "a legutóbbi, adatokkal lefedett hetek mediánja" : "kezdő alkalmazásbeállítás, a megadott szabad idővel korlátozva; ez nem állapotminősítés"}. {value.weekly_budget.baseline_status === "stale" && "A korábban megadott heti mennyiség már nem elég friss."} <a className="underline" href="/athlete-setup#sports">Jelenlegi terhelés és úszástudás megadása</a></p>}
    {value.sports.map(row => <div key={row.sport}>
      <p><strong>{sportLabels[row.sport as Sport]}:</strong> {row.supported ? `${row.planned_sessions} tervezett edzés · ${row.daylight_days} napon megfelelő időablak` : "Ehhez a sportághoz még nincs automatikus edzésminta."}</p>
      {row.supported && row.planned_sessions === 0 && row.candidate_days > 0 && <p>{row.candidate_days} naphoz készült választható változat, de más edzés került a tervbe. Az azonos célt támogató sportágak alternatívák lehetnek; nem szükséges mindegyikből külön edzést beilleszteni.</p>}
      {row.supported && row.reasons.length > 0 && <details><summary>{row.planned_sessions ? "További időpontok kizárási okai" : "A kimaradás okai"}</summary><ul>{[...new Set(row.reasons.map(code => reasons[code] ?? "További megadott korlát érvényes az érintett lehetőségnél."))].map(text => <li key={text}>{text}</li>)}</ul></details>}
    </div>)}
    {value.goal_coverage && <details><summary>Célok képviselete a kiosztott edzésekben</summary><ul>{value.goal_coverage.map(row => <li key={`${row.mesocycle_id}:${row.capability_key}:${row.role}`}>{capabilityLabels[row.capability_key]} · {formatDay(row.start_date)} – {formatDay(row.end_date)} · {row.planned_sessions} edzés fő célja · {row.candidate_days} napon illeszkedő változat</li>)}</ul><p>Egy hozzárendelt minta nem igazolja a cél elérését vagy a fejlesztési dózis elégségességét.</p></details>}
  </details>;
}
