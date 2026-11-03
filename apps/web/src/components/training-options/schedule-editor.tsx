"use client";
import Link from "next/link";
import { useState } from "react";
import {
  Field,
  buttonClass,
  secondaryClass,
} from "@/components/planning-goals/fields";
import {
  defaultSlot,
  readOptionsData,
  sportLabels,
  weekdayLabels,
} from "@/lib/training-options/contracts";
import type { OptionsData, WeeklySlot } from "@/lib/training-options/contracts";
import SlotFields from "./slot-fields";

export function splitWeeklySlots(data: OptionsData): OptionsData {
  const copy = structuredClone(data),
    mapping = new Map<string, Map<number, string>>();
  copy.weekly_slots = data.weekly_slots.flatMap((slot) =>
    slot.weekdays.map((day, i) => {
      const id = i === 0 ? slot.id : crypto.randomUUID();
      if (!mapping.has(slot.id)) mapping.set(slot.id, new Map());
      mapping.get(slot.id)!.set(day, id);
      return { ...structuredClone(slot), id, weekdays: [day] };
    }),
  );
  copy.exceptions = data.exceptions.map((item) => ({
    ...structuredClone(item),
    slot_id:
      mapping
        .get(item.slot_id)
        ?.get((new Date(item.date + "T12:00:00Z").getUTCDay() + 6) % 7) ??
      item.slot_id,
  }));
  return copy;
}
export default function ScheduleEditor({
  data,
  today,
  disabled,
  save,
}: {
  data: OptionsData;
  today: string;
  disabled: boolean;
  save: (data: OptionsData) => Promise<boolean>;
}) {
  const [draft, setDraft] = useState(() => ({
    ...splitWeeklySlots(data),
    schedule_start_date: data.schedule_start_date ?? today,
  }));
  const [editing, setEditing] = useState<WeeklySlot | null>(null);
  const [error, setError] = useState("");
  function put(slot: WeeklySlot) {
    setDraft((value) => ({
      ...value,
      weekly_slots: value.weekly_slots.some((s) => s.id === slot.id)
        ? value.weekly_slots.map((s) => (s.id === slot.id ? slot : s))
        : [...value.weekly_slots, slot],
    }));
    setEditing(null);
  }
  async function submit() {
    try {
      readOptionsData(draft);
      if (editing)
        throw Error(
          "Az időablak megkezdett módosítását előbb vedd át vagy vesd el.",
        );
      setError("");
      await save(draft);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ellenőrizd az órarendet.");
    }
  }
  function adopt() {
    if (!editing) return;
    try {
      readOptionsData({
        ...draft,
        weekly_slots: draft.weekly_slots.some((s) => s.id === editing.id)
          ? draft.weekly_slots.map((s) => (s.id === editing.id ? editing : s))
          : [...draft.weekly_slots, editing],
      });
      put(editing);
      setError("");
    } catch {
      setError("Érvényes időablak és legalább egy helyszín szükséges.");
    }
  }
  return (
    <section className="pt-options-section">
      <div className="pt-section-heading">
        <div>
          <h2>Általános órarend</h2>
          <p>
            Az itt megadott hét módosításig ismétlődik. Egy idősávhoz több
            helyszín is választható.
          </p>
        </div>
      </div>
      {!data.locations.some((l) => !l.archived) && (
        <p>
          Az órarendhez előbb{" "}
          <Link href="/training-options/locations" className="underline">
            vegyél fel egy helyszínt
          </Link>
          .
        </p>
      )}
      <fieldset className="pt-options-columns" disabled={disabled}>
        <Field
          label="Általános órarend érvényes ettől"
          type="date"
          required
          value={draft.schedule_start_date ?? ""}
          onChange={(e) =>
            setDraft({ ...draft, schedule_start_date: e.target.value })
          }
        />
        <Field
          label="Eddig · üresen módosításig"
          type="date"
          min={draft.schedule_start_date ?? undefined}
          value={draft.schedule_end_date ?? ""}
          onChange={(e) =>
            setDraft({ ...draft, schedule_end_date: e.target.value || null })
          }
        />
      </fieldset>
      <div className="pt-schedule-days">
        {weekdayLabels.map((day, index) => {
          const slots = draft.weekly_slots.filter((s) =>
            s.weekdays.includes(index),
          );
          const isEditing = editing?.weekdays.includes(index) ?? false;
          return (
            <section
              className="pt-panel pt-schedule-day"
              key={day}
              aria-label={day}
              data-weekday={index}
              data-editing={isEditing}
            >
              <header className="pt-schedule-day-header">
                <div>
                  <h3>{day}</h3>
                  <p className="pt-options-meta">Általános heti lehetőségek</p>
                </div>
                <button
                  type="button"
                  className={secondaryClass}
                  disabled={
                    disabled ||
                    !!editing ||
                    !data.locations.some((l) => !l.archived)
                  }
                  onClick={() => {
                    setEditing({
                      ...defaultSlot(draft.schedule_start_date ?? today),
                      weekdays: [index],
                    });
                    setError("");
                  }}
                >
                  + Idősáv
                </button>
              </header>
              <div className="pt-schedule-windows">
                {slots.map((slot) => (
                  <div className="pt-schedule-window" key={slot.id}>
                    <strong>
                      {slot.details.start_time}–{slot.details.end_time}
                      {slot.details.ends_next_day ? " (+1 nap)" : ""} ·
                      legfeljebb {slot.details.max_minutes} perc
                    </strong>
                    <div className="pt-schedule-locations">
                      {slot.details.location_ids.map((id) => {
                        const location = draft.locations.find(
                          (l) => l.id === id,
                        );
                        return (
                          <div key={id} className="pt-schedule-location">
                            <span>
                              {location?.name ?? "Hiányzó helyszín"}
                              {location?.archived
                                ? " · törölt, jelenleg nem használható"
                                : ""}
                            </span>
                            <small>
                              {location?.sports
                                .map((s) => sportLabels[s])
                                .join(" / ")}
                            </small>
                          </div>
                        );
                      })}
                    </div>
                    <small className="pt-options-meta">
                      {slot.details.location_ids.length} helyszín · egy közös
                      időkeret
                      {slot.start_date === slot.end_date
                        ? " · egyszeri alkalom"
                        : ""}
                    </small>
                    <div className="pt-options-actions">
                      <button
                        type="button"
                        className={secondaryClass}
                        disabled={disabled || !!editing}
                        onClick={() => {
                          setEditing(structuredClone(slot));
                          setError("");
                        }}
                      >
                        Módosítás
                      </button>
                      <button
                        type="button"
                        className={secondaryClass}
                        disabled={disabled || !!editing}
                        onClick={() =>
                          setDraft({
                            ...draft,
                            weekly_slots: draft.weekly_slots.filter(
                              (s) => s.id !== slot.id,
                            ),
                            exceptions: draft.exceptions.filter(
                              (e) => e.slot_id !== slot.id,
                            ),
                          })
                        }
                      >
                        Idősáv eltávolítása
                      </button>
                    </div>
                  </div>
                ))}
                {!slots.length && (
                  <p className="pt-options-empty">
                    Nem érek rá · ide adhatsz meg időablakot.
                  </p>
                )}
              </div>
              {editing && isEditing && (
                <form
                  className="pt-options-form pt-day-editor"
                  onSubmit={(e) => {
                    e.preventDefault();
                    adopt();
                  }}
                >
                  <h4>{day} · általános időablak</h4>
                  <SlotFields
                    value={editing.details}
                    onChange={(details) => setEditing({ ...editing, details })}
                    locations={draft.locations}
                    disabled={disabled}
                  />
                  {error && <p role="alert">{error}</p>}
                  <div className="pt-options-actions">
                    <button className={buttonClass} disabled={disabled}>
                      Idősáv átvétele az órarend vázlatába
                    </button>
                    <button
                      type="button"
                      className={secondaryClass}
                      disabled={disabled}
                      onClick={() => {
                        setEditing(null);
                        setError("");
                      }}
                    >
                      Elvetés
                    </button>
                  </div>
                  <p className="pt-options-meta">
                    A teljes általános órarendet az átvétel után külön mentsd
                    el.
                  </p>
                </form>
              )}
            </section>
          );
        })}
      </div>
      <p className="pt-options-meta">
        A felsorolt helyszínek egymás alternatívái. A felszerelést és a
        mozgásformákat mindig a választott helyszíntől vesszük át. A napi
        eltérések külön megmaradnak.
      </p>
      {error && !editing && <p role="alert">{error}</p>}
      <div className="pt-options-actions">
        <button
          type="button"
          className={buttonClass}
          disabled={disabled || !!editing}
          onClick={() => void submit()}
        >
          Általános órarend mentése
        </button>
        <button
          type="button"
          className={secondaryClass}
          disabled={disabled}
          onClick={() => {
            setDraft({
              ...splitWeeklySlots(data),
              schedule_start_date: data.schedule_start_date ?? today,
            });
            setEditing(null);
            setError("");
          }}
        >
          Nem mentett módosítások elvetése
        </button>
      </div>
    </section>
  );
}
