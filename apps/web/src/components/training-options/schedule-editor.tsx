"use client";
import { SaveActionButton } from "@/components/planning-data/save-actions";
import Link from "next/link";
import { useState } from "react";
import type { SaveFeedback } from "@/components/planning-data/save-actions";
import { scheduleContent } from "@/lib/training-options/synchronization";
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
  MAX_WEEKLY_SLOTS,
} from "@/lib/training-options/contracts";
import type { OptionsData, WeeklySlot } from "@/lib/training-options/contracts";
import SlotFields from "./slot-fields";
import { useScheduleDraft } from "./use-schedule-draft";
import { slotProblem, scheduleDateProblem } from "@/lib/training-options/slot-validation";
import { firstFormProblem } from "@/lib/forms/validation";

export { splitWeeklySlots } from "@/lib/training-options/schedule-draft";
export default function ScheduleEditor({
  data,
  today,
  disabled: externalDisabled,
  save,
  feedback,
  owner,
}: {
  data: OptionsData;
  today: string;
  disabled: boolean;
  save: (data: OptionsData) => Promise<boolean>;
  feedback?: SaveFeedback;
  owner?: string;
}) {
  const { draft, setDraft, editing, setEditing, dirty, conflict, ready, loaded, notice, blocked, discard, saved } = useScheduleDraft(data, today, owner);
  const disabled = externalDisabled || !ready;
  const [error, setError] = useState("");
  const conflictText = "Az edzésrendet közben máshol is módosították. A saját piszkozatod megmaradt. A mentett változatot a „Nem mentett módosítások elvetése” gombbal veheted át.";
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
      if (conflict) throw Error(conflictText);
      const next = dirty ? { ...data, ...scheduleContent(draft) } : data;
      const dateProblem = scheduleDateProblem(next.schedule_start_date, next.schedule_end_date);
      if (dateProblem) throw Error(dateProblem);
      if (next.weekly_slots.length > MAX_WEEKLY_SLOTS) throw Error(`Egy heti órarendben legfeljebb ${MAX_WEEKLY_SLOTS} idősáv menthető. Most ${next.weekly_slots.length} szerepel benne.`);
      for (const slot of next.weekly_slots) {
        const problem = slotProblem(slot.details, data.locations);
        if (problem) throw Error(`${weekdayLabels[slot.weekdays[0]]}: ${problem}`);
      }
      readOptionsData(next);
      if (editing)
        throw Error(
          "Az időablak megkezdett módosítását előbb vedd át vagy vesd el.",
        );
      setError("");
      if (await save(next)) saved(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ellenőrizd az órarendet.");
    }
  }
  function adopt() {
    if (!editing) return;
    try {
      const dateProblem = scheduleDateProblem(draft.schedule_start_date, draft.schedule_end_date);
      if (dateProblem) throw Error(dateProblem);
      const problem = slotProblem(editing.details, data.locations);
      if (problem) throw Error(problem);
      if (!draft.weekly_slots.some(s => s.id === editing.id) && draft.weekly_slots.length >= MAX_WEEKLY_SLOTS)
        throw Error(`Egy heti órarendben legfeljebb ${MAX_WEEKLY_SLOTS} idősáv menthető.`);
      readOptionsData({
        ...data,
        ...scheduleContent(draft),
        weekly_slots: draft.weekly_slots.some((s) => s.id === editing.id)
          ? draft.weekly_slots.map((s) => (s.id === editing.id ? editing : s))
          : [...draft.weekly_slots, editing],
      });
      put(editing);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ellenőrizd az időablakot és a helyszínt.");
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
      {notice && <p role={blocked ? "alert" : "status"} className="pt-notice">{notice}</p>}
      {blocked && <button type="button" className={secondaryClass} disabled={externalDisabled || !loaded} onClick={discard}>Helyi piszkozat elvetése és a mentett órarend betöltése</button>}
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
          min="1900-01-01"
          max="2100-12-31"
          required
          value={draft.schedule_start_date ?? ""}
          onChange={(e) =>
            setDraft({ ...draft, schedule_start_date: e.target.value })
          }
        />
        <Field
          label="Eddig · üresen módosításig"
          type="date"
          max="2100-12-31"
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
                    draft.weekly_slots.length >= MAX_WEEKLY_SLOTS ||
                    !data.locations.some((l) => !l.archived)
                  }
                  title={draft.weekly_slots.length >= MAX_WEEKLY_SLOTS ? `A heti ${MAX_WEEKLY_SLOTS} idősávos határt elérted.` : undefined}
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
                        const location = data.locations.find(
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
                  onInvalidCapture={event => setError(slotProblem(editing.details, data.locations) ?? firstFormProblem(event.currentTarget)?.text ?? "Ellenőrizd az időablak megjelölt mezőjét.")}
                  onSubmit={(e) => {
                    e.preventDefault();
                    adopt();
                  }}
                >
                  <h4>{day} · általános időablak</h4>
                  <SlotFields
                    value={editing.details}
                    onChange={(details) => { setError(""); setEditing({ ...editing, details }); }}
                    locations={data.locations}
                    disabled={disabled}
                  />
                  {error && error !== slotProblem(editing.details, data.locations) && <p role="alert">{error}</p>}
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
      {conflict && <p role="alert">{conflictText}</p>}
      <div className="pt-options-actions">
        <SaveActionButton saveLabel="Általános edzésrend mentése" saveHint={editing ? "Előbb fejezd be az időablak szerkesztését." : disabled ? "A korábbi edzésrend mentése vagy betöltése még folyamatban van." : "A megadott heti órarendet és az időszakát menti."}
          saveFeedback={error || conflict ? { tone: "error", text: error || conflictText } : feedback?.tone === "error" ? feedback : dirty ? { tone: "info", text: "Az edzésrend módosításai még nincsenek elmentve." } : feedback}
          type="button"
          className={buttonClass}
          disabled={disabled || !!editing || conflict}
          onClick={() => void submit()}
        >
          Általános órarend mentése
        </SaveActionButton>
        <button
          type="button"
          className={secondaryClass}
          disabled={externalDisabled || !loaded}
          onClick={() => {
            discard();
            setError("");
          }}
        >
          Nem mentett módosítások elvetése
        </button>
      </div>
    </section>
  );
}
