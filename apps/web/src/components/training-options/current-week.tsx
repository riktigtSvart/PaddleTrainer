"use client";
import Link from "next/link";
import { useState } from "react";
import { canonical } from "@/lib/planning-cycles/contracts";
import {
  Field,
  Select,
  buttonClass,
  secondaryClass,
} from "@/components/planning-goals/fields";
import {
  defaultSlot,
  readOptionsData,
  sportLabels,
  weekdayLabels,
} from "@/lib/training-options/contracts";
import type {
  LocationRestriction,
  OptionsContext,
  OptionsData,
  ResolvedGroup,
  SlotDetails,
  WeeklySlot,
} from "@/lib/training-options/contracts";
import type { ScheduleContext } from "@/lib/calendar/constraints";
import SlotFields from "./slot-fields";

const issueLabels: Record<string, string> = {
  LOCATION_ARCHIVED: "A helyszín törölt, jelenleg nem használható.",
  BOAT_TRANSPORT_NOT_DECLARED: "A hajó szállítása még nincs megadva.",
  LOCATION_TEMPORARILY_RESTRICTED: "Időszaki korlátozás érvényes.",
};
const weekday = (date: string) =>
  (new Date(date + "T12:00:00Z").getUTCDay() + 6) % 7;
function days(first: string) {
  return Array.from({ length: 7 }, (_, i) => {
    const date = new Date(first + "T12:00:00Z");
    date.setUTCDate(date.getUTCDate() + i);
    return date.toISOString().slice(0, 10);
  });
}
export default function CurrentWeek({
  context,
  schedule,
  disabled,
  save,
  onContinue,
}: {
  context: OptionsContext;
  schedule: ScheduleContext | null;
  disabled: boolean;
  save: (data: OptionsData) => Promise<boolean>;
  onContinue?: () => void;
}) {
  const [editing, setEditing] = useState<{
      date: string;
      slot: WeeklySlot;
      details: SlotDetails;
      available: boolean;
      additional: boolean;
    } | null>(null),
    [restriction, setRestriction] = useState<LocationRestriction | null>(null),
    [error, setError] = useState("");
  const data = context.data,
    dates = days(context.start_date);
  const time = (value: string) =>
    new Intl.DateTimeFormat("hu-HU", {
      timeZone: context.timezone_name,
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  function open(date: string, group?: ResolvedGroup) {
    const slot = group
      ? data.weekly_slots.find((s) => s.id === group.slot_id)
      : null;
    setEditing(
      slot
        ? {
            date,
            slot: structuredClone(slot),
            details: structuredClone(group?.details ?? slot.details),
            available: group?.details !== null,
            additional: false,
          }
        : {
            date,
            slot: {
              ...defaultSlot(date),
              end_date: date,
              weekdays: [weekday(date)],
            },
            details: defaultSlot(date).details,
            available: true,
            additional: true,
          },
    );
    setError("");
  }
  async function saveDay() {
    if (!editing) return;
    let next: OptionsData;
    if (editing.additional)
      next = {
        ...data,
        weekly_slots: [
          ...data.weekly_slots,
          { ...editing.slot, details: editing.details },
        ],
      };
    else {
      const same =
        editing.available &&
        canonical(editing.details) === canonical(editing.slot.details);
      next = {
        ...data,
        exceptions: [
          ...data.exceptions.filter(
            (e) => e.slot_id !== editing.slot.id || e.date !== editing.date,
          ),
          ...(same
            ? []
            : [
                {
                  slot_id: editing.slot.id,
                  date: editing.date,
                  replacement: editing.available ? editing.details : null,
                },
              ]),
        ],
      };
    }
    try {
      readOptionsData(next);
      if (await save(next)) setEditing(null);
    } catch {
      setError("Ellenőrizd az időablakot és jelölj legalább egy helyszínt.");
    }
  }
  async function saveRestriction() {
    if (!restriction) return;
    const next = {
      ...data,
      restrictions: data.restrictions.some((r) => r.id === restriction.id)
        ? data.restrictions.map((r) =>
            r.id === restriction.id ? restriction : r,
          )
        : [...data.restrictions, restriction],
    };
    try {
      readOptionsData(next);
      if (await save(next)) setRestriction(null);
    } catch {
      setError(
        "A helyszín, az érvényes dátumtartomány és legalább egy kieső mozgásforma szükséges.",
      );
    }
  }
  const changed =
    data.exceptions.some((e) => dates.includes(e.date)) ||
    data.restrictions.some(
      (r) => r.start_date <= dates[6] && r.end_date >= dates[0],
    );
  const known = dates.every(
    (date) =>
      context.override_days.includes(date) ||
      schedule?.opportunities.some((o) => o.source_date === date && o.known),
  );
  const dayEditor = editing && (
    <form
      className="pt-options-form pt-day-editor"
      onSubmit={(e) => {
        e.preventDefault();
        void saveDay();
      }}
    >
      <h4>
        {editing.date} ·{" "}
        {editing.additional ? "egyszeri lehetőség" : "napi eltérés"}
      </h4>
      {!editing.additional && (
        <label className="pt-options-check">
          <input
            type="checkbox"
            disabled={disabled}
            checked={editing.available}
            onChange={(e) =>
              setEditing({ ...editing, available: e.target.checked })
            }
          />
          Ezen az alkalmon ráérek
        </label>
      )}
      {editing.available && (
        <SlotFields
          value={editing.details}
          onChange={(details) => setEditing({ ...editing, details })}
          locations={data.locations}
          disabled={disabled}
        />
      )}
      {error && <p role="alert">{error}</p>}
      <div className="pt-options-actions">
        <button className={buttonClass} disabled={disabled}>
          Napi eltérés mentése
        </button>
        {!editing.additional && (
          <button
            type="button"
            className={secondaryClass}
            disabled={disabled}
            onClick={() => {
              const next = {
                ...data,
                exceptions: data.exceptions.filter(
                  (e) =>
                    e.slot_id !== editing.slot.id || e.date !== editing.date,
                ),
              };
              void save(next).then((ok) => {
                if (ok) setEditing(null);
              });
            }}
          >
            Az általános órarendet használom
          </button>
        )}
        <button
          type="button"
          className={secondaryClass}
          disabled={disabled}
          onClick={() => setEditing(null)}
        >
          Elvetés
        </button>
      </div>
    </form>
  );
  return (
    <section className="pt-options-section">
      <h2>Az aktuális hét lehetőségei</h2>
      <p>
        {changed
          ? "Az általános órarend a rögzített napi eltérésekkel érvényes."
          : "Az általános órarendet és a helyszínek lehetőségeit vesszük át. Elég az eltéréseket megadnod."}
      </p>
      {context.timezone_review_required && (
        <p role="alert">
          A mentett órarend időzónája megváltozott. A helyi időpontokat felül
          kell vizsgálni.
        </p>
      )}
      <div className="pt-schedule-days">
        {dates.map((date) => {
          const groups = context.groups.filter((g) => g.date === date);
          const legacy =
            schedule?.opportunities.filter(
              (o) => o.source_date === date && o.source !== "training_options",
            ) ?? [];
          const declared = context.override_days.includes(date);
          return (
            <section
              className="pt-panel pt-schedule-day"
              key={date}
              aria-label={`${weekdayLabels[weekday(date)]} · ${date}`}
              data-date={date}
              data-editing={editing?.date === date}
            >
              <header className="pt-schedule-day-header">
                <div>
                  <h3>
                    {weekdayLabels[weekday(date)]}
                    {date === context.local_today ? " · Ma" : ""}
                  </h3>
                  <p className="pt-options-meta">{date}</p>
                </div>
                {declared && (
                  <button
                    type="button"
                    className={secondaryClass}
                    disabled={
                      disabled ||
                      !!editing ||
                      !!restriction ||
                      !data.locations.some((l) => !l.archived)
                    }
                    onClick={() => open(date)}
                  >
                    + Egyszeri lehetőség
                  </button>
                )}
              </header>
              <div className="pt-schedule-windows">
                {groups.map((group) => (
                  <div className="pt-schedule-window" key={group.key}>
                    {group.details ? (
                      <>
                        <strong>
                          {group.details.start_time}–{group.details.end_time}
                          {group.details.ends_next_day ? " (+1 nap)" : ""} ·
                          legfeljebb {group.details.max_minutes} perc
                        </strong>
                        <small className="pt-options-meta">
                          {group.overridden
                            ? "Napi eltérés"
                            : "Általános órarend"}{" "}
                          · közös időkeret az alternatíváknak
                        </small>
                      </>
                    ) : (
                      <strong>Erre az alkalomra nem érek rá</strong>
                    )}
                    <div className="pt-schedule-locations">
                      {group.alternatives.map((alternative) => (
                        <div
                          className="pt-schedule-location"
                          key={alternative.location_id}
                        >
                          <strong>{alternative.name}</strong>
                          <span>
                            {alternative.sports.length
                              ? alternative.sports
                                  .map((sport) => sportLabels[sport])
                                  .join(" / ")
                              : "Itt most nincs használható mozgásforma"}
                          </span>
                          {alternative.combine_allowed && (
                            <small>Egy alkalmon belül kombinálhatók.</small>
                          )}
                          {alternative.issues.map((issue) => (
                            <small key={issue}>
                              {issueLabels[issue] ??
                                "A helyszíni feltételek pontosítandók."}
                            </small>
                          ))}
                        </div>
                      ))}
                    </div>
                    <div className="pt-options-actions">
                      <button
                        type="button"
                        className={secondaryClass}
                        disabled={disabled || !!editing || !!restriction}
                        onClick={() => open(date, group)}
                      >
                        Eltérés
                      </button>
                    </div>
                  </div>
                ))}
                {!groups.length &&
                  (declared ? (
                    <p className="pt-options-empty">Nem érek rá</p>
                  ) : legacy.length ? (
                    <>
                      {legacy.map((opportunity) => (
                        <div
                          className="pt-schedule-window"
                          key={opportunity.key}
                        >
                          <strong>
                            {opportunity.start_at && opportunity.end_at
                              ? `${time(opportunity.start_at)}–${time(opportunity.end_at)}`
                              : "Időpont pontosítandó"}
                          </strong>
                          <small className="pt-options-meta">
                            Korábbi mentett időbeosztás · legfeljebb{" "}
                            {opportunity.max_minutes} perc
                          </small>
                        </div>
                      ))}
                      <Link href="/" className="underline">
                        Korábbi keretek a Naptárban
                      </Link>
                    </>
                  ) : (
                    <p className="pt-options-empty">
                      Még nincs megadott órarend
                    </p>
                  ))}
              </div>
              {editing?.date === date && dayEditor}
            </section>
          );
        })}
      </div>
      {schedule && schedule.conflicts.length > 0 && (
        <p className="pt-options-meta">
          A Napirend további elfoglaltságokat vagy ütközéseket jelez. A tervező
          a ténylegesen megmaradó idővel számol.{" "}
          <Link className="underline" href="/">
            Naptár megnyitása
          </Link>
        </p>
      )}

      <div className="pt-options-actions">
        <button
          type="button"
          className={secondaryClass}
          disabled={
            disabled ||
            !!editing ||
            !!restriction ||
            !data.locations.some((l) => !l.archived)
          }
          onClick={() => {
            setRestriction({
              id: crypto.randomUUID(),
              location_id: data.locations.find((l) => !l.archived)!.id,
              start_date: context.local_today,
              end_date: context.local_today,
              unavailable_sports: [],
              reason: "",
            });
            setError("");
          }}
        >
          Helyszín ideiglenes korlátozása
        </button>
        <Link className={secondaryClass} href="/training-options/schedule">
          Általános órarend szerkesztése
        </Link>
      </div>
      {restriction && (
        <form
          className="pt-panel pt-options-form"
          onSubmit={(e) => {
            e.preventDefault();
            void saveRestriction();
          }}
        >
          <h3>Helyszíni kivétel · az általános lehetőségek megmaradnak</h3>
          <fieldset disabled={disabled}>
            <Select
              label="Érintett helyszín"
              value={restriction.location_id}
              onChange={(e) =>
                setRestriction({
                  ...restriction,
                  location_id: e.target.value,
                  unavailable_sports: [],
                })
              }
            >
              {data.locations.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </Select>
            <div className="pt-options-columns">
              <Field
                label="Érvényes ettől"
                type="date"
                required
                value={restriction.start_date}
                onChange={(e) =>
                  setRestriction({ ...restriction, start_date: e.target.value })
                }
              />
              <Field
                label="Eddig"
                type="date"
                required
                min={restriction.start_date}
                value={restriction.end_date}
                onChange={(e) =>
                  setRestriction({ ...restriction, end_date: e.target.value })
                }
              />
            </div>
            <fieldset className="pt-options-checks">
              <legend>Ebben az időszakban nem elérhető</legend>
              {data.locations
                .find((l) => l.id === restriction.location_id)
                ?.sports.map((sport) => (
                  <label key={sport}>
                    <input
                      type="checkbox"
                      checked={restriction.unavailable_sports.includes(sport)}
                      onChange={(e) =>
                        setRestriction({
                          ...restriction,
                          unavailable_sports: e.target.checked
                            ? [...restriction.unavailable_sports, sport]
                            : restriction.unavailable_sports.filter(
                                (s) => s !== sport,
                              ),
                        })
                      }
                    />
                    {sportLabels[sport]}
                  </label>
                ))}
            </fieldset>
            <Field
              label="Indok · opcionális"
              maxLength={1000}
              value={restriction.reason}
              onChange={(e) =>
                setRestriction({ ...restriction, reason: e.target.value })
              }
            />
            <div className="pt-options-actions">
              <button className={buttonClass}>Korlátozás mentése</button>
              <button
                type="button"
                className={secondaryClass}
                onClick={() => setRestriction(null)}
              >
                Elvetés
              </button>
            </div>
          </fieldset>
        </form>
      )}
      {data.restrictions
        .filter((r) => r.start_date <= dates[6] && r.end_date >= dates[0])
        .map((r) => (
          <div key={r.id} className="pt-panel">
            <strong>
              {data.locations.find((l) => l.id === r.location_id)?.name}
            </strong>
            <p>
              {r.start_date} – {r.end_date} · kiesik:{" "}
              {r.unavailable_sports.map((s) => sportLabels[s]).join(", ")}
              {r.reason ? ` · ${r.reason}` : ""}
            </p>
            <button
              type="button"
              className={secondaryClass}
              disabled={disabled || !!editing || !!restriction}
              onClick={() =>
                void save({
                  ...data,
                  restrictions: data.restrictions.filter(
                    (item) => item.id !== r.id,
                  ),
                })
              }
            >
              Korlátozás feloldása
            </button>
          </div>
        ))}
      {error && !editing && <p role="alert">{error}</p>}
      {onContinue && (
        <button
          type="button"
          className={buttonClass}
          disabled={
            disabled ||
            !!editing ||
            !!restriction ||
            !known ||
            context.timezone_review_required
          }
          onClick={onContinue}
        >
          {changed ? "Áttekintettem, tovább" : "Változás nélkül tovább"}
        </button>
      )}
      {!known && (
        <p className="pt-options-meta">
          A továbblépéshez a hiányzó napok kereteit is add meg az általános
          órarendben. Az elérhetetlennek jelölt nap is teljes értékű válasz.
        </p>
      )}
    </section>
  );
}
