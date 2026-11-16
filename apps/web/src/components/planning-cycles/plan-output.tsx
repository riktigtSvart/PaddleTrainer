"use client";
import WorkoutInstructionDetails from "./workout-instructions";
import {deriveInstructions} from "@/lib/planning-cycles/workout-instructions";
import { daylightReasons } from "@/lib/training-options/daylight-rules";
import { useEffect, useState } from "react";
import { AssessedStrengthDetails } from "./strength-assessment";
import { strengthReasons } from "@/lib/planning-cycles/strength-assessment";
import Link from "next/link";
import { capabilityLabels } from "@/lib/planning-goals/labels";
import { addDays } from "@/lib/planning-cycles/contracts";
import {
  detailedPeriods,
  entriesOnDay,
  dayReason,
  localDay,
  planBlockLabels,
  planSportLabels,
  rollingDates,
} from "@/lib/planning-cycles/plan-view";
import type { PlanEntry } from "@/lib/planning-cycles/plan-view";
import { trainingReasons } from "@/lib/planning-cycles/training-plan";
import type {
  Candidate,
  TrainingReview,
} from "@/lib/planning-cycles/training-plan";
import {
  buttonClass,
  secondaryClass,
} from "@/components/planning-goals/fields";

const weekday = (day: string) =>
  (new Date(day + "T12:00:00Z").getUTCDay() + 6) % 7;
const weekdays = [
  "Hétfő",
  "Kedd",
  "Szerda",
  "Csütörtök",
  "Péntek",
  "Szombat",
  "Vasárnap",
];
const unavailableLabels: Record<string, string> = {
  ...daylightReasons,
  ...strengthReasons,
  SPORT_NOT_ALLOWED:
    "A helyszínen elérhető mozgásformához még nincs a célhoz illesztett támogatott edzésminta.",
  EQUIPMENT_NOT_DECLARED:
    "A mintához szükséges felszerelés nincs ezen a helyszínen megadva.",
  PERSONAL_DURATION_REFERENCE_MISSING:
    "Ehhez a mozgásformához még nincs használható saját időtartam-előzmény az elmúlt 56 napban.",
  PERSONAL_DURATION_REFERENCE_TOO_SHORT:
    "A saját előzmény rövidebb a jelenleg támogatott változat minimális időtartamánál.",
  CAPABILITY_NOT_SUPPORTED_BY_AVAILABLE_SPORT:
    "Az itt elérhető mozgásformához nincs a kijelölt fejlesztési célhoz illesztett edzésváltozat.",
  OPPORTUNITY_OR_DAILY_MINUTE_CAP:
    "A támogatott edzés nem fér a megadott időkeretbe.",
  INTERVAL_TOO_SHORT_OR_START_PASSED:
    "A használható időablak túl rövid, vagy a kezdés már elmúlt.",
  ROLLING_BUDGET_REVIEW: "Ez a változat meghaladná a gördülő heti keretet.",
  MICROCYCLE_BUDGET_RESERVED:
    "Az adott szakasz időkeretét a meglévő és javasolt edzések már lefoglalják.",
  MINIMUM_SPACING: "Nem maradna elegendő idő a többi edzéshez képest.",
  LOCATION_ARCHIVED: "A helyszín törölt, jelenleg nem használható.",
  BOAT_TRANSPORT_NOT_DECLARED: "A hajó szállítása még nincs megadva.",
  LOCATION_TEMPORARILY_RESTRICTED: "Időszaki helyszíni korlátozás érvényes.",
  EFFORT_NOT_ALLOWED: "Az edzés terhelése meghaladná a megadott keretet.",
  NO_SUPPORTED_SAMPLE_FITS:
    "Ehhez a célhoz és helyszínhez még nincs illeszkedő támogatott minta.",
  SWIMMING_POOL_REQUIRED:
    "A medencés kezdőmintához az adott helyszínen úszómedence szükséges. Az időalapú mintához nem kötelező a pontos medencehossz.",
};
const minutes = (seconds: number | null) =>
  seconds === null
    ? "Időtartam pontosítandó"
    : `${Math.round(seconds / 6) / 10} perc`;
export function WorkoutParts({
  entry,
}: {
  entry: { blocks?: Candidate["blocks"]; description: string };
}) {
  return (
    <>
      {entry.description && <p>{entry.description}</p>}
      {!!entry.blocks?.length && (
        <ol className="pt-plan-blocks">
          {[...entry.blocks]
            .sort((a, b) => a.position - b.position)
            .map((block) => (
              <li key={block.position}>
                <strong>
                  {planBlockLabels[block.block_type] ?? block.block_type}
                </strong>{" "}
                · {block.name}
                {block.duration_sec != null
                  ? ` · ${minutes(block.duration_sec)}`
                  : block.distance_m != null
                    ? ` · ${block.distance_m} m`
                    : ""}
              </li>
            ))}
        </ol>
      )}
    </>
  );
}
export function PrescriptionDetails({
  review,
  candidateKey,
}: {
  review: TrainingReview;
  candidateKey: string;
}) {
  const prescription =
    review.result.prescription_context?.by_candidate[candidateKey];
  if (!prescription) return null;
  const candidate=[...review.result.proposals,...(review.result.alternatives?.flatMap(g=>g.candidates)??[])].find(c=>c.candidate_key===candidateKey);
  const instructions=review.result.instruction_context&&candidate?deriveInstructions(candidate as unknown as Record<string,unknown>,prescription as unknown as Record<string,unknown>):null;
  if(instructions)return <WorkoutInstructionDetails value={instructions}/>;
  if (prescription.introductory_strength)
    return (
      <div className="pt-options-meta">
        <p>Bevezető erőnléti gyakorlás számszerű saját erőreferencia nélkül. A 20 perc felső időkeret, pihenőkkel együtt.</p>
        <p>Gyakorlatonként egy sorozat, legfeljebb 5 könnyű ismétlés, külső teher nélkül. A részletes végrehajtás az edzésutasításban található.</p>
        <p>Ez előkészítő alkalom. Nem jelent mért kapacitásból számolt maximáliserő-fejlesztést; a pontos terheléshez saját visszajelzések és referenciák szükségesek.</p>
        <a className="underline" href={prescription.introductory_strength.source_url} target="_blank" rel="noreferrer">Erőedzés szakmai háttér · ACSM 2026</a>
      </div>
    );
  if (prescription.strength && "schema_version" in prescription.strength && prescription.strength.schema_version === "assessed-strength-dose-v0.1")
    return (
      <AssessedStrengthDetails
        review={review}
        dose={prescription.strength}
        seconds={prescription.duration_sec}
        declaredMinutes={prescription.assessment_duration_minutes ?? null}
        productDefault={prescription.product_default_used}
      />
    );
  return (
    <div className="pt-options-meta">
      <p>
        {prescription.swimming
          ? prescription.swimming.mode === "self_paced"
            ? `Úszás: a sportelőéletben megadott önálló/rutinos jártasság alapján, saját szakaszokkal és szükség szerinti pihenővel.${prescription.swimming.pool_length_m ? ` Medence: ${prescription.swimming.pool_length_m} m.` : ""} Nincs minden 50 méterhez előírt megállás; a jártasságból nem következtetünk tempóra vagy folyamatosan leúszható távra.`
            : `Úszás: ${prescription.swimming.pool_length_m} méteres medence, ${prescription.swimming.mode === "continuous" ? "folyamatos főrész, szükség szerinti pihenővel" : `${prescription.swimming.lengths_per_repeat} hosszanként ${prescription.swimming.rest_seconds} másodperc pihenő`}. A megadott úszástudásra és az elérhető saját időadatokra épül; ez nem mért aktuális úszóképesség.`
          : prescription.running
          ? prescription.running.mode === "recent_duration"
            ? `Időtartam: a legutóbbi legfeljebb három, legalább 20 perces saját futás legrövidebb ideje (${minutes(prescription.reference_cap_seconds)}) és az elérhető idő alapján. A rövid tesztek nem szabnak felső korlátot.`
            : prescription.running.mode === "experience_start"
              ? "A korábbi futások, sportmúlt vagy egyéni eredmények alapján 20 perces tájékozódó kezdés, szükség szerinti sétával. A mai terhelhetőséget még pontosítani kell."
              : "Még nincs saját futási referencia. A 20 perces kezdő futás–séta konkrét utasítást ad az első alkalomhoz."
          : prescription.product_default_used
          ? "Időtartam: általános, legfeljebb 30 perces kezdőváltozat, a használható időablakhoz igazítva."
          : `Időtartam: ${review.calibration_review ? "a ciklus kiindulópontján rögzített" : "a legutóbbi"} legfeljebb három, azonos sportágban rögzített saját teljesítés legrövidebb ideje (${minutes(prescription.reference_cap_seconds)}) és a rendelkezésre álló idő alapján.`}
      </p>
      {prescription.soft_duration_reduced && !prescription.running && !prescription.swimming && (
        <p>Rövidített változat az elérhető időkerethez.</p>
      )}
      <p>
        {prescription.strength
          ? "Intenzitás: ismert teher, 2 gyakorlat × 2 × 6 ismétlés, 3–4 ismétlés tartalékkal. A főrész időkeret, a pihenőkkel együtt; nincs automatikus súlyemelés."
          : "Intenzitás: könnyű, beszélgetős érzet, RPE 2–3/10. Ez általános kiindulópont; személyes pulzus- vagy tempóküszöböt nem feltételez."}
      </p>
      {!!prescription.reference_session_ids.length && (
        <p>
          Saját előzmények:{" "}
          {prescription.reference_session_ids.map((id, i) => {
            const source = (
              prescription.running || prescription.swimming ? review : review.calibration_review ?? review
            ).inputs?.recent_sessions?.find((s) => s.id === id);
            return (
              <span key={id}>
                {i > 0 ? "; " : ""}
                <Link
                  className="underline"
                  href={`/sessions/${encodeURIComponent(id)}`}
                >
                  {source?.started_at
                    ? localDay(
                        review.timezone_name,
                        new Date(source.started_at),
                      )
                    : "Edzés"}
                  {source?.name ? ` · ${source.name}` : ""}
                </Link>
              </span>
            );
          })}
        </p>
      )}
    </div>
  );
}
export default function PlanOutput({
  review,
  disabled,
  onChoose,
  changes,
  onUndo,
}: {
  review: TrainingReview;
  disabled: boolean;
  onChoose: (date: string, candidate: string) => void;
  changes?: { date: string; before: string; after: string }[];
  onUndo?: () => void;
}) {
  const [mode, setMode] = useState<"week" | "calendar">("week"),
    [today, setToday] = useState(() => localDay(review.timezone_name)),
    [first, setFirst] = useState(() => localDay(review.timezone_name)),
    [following, setFollowing] = useState(true),
    [selected, setSelected] = useState(() => localDay(review.timezone_name));
  useEffect(() => {
    const update = () => {
      const current = localDay(review.timezone_name);
      setToday(current);
      if (following) setFirst(current);
    };
    const tick = window.setInterval(update, 60000);
    window.addEventListener("focus", update);
    document.addEventListener("visibilitychange", update);
    return () => {
      window.clearInterval(tick);
      window.removeEventListener("focus", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, [review.timezone_name, following]);
  const dates = rollingDates(first),
    active = dates.includes(selected) ? selected : first,
    entries = entriesOnDay(review, active),
    groups = review.result.alternatives?.find((group) => group.date === active),
    reason = dayReason(review, active),
    periods = detailedPeriods(review.inputs?.periods ?? [], review.start_date);
  const visible = dates.flatMap((date) => entriesOnDay(review, date)),
    seconds = visible.reduce(
      (sum, entry) => sum + (entry.duration_sec ?? 0),
      0,
    ),
    unknown = visible.some((entry) => entry.duration_sec === null);
  function openDate(date: string) {
    setFirst(date);
    setSelected(date);
    setFollowing(false);
    setMode("week");
  }
  function reset() {
    const current = localDay(review.timezone_name);
    setToday(current);
    setFirst(current);
    setSelected(current);
    setFollowing(true);
    setMode("week");
  }
  const unchanged = (entry: PlanEntry) => (
    <article className="pt-plan-variant" key={entry.key}>
      <header>
        <h4>{entry.title}</h4>
        <span className="pt-plan-badge">
          {entry.kind === "protected" ? "Meglévő · megőrzött" : "Mentett terv"}
        </span>
      </header>
      <p>
        {planSportLabels[entry.sport] ?? entry.sport} ·{" "}
        {entry.estimated ? "Becsült: " : ""}
        {minutes(entry.duration_sec)}
      </p>
      <WorkoutParts entry={entry} />
      <Link
        className={secondaryClass}
        href={`/workouts/${encodeURIComponent(entry.key)}`}
      >
        Edzés megnyitása
      </Link>
    </article>
  );
  return (
    <section
      className="pt-plan-output"
      aria-label="Edzésterv naptár és gördülő heti bontás"
    >
      <div className="pt-section-heading">
        <h3>Edzésterv</h3>
        <div className="pt-options-actions">
          <button
            type="button"
            className={secondaryClass}
            aria-pressed={mode === "calendar"}
            onClick={() => setMode("calendar")}
          >
            Ciklusnaptár
          </button>
          <button
            type="button"
            className={secondaryClass}
            aria-pressed={mode === "week"}
            onClick={reset}
          >
            Következő 7 nap
          </button>
        </div>
      </div>
      <p className="pt-options-meta">
        Részletes felülvizsgálat: {review.start_date} – {review.end_date}. Az
        edzéscsere a javaslatot újraszámolja; a naptári mentést az elfogadás
        véglegesíti.
      </p>
      {review.result.distribution&&<p className="pt-options-meta">Az elosztás a mentett fő céloknak ad elsőbbséget, majd pihenőnapokkal tagoltabb ritmust keres a használható időablakokban. Ettől a mikrociklus edzésszáma és összideje nem nő. A szomszédos ciklusok és a meglévő edzések korlátai is számítanak.</p>}
      {!!changes?.length && (
        <section className="pt-plan-changes" aria-live="polite">
          <h4>A választás után módosult</h4>
          <ul>
            {changes.map((change) => (
              <li key={change.date}>
                <strong>{change.date}</strong> · {change.before} →{" "}
                {change.after}
              </li>
            ))}
          </ul>
          {onUndo && (
            <button
              type="button"
              className={secondaryClass}
              disabled={disabled}
              onClick={onUndo}
            >
              Választás visszavonása
            </button>
          )}
        </section>
      )}
      {mode === "calendar" ? (
        <div className="pt-plan-cycles">
          {(periods.length
            ? periods
            : [
                {
                  id: "review",
                  title: "Részletes időszak",
                  start_date: review.start_date,
                  end_date: review.end_date,
                },
              ]
          ).map((period, index) => {
            const length =
              Math.round(
                (Date.parse(period.end_date) - Date.parse(period.start_date)) /
                  86400000,
              ) + 1;
            return (
              <section key={period.id}>
                <h4>
                  {index === 0
                    ? "Aktuális / soron következő mezociklus"
                    : "Következő mezociklus"}{" "}
                  · {period.title}
                </h4>
                <p className="pt-options-meta">
                  {period.start_date} – {period.end_date}
                </p>
                <div className="pt-options-table-scroll">
                  <table className="pt-plan-cycle-table">
                    <thead>
                      <tr>
                        {weekdays.map((day) => (
                          <th key={day}>{day.slice(0, 3)}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {Array.from(
                        {
                          length: Math.ceil(
                            (weekday(period.start_date) + length) / 7,
                          ),
                        },
                        (_, row) => (
                          <tr key={row}>
                            {Array.from({ length: 7 }, (_, col) => {
                              const index =
                                  row * 7 + col - weekday(period.start_date),
                                date = addDays(period.start_date, index);
                              if (index < 0 || index >= length)
                                return <td key={col} />;
                              const items = entriesOnDay(review, date);
                              return (
                                <td key={col}>
                                  <button
                                    type="button"
                                    className="pt-plan-calendar-day"
                                    data-session={items.length > 0}
                                    onClick={() => openDate(date)}
                                    aria-label={`${date} · ${items.map((entry) => entry.title).join(" + ") || dayReason(review, date).label}`}
                                  >
                                    <span>
                                      {date.slice(5).replace("-", ".")}
                                    </span>
                                    {items.length ? (
                                      items.map((entry) => (
                                        <span key={entry.key}>
                                          {planSportLabels[entry.sport] ??
                                            entry.sport}{" "}
                                          · {minutes(entry.duration_sec)}
                                        </span>
                                      ))
                                    ) : (
                                      <small>
                                        {dayReason(review, date).label}
                                      </small>
                                    )}
                                  </button>
                                </td>
                              );
                            })}
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <>
          <div className="pt-section-heading">
            <button
              type="button"
              className={secondaryClass}
              onClick={() => {
                setFirst(addDays(first, -1));
                setFollowing(false);
              }}
              aria-label="Egy nappal korábbról"
            >
              ←
            </button>
            <span>
              {first} – {addDays(first, 6)}
            </span>
            <div className="pt-options-actions">
              <button type="button" className={secondaryClass} onClick={reset}>
                Mától 7 nap
              </button>
              <button
                type="button"
                className={secondaryClass}
                onClick={() => {
                  setFirst(addDays(first, 1));
                  setFollowing(false);
                }}
                aria-label="Egy nappal későbbről"
              >
                →
              </button>
            </div>
          </div>
          <p className="pt-options-meta">
            {visible.length} edzés / javaslat · {unknown ? "legalább " : ""}
            {minutes(seconds)} · egymást követő 7 nap
          </p>
          <div className="pt-options-table-scroll">
            <table className="pt-plan-rolling">
              <thead>
                <tr>
                  {dates.map((date) => (
                    <th key={date} scope="col">
                      <span>
                        {weekdays[weekday(date)]}
                        {date === today ? " · Ma" : ""}
                      </span>
                      <small>{date.slice(5).replace("-", ".")}</small>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  {dates.map((date) => {
                    const dayEntries = entriesOnDay(review, date);
                    return (
                      <td key={date}>
                        <button
                          type="button"
                          className="pt-plan-day"
                          aria-pressed={active === date}
                          aria-controls="pt-plan-selected-day"
                          data-has-session={dayEntries.length > 0}
                          onClick={() => setSelected(date)}
                        >
                          {dayEntries.length ? (
                            dayEntries.map((entry) => (
                              <span key={entry.key}>
                                <strong>
                                  {planSportLabels[entry.sport] ?? entry.sport}
                                </strong>
                                <small>
                                  {entry.estimated ? "~ " : ""}
                                  {minutes(entry.duration_sec)}
                                </small>
                                <small>
                                  {entry.kind === "proposal"
                                    ? review.selection_preferences?.[date]
                                      ? "Saját választás"
                                      : "Ajánlott"
                                    : "Mentett"}
                                </small>
                              </span>
                            ))
                          ) : (
                            <span>{dayReason(review, date).label}</span>
                          )}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              </tbody>
            </table>
          </div>
          <section id="pt-plan-selected-day" className="pt-plan-selected">
            <h3>
              {weekdays[weekday(active)]} · {active}
            </h3>
            <div className="pt-plan-variants">
              {entries.filter((entry) => !entry.candidate_key).map(unchanged)}
              {groups
                ? groups.candidates.map((candidate) => {
                    const chosen =
                        groups.selected_candidate_key ===
                        candidate.candidate_key,
                      recommended =
                        groups.recommended_candidate_key ===
                        candidate.candidate_key;
                    return (
                      <article
                        key={candidate.candidate_key}
                        className="pt-plan-variant"
                        data-selected={chosen}
                        data-default={recommended}
                      >
                        <header>
                          <h4>{candidate.location || candidate.title}</h4>
                          <span className="pt-plan-badge">
                            {recommended
                              ? "Alapértelmezett · ajánlott"
                              : "Alternatíva"}
                          </span>
                          {chosen && (
                            <span className="pt-plan-badge">
                              A javaslatban kiválasztva
                            </span>
                          )}
                        </header>
                        {candidate.location && <p>{candidate.title}</p>}
                        <p>
                          {minutes(candidate.duration_sec)} ·{" "}
                          {capabilityLabels[candidate.capability_key] ??
                            candidate.capability_key}
                        </p>
                        <WorkoutParts entry={candidate} />
                        <PrescriptionDetails
                          review={review}
                          candidateKey={candidate.candidate_key}
                        />
                        <p className="pt-options-meta">{candidate.rationale}</p>
                        <button
                          type="button"
                          className={chosen ? secondaryClass : buttonClass}
                          disabled={disabled || chosen}
                          aria-pressed={chosen}
                          onClick={() =>
                            onChoose(active, candidate.candidate_key)
                          }
                        >
                          {chosen
                            ? "Ez szerepel a javaslatban"
                            : "Ezt választom helyette"}
                        </button>
                      </article>
                    );
                  })
                : entries
                    .filter((entry) => !!entry.candidate_key)
                    .map((entry) => (
                      <article key={entry.key} className="pt-plan-variant">
                        <header>
                          <h4>{entry.title}</h4>
                          <span className="pt-plan-badge">
                            Ajánlott javaslat
                          </span>
                        </header>
                        <p>{minutes(entry.duration_sec)}</p>
                        <WorkoutParts entry={entry} />
                        <PrescriptionDetails
                          review={review}
                          candidateKey={entry.candidate_key!}
                        />
                      </article>
                    ))}
              {!entries.length && !groups && (
                <p>{trainingReasons[reason.reason] ?? reason.reason}</p>
              )}
              {review.result.unavailable_alternatives
                ?.filter((option) => option.date === active)
                .map((option) => (
                  <article
                    key={option.opportunity_key}
                    className="pt-plan-variant"
                  >
                    <header>
                      <h4>{option.location}</h4>
                      <span className="pt-plan-badge">
                        Most nem választható
                      </span>
                    </header>
                    <ul>
                      {option.codes.map((code) => (
                        <li key={code}>
                          {unavailableLabels[code] ??
                            "A helyszín vagy az edzés feltételeit még pontosítani kell."}
                        </li>
                      ))}
                    </ul>
                  </article>
                ))}
            </div>
          </section>
        </>
      )}
    </section>
  );
}
