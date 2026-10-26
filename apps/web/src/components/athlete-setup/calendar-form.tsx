"use client";
import { useState } from "react";
import {
  Area,
  Field,
  Select,
  secondaryClass,
} from "@/components/planning-goals/fields";
import { addDays } from "@/lib/planning-cycles/contracts";
import {
  copyDay,
  list,
  newWindow,
  resizeCalendar,
} from "@/lib/athlete-setup/contracts";
import type {
  Calendar,
  CalendarDay,
  Window,
} from "@/lib/athlete-setup/contracts";
export type PeriodChoice = {
  id: string;
  title: string;
  start_date: string;
  end_date: string;
};
export default function CalendarForm({
  value,
  onChange,
  periods,
  onError,
}: {
  value: Calendar;
  onChange: (v: Calendar) => void;
  periods: PeriodChoice[];
  onError: (s: string) => void;
}) {
  const [first, setFirst] = useState(value.start_date),
    [last, setLast] = useState(value.end_date),
    [view, setView] = useState(0),
    [source, setSource] = useState(value.start_date),
    [selected, setSelected] = useState<string[]>([]);
  function range(start: string, end: string, period: string | null = null) {
    try {
      onChange(resizeCalendar(value, start, end, value.timezone_name, period));
      setFirst(start);
      setLast(end);
      setView(0);
      setSelected([]);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Ellenőrizd az időszakot.");
    }
  }
  const edit = (date: string, change: Partial<CalendarDay>) =>
    onChange({
      ...value,
      days: value.days.map((d) => (d.date === date ? { ...d, ...change } : d)),
    });
  const windowEdit = (date: string, key: string, p: Partial<Window>) => {
    const d = value.days.find((d) => d.date === date)!;
    edit(date, {
      windows: d.windows.map((w) => (w.key === key ? { ...w, ...p } : w)),
    });
  };
  return (
    <div className="space-y-5">
      <p className="text-sm leading-6 text-zinc-300">
        Időzóna: {value.timezone_name}. A konkrét dátumok adják az edzéstervezés
        időkeretét. A kitöltetlen nap ismeretlen marad; az időablak lehetőség,
        nem kötelező edzés.
      </p>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field
          label="Naptár kezdőnapja"
          type="date"
          value={first}
          onChange={(e) => setFirst(e.target.value)}
        />
        <Field
          label="Naptár utolsó napja"
          type="date"
          value={last}
          onChange={(e) => setLast(e.target.value)}
        />
        <button
          className={secondaryClass}
          type="button"
          onClick={() => range(first, last)}
        >
          Időszak alkalmazása
        </button>
      </div>
      <div className="flex flex-wrap gap-3">
        {[7, 14, 28].map((n) => (
          <button
            className={secondaryClass}
            key={n}
            type="button"
            onClick={() => {
              try {
                range(first, addDays(first, n - 1));
              } catch {
                onError("Adj meg kezdőnapot.");
              }
            }}
          >
            {n} nap
          </button>
        ))}
      </div>
      {!!periods.length && (
        <Select
          label="Teljes meglévő mezociklus kiválasztása"
          value={value.mesocycle_id ?? ""}
          onChange={(e) => {
            const p = periods.find((p) => p.id === e.target.value);
            if (p) range(p.start_date, p.end_date, p.id);
            else onChange({ ...value, mesocycle_id: null });
          }}
        >
          <option value="">Egyéni időszak</option>
          {periods.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title} · {p.start_date} – {p.end_date}
            </option>
          ))}
        </Select>
      )}
      <p className="text-sm text-zinc-400">
        Az időszak módosítása megtartja az átfedő napokat. A kikerülő napok
        korábbi mentett változata visszakereshető marad. Ha a mezociklus
        hosszabbodik, a hiányzó új napokat külön kell kitölteni.
      </p>
      <div className="rounded-xl border border-zinc-700 p-4 space-y-3">
        <Select
          label="Melyik nap lehetőségeit másoljuk?"
          value={source}
          onChange={(e) => setSource(e.target.value)}
        >
          {value.days.map((d) => (
            <option value={d.date} key={d.date}>
              {d.date}
            </option>
          ))}
        </Select>
        <p className="text-sm">
          Jelöld ki a célnapokat a naptárban, majd másold át a kiválasztott
          napot. A másolás felülírja a célnapok szerkesztett keretét.
        </p>
        <button
          className={secondaryClass}
          type="button"
          disabled={!selected.length}
          onClick={() => {
            try {
              onChange(copyDay(value, source, selected));
              setSelected([]);
            } catch (e) {
              onError(String(e));
            }
          }}
        >
          Másolás a kijelölt {selected.length} napra
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={secondaryClass}
          disabled={view === 0}
          onClick={() => setView(Math.max(0, view - 7))}
        >
          Előző 7 nap
        </button>
        <span className="text-sm">
          {view + 1}–{Math.min(view + 7, value.days.length)} /{" "}
          {value.days.length} nap
        </span>
        <button
          type="button"
          className={secondaryClass}
          disabled={view + 7 >= value.days.length}
          onClick={() => setView(view + 7)}
        >
          Következő 7 nap
        </button>
      </div>
      {value.days.slice(view, view + 7).map((d) => (
        <fieldset
          key={d.date}
          className="space-y-4 rounded-xl border border-zinc-700 p-4"
        >
          <legend className="px-2 font-semibold">
            {d.date} ·{" "}
            {new Intl.DateTimeFormat("hu-HU", {
              weekday: "long",
              timeZone: "UTC",
            }).format(new Date(d.date + "T12:00:00Z"))}
          </legend>
          <label className="flex gap-2 text-sm">
            <input
              type="checkbox"
              checked={selected.includes(d.date)}
              onChange={(e) =>
                setSelected(
                  e.target.checked
                    ? [...selected, d.date]
                    : selected.filter((k) => k !== d.date),
                )
              }
            />
            Másolási célnap: {d.date}
          </label>
          <Select
            label={`Elérhetőség · ${d.date}`}
            value={d.status}
            onChange={(e) => {
              const status = e.target.value as CalendarDay["status"];
              edit(d.date, {
                status,
                windows:
                  status === "available"
                    ? d.windows.length
                      ? d.windows
                      : [newWindow()]
                    : [],
                max_total_minutes:
                  status === "available" ? d.max_total_minutes : null,
              });
            }}
          >
            <option value="unknown">Még nincs megadva</option>
            <option value="unavailable">Ezen a napon nem tudok edzeni</option>
            <option value="available">Van edzéslehetőség</option>
          </Select>
          {d.status === "available" && (
            <>
              <Field
                label={`Napi összes edzésidő felső korlátja, perc (opcionális) · ${d.date}`}
                type="number"
                min={1}
                max={1440}
                value={d.max_total_minutes ?? ""}
                onChange={(e) =>
                  edit(d.date, {
                    max_total_minutes:
                      e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
              {d.windows.map((w, i) => (
                <div
                  key={w.key}
                  className="space-y-4 rounded-lg bg-zinc-950 p-4"
                >
                  <p className="text-sm font-semibold">
                    {i + 1}. edzéslehetőség
                  </p>
                  <div className="grid gap-4 sm:grid-cols-3">
                    <Field
                      label={`Kezdés · ${d.date} · ${i + 1}`}
                      type="time"
                      required
                      value={w.start_time}
                      onChange={(e) =>
                        windowEdit(d.date, w.key, {
                          start_time: e.target.value,
                        })
                      }
                    />
                    <Field
                      label={`Befejezés · ${d.date} · ${i + 1}`}
                      type="time"
                      required
                      value={w.end_time}
                      onChange={(e) =>
                        windowEdit(d.date, w.key, { end_time: e.target.value })
                      }
                    />
                    <Field
                      label={`Legfeljebb hány perc edzés? · ${d.date} · ${i + 1}`}
                      type="number"
                      min={1}
                      max={1440}
                      required
                      value={w.max_minutes || ""}
                      onChange={(e) =>
                        windowEdit(d.date, w.key, {
                          max_minutes: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                  <label className="flex gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={w.ends_next_day}
                      onChange={(e) =>
                        windowEdit(d.date, w.key, {
                          ends_next_day: e.target.checked,
                        })
                      }
                    />
                    A befejezés a következő napon van
                  </label>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Select
                      label="Sportági lehetőség"
                      value={w.sport_scope}
                      onChange={(e) =>
                        windowEdit(d.date, w.key, {
                          sport_scope: e.target.value as Window["sport_scope"],
                          sports:
                            e.target.value === "specified" ? w.sports : [],
                        })
                      }
                    >
                      <option value="unknown">Még nincs megadva</option>
                      <option value="any">Bármely tervezett sportág</option>
                      <option value="specified">Csak megadott sportágak</option>
                    </Select>
                    <Select
                      label="Terhelési felső keret ebben az ablakban"
                      value={w.effort_cap}
                      onChange={(e) =>
                        windowEdit(d.date, w.key, {
                          effort_cap: e.target.value as Window["effort_cap"],
                        })
                      }
                    >
                      <option value="unknown">Még nincs tisztázva</option>
                      <option value="easy">Csak könnyű</option>
                      <option value="moderate">Legfeljebb közepes</option>
                      <option value="any">
                        Nincs külön ablakhoz kötött korlát
                      </option>
                    </Select>
                    {w.sport_scope === "specified" && (
                      <Field
                        label="Lehetséges sportágak (vesszővel elválasztva)"
                        defaultValue={w.sports.join(", ")}
                        required
                        onChange={(e) =>
                          windowEdit(d.date, w.key, {
                            sports: list(e.target.value),
                          })
                        }
                      />
                    )}
                    <Field
                      label="Elérhető eszközök (vesszővel elválasztva)"
                      defaultValue={w.resources.join(", ")}
                      onChange={(e) =>
                        windowEdit(d.date, w.key, {
                          resources: list(e.target.value),
                        })
                      }
                    />
                    <Field
                      label="Helyszín (opcionális)"
                      maxLength={200}
                      value={w.location}
                      onChange={(e) =>
                        windowEdit(d.date, w.key, { location: e.target.value })
                      }
                    />
                  </div>
                  <Area
                    label="Az alkalom egyéb korlátai (opcionális)"
                    maxLength={2000}
                    value={w.notes}
                    onChange={(e) =>
                      windowEdit(d.date, w.key, { notes: e.target.value })
                    }
                  />
                  <details className="text-sm">
                    <summary className="cursor-pointer">
                      Óraátállítás pontosítása
                    </summary>
                    <div className="mt-3 grid gap-4 sm:grid-cols-2">
                      {(["start_fold", "end_fold"] as const).map((key) => (
                        <Select
                          key={key}
                          label={
                            key === "start_fold"
                              ? "Kezdés előfordulása"
                              : "Befejezés előfordulása"
                          }
                          value={w[key] === null ? "" : String(w[key])}
                          onChange={(e) =>
                            windowEdit(d.date, w.key, {
                              [key]:
                                e.target.value === ""
                                  ? null
                                  : (Number(e.target.value) as 0 | 1),
                            })
                          }
                        >
                          <option value="">Automatikus, ha egyértelmű</option>
                          <option value="0">
                            Az ismétlődő óra első előfordulása
                          </option>
                          <option value="1">
                            Az ismétlődő óra második előfordulása
                          </option>
                        </Select>
                      ))}
                    </div>
                  </details>
                  <button
                    type="button"
                    className={secondaryClass}
                    onClick={() =>
                      edit(d.date, {
                        windows: d.windows.filter((x) => x.key !== w.key),
                        ...(d.windows.length === 1
                          ? { status: "unknown", max_total_minutes: null }
                          : {}),
                      })
                    }
                  >
                    Edzéslehetőség eltávolítása
                  </button>
                </div>
              ))}
              <button
                type="button"
                className={secondaryClass}
                disabled={d.windows.length >= 8}
                onClick={() =>
                  edit(d.date, { windows: [...d.windows, newWindow()] })
                }
              >
                Új edzéslehetőség · {d.date}
              </button>
            </>
          )}
          <Area
            label={`Napi megjegyzés (opcionális) · ${d.date}`}
            maxLength={2000}
            value={d.notes}
            onChange={(e) => edit(d.date, { notes: e.target.value })}
          />
        </fieldset>
      ))}
    </div>
  );
}
