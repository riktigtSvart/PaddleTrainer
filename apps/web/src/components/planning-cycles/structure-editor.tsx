"use client";
import { useState } from "react";
import {
  addDays,
  day,
  mesocycles,
  moveDraftBoundary,
  splitMacro,
} from "@/lib/planning-cycles/contracts";
import type {
  MacroInput,
  PeriodInput,
  Program,
} from "@/lib/planning-cycles/contracts";
import { Field, secondaryClass } from "@/components/planning-goals/fields";

function middle(m: MacroInput) {
  try {
    return new Date(
      (day(m.start_date).getTime() + day(m.end_date).getTime()) / 2,
    )
      .toISOString()
      .slice(0, 10);
  } catch {
    return "";
  }
}
export default function StructureEditor({
  value,
  change,
  invalid,
}: {
  value: Program;
  change: (program: Program) => void;
  invalid: (message: string) => void;
}) {
  const [splitDates, setSplitDates] = useState<Record<string, string>>({});
  function macro(index: number, patch: Partial<MacroInput>) {
    change({
      ...value,
      macrocycles: value.macrocycles.map((m, i) =>
        i === index ? { ...m, ...patch } : m,
      ),
    });
  }
  function updateSeason(index: number, patch: Partial<PeriodInput>) {
    change({
      ...value,
      seasons: value.seasons.map((s, i) =>
        i === index ? { ...s, ...patch } : s,
      ),
    });
  }
  function attempt(action: () => void) {
    try {
      action();
    } catch (e) {
      invalid(
        e instanceof Error ? e.message : "Ellenőrizd a ciklusok dátumait.",
      );
    }
  }
  return (
    <div className="space-y-6">
      <p className="text-sm leading-6 text-zinc-300">
        Ez a kezdeti felosztás tervezett, rugalmas időkeret. A mezociklus a
        fáradtság, a fittségi állapot és a fejlődés felülvizsgálata alapján
        rövidülhet vagy hosszabbodhat. A pontos főversenynapok a későbbi
        újratervezés célpontjai. A közös határ átírása a szomszéd kezdetét is
        igazítja; a terhelés és a mérési protokoll külön felülvizsgálandó.
      </p>
      {value.planning_basis && (
        <Field
          label="Kiinduló mezociklushossz (nap, csak tervezési javaslat)"
          name="initial_mesocycle_days"
          type="number"
          min={1}
          max={366}
          step={1}
          required
          value={value.planning_basis.initial_mesocycle_days}
          onChange={(e) => {
            const days = Number(e.target.value);
            if (Number.isInteger(days) && days >= 1 && days <= 366)
              change({
                ...value,
                planning_basis: {
                  ...value.planning_basis!,
                  initial_mesocycle_days: days,
                },
              });
          }}
          hint="A hossz átírása után az újrabontás gombbal készíthetsz új javaslatot. Az egyes közös határokat külön is állíthatod."
        />
      )}
      {!!value.seasons.length && (
        <details className="rounded-xl border border-zinc-700 p-4">
          <summary className="cursor-pointer font-medium">
            Szezonok időhatárai
          </summary>
          <div className="mt-5 space-y-5">
            {value.seasons.map((s, i) => (
              <div key={s.key} className="grid gap-3 sm:grid-cols-3">
                <Field
                  label={`${i + 1}. szezon neve`}
                  value={s.title}
                  maxLength={200}
                  required
                  onChange={(e) => updateSeason(i, { title: e.target.value })}
                />
                <Field
                  label="Szezon kezdete"
                  name={`season.${i}.start`}
                  type="date"
                  value={s.start_date}
                  required
                  onChange={(e) =>
                    updateSeason(i, { start_date: e.target.value })
                  }
                />
                <Field
                  label="Szezon vége"
                  name={`season.${i}.end`}
                  type="date"
                  value={s.end_date}
                  required
                  onChange={(e) =>
                    updateSeason(i, { end_date: e.target.value })
                  }
                />
              </div>
            ))}
            <button
              type="button"
              className={secondaryClass}
              onClick={() =>
                attempt(() =>
                  change({
                    ...value,
                    macrocycles: value.seasons.map((s, i) => ({
                      key: `macro-${i + 1}`,
                      title: `${i + 1}. makrociklus`,
                      season_key: s.key,
                      start_date: s.start_date,
                      end_date: s.end_date,
                      mesocycles: mesocycles(
                        s.start_date,
                        s.end_date,
                        `macro-${i + 1}`,
                        value.planning_basis?.initial_mesocycle_days ?? 28,
                      ),
                    })),
                  }),
                )
              }
            >
              Új ciklusbontás a megadott szezonhatárokból
            </button>
            <p className="text-xs text-zinc-400">
              Ez a gomb újra elkészíti a piszkozat makro- és mezociklusait.
            </p>
          </div>
        </details>
      )}
      {value.macrocycles.map((m, i) => (
        <fieldset
          key={m.key}
          className="space-y-4 rounded-xl border border-zinc-700 p-4 sm:p-5"
        >
          <legend className="px-2 font-semibold">
            {m.title || "Makrociklus"}
          </legend>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field
              label="Makrociklus neve"
              name={`macro.${i}.title`}
              value={m.title}
              maxLength={200}
              required
              onChange={(e) => macro(i, { title: e.target.value })}
            />
            <Field
              label="Makrociklus kezdete"
              name={`macro.${i}.start`}
              type="date"
              value={m.start_date}
              required
              onChange={(e) => macro(i, { start_date: e.target.value })}
            />
            <Field
              label="Makrociklus vége"
              name={`macro.${i}.end`}
              type="date"
              value={m.end_date}
              required
              onChange={(e) => macro(i, { end_date: e.target.value })}
            />
          </div>
          <button
            type="button"
            className={secondaryClass}
            onClick={() =>
              attempt(() =>
                macro(i, {
                  mesocycles: mesocycles(
                    m.start_date,
                    m.end_date,
                    m.key,
                    value.planning_basis?.initial_mesocycle_days ?? 28,
                  ),
                }),
              )
            }
          >
            Mezociklusok újrabontása a kiinduló hosszal
          </button>
          {["olympic", "season"].includes(value.mode) && (
            <div className="flex flex-wrap items-end gap-3">
              <Field
                label="Az első makrociklus utolsó napja bontáskor"
                type="date"
                value={splitDates[m.key] ?? middle(m)}
                onChange={(e) =>
                  setSplitDates({ ...splitDates, [m.key]: e.target.value })
                }
              />
              <button
                type="button"
                className={secondaryClass}
                disabled={value.macrocycles.length >= 24}
                onClick={() =>
                  attempt(() =>
                    change(
                      splitMacro(value, i, splitDates[m.key] ?? middle(m)),
                    ),
                  )
                }
              >
                Makrociklus kettébontása
              </button>
            </div>
          )}
          <details open={i === 0}>
            <summary className="cursor-pointer py-2 text-sm text-teal-200">
              Mezociklusok szerkesztése · {m.mesocycles.length} blokk
            </summary>
            <div className="mt-3 space-y-4">
              {m.mesocycles.map((s, j) => (
                <div
                  key={s.key}
                  className="grid gap-3 border-l-2 border-zinc-700 pl-4 sm:grid-cols-3"
                >
                  <Field
                    label={`${j + 1}. mezociklus neve`}
                    value={s.title}
                    maxLength={200}
                    required
                    onChange={(e) =>
                      macro(i, {
                        mesocycles: m.mesocycles.map((n, k) =>
                          k === j ? { ...n, title: e.target.value } : n,
                        ),
                      })
                    }
                  />
                  <Field
                    label="Mezociklus tervezett kezdete"
                    name={`meso.${i}.${j}.start`}
                    type="date"
                    value={s.start_date}
                    required
                    readOnly={j === 0}
                    min={
                      j
                        ? addDays(m.mesocycles[j - 1].start_date, 1)
                        : m.start_date
                    }
                    max={s.end_date}
                    onChange={(e) =>
                      attempt(() =>
                        change(
                          moveDraftBoundary(
                            value,
                            i,
                            j - 1,
                            addDays(e.target.value, -1),
                          ),
                        ),
                      )
                    }
                  />
                  <Field
                    label="Mezociklus tervezett vége"
                    name={`meso.${i}.${j}.end`}
                    type="date"
                    value={s.end_date}
                    required
                    readOnly={j === m.mesocycles.length - 1}
                    min={s.start_date}
                    max={
                      j < m.mesocycles.length - 1
                        ? addDays(m.mesocycles[j + 1].end_date, -1)
                        : m.end_date
                    }
                    onChange={(e) =>
                      attempt(() =>
                        change(moveDraftBoundary(value, i, j, e.target.value)),
                      )
                    }
                  />
                  {value.competitions
                    .filter(
                      (c) =>
                        c.status === "planned" &&
                        c.start_date <= s.end_date &&
                        c.end_date >= s.start_date,
                    )
                    .map((c) => (
                      <p
                        key={c.key}
                        className="text-xs leading-5 text-teal-200 sm:col-span-3"
                      >
                        {c.priority === "main" ? "Főverseny" : "Köztes verseny"}
                        : {c.title} · {c.start_date}
                        {c.start_date !== c.end_date ? ` – ${c.end_date}` : ""}
                        {c.profile?.distance_status === "specified"
                          ? ` · ${c.profile.distance_value} ${c.profile.distance_unit}`
                          : ""}
                      </p>
                    ))}
                </div>
              ))}
            </div>
          </details>
        </fieldset>
      ))}
    </div>
  );
}
