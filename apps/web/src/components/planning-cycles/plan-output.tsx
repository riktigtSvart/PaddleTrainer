"use client";
import { useEffect, useState } from "react";
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
  SPORT_NOT_ALLOWED:
    "A helyszínen elérhető mozgásformához még nincs a célhoz illesztett támogatott edzésminta.",
  EQUIPMENT_NOT_DECLARED:
    "A mintához szükséges felszerelés nincs ezen a helyszínen megadva.",
  PERSONAL_DURATION_REFERENCE_MISSING:
    "Ehhez a változathoz még szükséges korábbi saját edzésreferencia.",
  OPPORTUNITY_OR_DAILY_MINUTE_CAP:
    "A támogatott edzés nem fér a megadott időkeretbe.",
  INTERVAL_TOO_SHORT_OR_START_PASSED:
    "A használható időablak túl rövid, vagy a kezdés már elmúlt.",
  ROLLING_BUDGET_REVIEW: "Ez a változat meghaladná a gördülő heti keretet.",
  MINIMUM_SPACING: "Nem maradna elegendő idő a többi edzéshez képest.",
  LOCATION_ARCHIVED: "A helyszín törölt, jelenleg nem használható.",
  BOAT_TRANSPORT_NOT_DECLARED: "A hajó szállítása még nincs megadva.",
  LOCATION_TEMPORARILY_RESTRICTED: "Időszaki helyszíni korlátozás érvényes.",
  EFFORT_NOT_ALLOWED: "Az edzés terhelése meghaladná a megadott keretet.",
  NO_SUPPORTED_SAMPLE_FITS:
    "Ehhez a célhoz és helyszínhez még nincs illeszkedő támogatott minta.",
};
const minutes = (seconds: number | null) =>
  seconds === null
    ? "Időtartam pontosítandó"
    : `${Math.round(seconds / 6) / 10} perc`;
function WorkoutParts({
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
