"use client";
import { useState } from "react";
import { addDays, day } from "@/lib/planning-cycles/contracts";
import type { BoundaryRevision, Period } from "@/lib/planning-cycles/contracts";
import {
  Area,
  buttonClass,
  Field,
  Message,
  secondaryClass,
  Select,
} from "@/components/planning-goals/fields";

export default function BoundaryEditor({
  value,
  periods,
  change,
  submit,
  invalid,
  today,
}: {
  value: BoundaryRevision;
  periods: Period[];
  change: (value: BoundaryRevision) => void;
  submit: (value: BoundaryRevision) => void;
  invalid: (message: string) => void;
  today: string;
}) {
  const [review, setReview] = useState(false),
    [accepted, setAccepted] = useState(false);
  const mesos = periods
    .filter((p) => p.period_type === "MESOCYCLE")
    .sort((a, b) => a.start_date.localeCompare(b.start_date));
  const pairs = mesos.flatMap((p, i) => {
    const next = mesos[i + 1];
    return next &&
      next.parent_id === p.parent_id &&
      next.start_date === addDays(p.end_date, 1) &&
      p.end_date >= today
      ? [{ left: p, right: next }]
      : [];
  });
  const pair = pairs.find(
    (p) =>
      p.left.id === value.left_period_id &&
      p.right.id === value.right_period_id,
  );
  function patch(p: Partial<BoundaryRevision>) {
    setReview(false);
    setAccepted(false);
    change({ ...value, ...p });
  }
  return (
    <div className="space-y-5 rounded-xl border border-zinc-600 p-5">
      <h3 className="font-semibold">Mezociklushatár felülvizsgálata</h3>
      <p className="text-sm leading-6 text-zinc-300">
        A két szomszédos ciklus közös tervezett határát módosítjuk. A
        makrociklus vége és a főversenyek dátumai megmaradnak célpontnak. A
        fáradtság, a fittségi állapot és a fejlődés értékelését itt te adod meg.
      </p>
      {!pairs.length ? (
        <Message>
          Nincs módosítható mai vagy jövőbeli közös mezociklushatár.
        </Message>
      ) : (
        <form
          className="space-y-5"
          onSubmit={(e) => {
            e.preventDefault();
            try {
              day(value.new_end_date);
              if (
                !pair ||
                value.new_end_date < pair.left.start_date ||
                value.new_end_date >= pair.right.end_date ||
                value.new_end_date < today ||
                value.new_end_date === pair.left.end_date
              )
                throw new Error(
                  "A határ legyen mai vagy jövőbeli, különbözzön a korábbitól, és mindkét ciklusnak maradjon legalább egy napja.",
                );
              setReview(true);
            } catch (e) {
              invalid(
                e instanceof Error ? e.message : "Ellenőrizd a közös határt.",
              );
            }
          }}
        >
          <Select
            label="Felülvizsgált közös határ"
            name="boundary.pair"
            value={value.left_period_id}
            required
            onChange={(e) => {
              const p = pairs.find((p) => p.left.id === e.target.value)!;
              patch({
                left_period_id: p.left.id,
                right_period_id: p.right.id,
                new_end_date: p.left.end_date,
              });
            }}
          >
            {pairs.map((p) => (
              <option key={p.left.id} value={p.left.id}>
                {p.left.title} → {p.right.title} · jelenlegi határ:{" "}
                {p.left.end_date}
              </option>
            ))}
          </Select>
          <Field
            label="Az első mezociklus új tervezett zárónapja"
            name="boundary.end"
            type="date"
            value={value.new_end_date}
            required
            min={pair ? [pair.left.start_date, today].sort().at(-1) : today}
            max={pair ? addDays(pair.right.end_date, -1) : undefined}
            onChange={(e) => patch({ new_end_date: e.target.value })}
          />
          <Select
            label="Felülvizsgálat oka"
            name="boundary.reason"
            value={value.reason}
            onChange={(e) =>
              patch({ reason: e.target.value as BoundaryRevision["reason"] })
            }
          >
            <option value="fatigue">
              Túlzott fáradtság / regenerációs igény
            </option>
            <option value="progress_continues">
              Folyamatos fejlődés, elfogadható fáradtság
            </option>
            <option value="plateau">Fejlődés megtorpanása</option>
            <option value="calendar">Naptári igazítás</option>
            <option value="other">Más ok</option>
          </Select>
          <Area
            label="Megfigyelések: fáradtság, fittségi állapot, fejlődés"
            name="boundary.observations"
            required
            maxLength={2000}
            value={value.observations}
            onChange={(e) => patch({ observations: e.target.value })}
          />
          <Area
            label="Döntés indoklása és a következő ciklus felülvizsgálata"
            name="boundary.rationale"
            required
            maxLength={2000}
            value={value.rationale}
            onChange={(e) => patch({ rationale: e.target.value })}
          />
          <button className={secondaryClass} type="submit">
            Határmódosítás áttekintése
          </button>
          {review && pair && (
            <div className="space-y-4 border-t border-zinc-700 pt-4">
              <p className="text-sm">
                {pair.left.title}: {pair.left.start_date} – {value.new_end_date}
                <br />
                {pair.right.title}: {addDays(value.new_end_date, 1)} –{" "}
                {pair.right.end_date}
              </p>
              <Message>
                A mentés után a következő ciklus terhelését, képességcéljait és
                mérési időablakait felül kell vizsgálni a főversenyekhez képest.
                A korábbi mérési protokollok megmaradnak az eredeti
                tartalmukkal.
              </Message>
              <label className="flex gap-3 text-sm">
                <input
                  type="checkbox"
                  name="boundary.accept"
                  checked={accepted}
                  onChange={(e) => setAccepted(e.target.checked)}
                />
                Jóváhagyom a közös határ módosítását, és felülvizsgálom az
                érintett terhelést és mérési tervet.
              </label>
              <button
                className={buttonClass}
                type="button"
                disabled={!accepted}
                onClick={() =>
                  submit({
                    ...value,
                    observations: value.observations.trim(),
                    rationale: value.rationale.trim(),
                  })
                }
              >
                Jóváhagyott ciklushatár mentése
              </button>
            </div>
          )}
        </form>
      )}
    </div>
  );
}
