import {
  Area,
  Field,
  Select,
  secondaryClass,
} from "@/components/planning-goals/fields";
import { list } from "@/lib/athlete-setup/contracts";
import type {
  Profile,
  SportHistory,
  Constraint,
} from "@/lib/athlete-setup/contracts";
export default function ProfileForm({
  value,
  onChange,
  today,
}: {
  value: Profile;
  onChange: (v: Profile) => void;
  today: string;
}) {
  const edit = (p: Partial<Profile>) => onChange({ ...value, ...p });
  const sport = (i: number, p: Partial<SportHistory>) =>
    edit({
      sport_history: value.sport_history.map((s, k) =>
        k === i ? { ...s, ...p } : s,
      ),
    });
  const constraint = (i: number, p: Partial<Constraint>) =>
    edit({
      constraints: value.constraints.map((s, k) =>
        k === i ? { ...s, ...p } : s,
      ),
    });
  return (
    <div className="space-y-7">
      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-3 font-semibold">Alapadatok</legend>
        <Field
          label="Születési dátum (ha ismert)"
          name="birth_date"
          type="date"
          max={today}
          value={value.birth_date ?? ""}
          onChange={(e) => edit({ birth_date: e.target.value || null })}
        />
        <Select
          label="Élettani referencia szerinti nem"
          name="sex_reference"
          value={value.sex_reference}
          onChange={(e) =>
            edit({ sex_reference: e.target.value as Profile["sex_reference"] })
          }
        >
          {Object.entries({
            unknown: "Még nincs megadva",
            female: "Nő",
            male: "Férfi",
            intersex: "Intersex / egyéni értékelés",
            prefer_not_to_say: "Nem szeretném megadni",
          }).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
        <Field
          label="Célsportág / szakág"
          name="target_sport"
          maxLength={200}
          value={value.target_sport}
          onChange={(e) => edit({ target_sport: e.target.value })}
        />
        <Field
          label="Versenykategória (opcionális)"
          name="competition_category"
          maxLength={200}
          value={value.competition_category}
          onChange={(e) => edit({ competition_category: e.target.value })}
        />
      </fieldset>
      <fieldset className="space-y-4">
        <legend className="mb-3 font-semibold">Sportmúlt, sportáganként</legend>
        <p className="text-sm text-zinc-400">
          A más sportágban szerzett tapasztalat megmarad; ebből önmagában nem
          következik a célsport technikája vagy mozgásszervi terhelhetősége.
        </p>
        <Select
          label="Korábbi sporttapasztalat"
          value={value.sport_history_status}
          onChange={(e) =>
            edit({
              sport_history_status: e.target
                .value as Profile["sport_history_status"],
              sport_history:
                e.target.value === "recorded" ? value.sport_history : [],
            })
          }
        >
          <option value="unknown">Még nincs felmérve</option>
          <option value="none">Még nincs sportmúltam</option>
          <option value="recorded">Van korábbi sporttapasztalatom</option>
        </Select>
        {value.sport_history.map((s, i) => (
          <div
            key={i}
            className="space-y-4 rounded-xl border border-zinc-700 p-4"
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label={`${i + 1}. sportág`}
                required
                maxLength={200}
                value={s.sport}
                onChange={(e) => sport(i, { sport: e.target.value })}
              />
              <Field
                label="Szakág (opcionális)"
                maxLength={200}
                value={s.discipline}
                onChange={(e) => sport(i, { discipline: e.target.value })}
              />
              <Field
                label="Kezdés éve (ha ismert)"
                type="number"
                min={1900}
                max={Number(today.slice(0, 4))}
                value={s.start_year ?? ""}
                onChange={(e) =>
                  sport(i, {
                    start_year:
                      e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
              <Select
                label="Ebben a sportágban elért szint"
                value={s.level}
                onChange={(e) =>
                  sport(i, { level: e.target.value as SportHistory["level"] })
                }
              >
                {Object.entries({
                  unknown: "Még nincs megadva",
                  beginner: "Kezdő",
                  recreational: "Szabadidős",
                  competitive: "Versenyző",
                  professional: "Hivatásos / élversenyző",
                }).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </Select>
              <Field
                label="Szokásos edzésszám hetente ebben a sportágban (ha ismert)"
                type="number"
                min={0}
                max={28}
                value={s.usual_sessions_per_week ?? ""}
                onChange={(e) =>
                  sport(i, {
                    usual_sessions_per_week:
                      e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
              <Field
                label="Legutóbbi aktív nap (opcionális)"
                type="date"
                max={today}
                value={s.last_active_date ?? ""}
                onChange={(e) =>
                  sport(i, { last_active_date: e.target.value || null })
                }
              />
            </div>
            <label className="flex gap-2 text-sm">
              <input
                type="checkbox"
                checked={s.current}
                onChange={(e) => sport(i, { current: e.target.checked })}
              />
              Jelenleg is végzem ezt a sportágat
            </label>
            <Area
              label="Kihagyások, fontos tapasztalatok (opcionális)"
              maxLength={2000}
              value={s.notes}
              onChange={(e) => sport(i, { notes: e.target.value })}
            />
            <button
              type="button"
              className={secondaryClass}
              onClick={() =>
                edit({
                  sport_history: value.sport_history.filter((_, k) => i !== k),
                })
              }
            >
              Sportmúlt bejegyzés törlése
            </button>
          </div>
        ))}
        <button
          type="button"
          className={secondaryClass}
          disabled={value.sport_history.length >= 32}
          onClick={() =>
            edit({
              sport_history_status: "recorded",
              sport_history: [
                ...value.sport_history,
                {
                  sport: "",
                  discipline: "",
                  start_year: null,
                  current: true,
                  last_active_date: null,
                  level: "unknown",
                  usual_sessions_per_week: null,
                  notes: "",
                },
              ],
            })
          }
        >
          Sportág hozzáadása
        </button>
      </fieldset>
      <fieldset className="space-y-4">
        <legend className="mb-3 font-semibold">
          Korlátozások és alkalmazkodás
        </legend>
        <Select
          label="Van edzést érintő állandó vagy ideiglenes korlátozás?"
          name="constraint_status"
          value={value.constraint_status}
          onChange={(e) => {
            const status = e.target.value as Profile["constraint_status"];
            if (
              value.constraints.length &&
              status !== "present" &&
              !window.confirm(
                "A részletes korlátozásbejegyzések kikerülnek ebből a szerkesztett változatból. Folytatod?",
              )
            )
              return;
            edit({
              constraint_status: status,
              constraints: status === "present" ? value.constraints : [],
            });
          }}
        >
          <option value="unknown">Még nincs felmérve</option>
          <option value="none_known">Nincs ismert korlátozás</option>
          <option value="present">Van korlátozás / alkalmazkodási igény</option>
        </Select>
        {value.constraint_status === "present" && (
          <>
            {value.constraints.map((c, i) => (
              <div
                className="space-y-4 rounded-xl border border-zinc-700 p-4"
                key={c.key}
              >
                <div className="grid gap-4 sm:grid-cols-2">
                  <Select
                    label="Időtartam jellege"
                    value={c.duration}
                    onChange={(e) =>
                      constraint(i, {
                        duration: e.target.value as Constraint["duration"],
                      })
                    }
                  >
                    <option value="permanent">Állandó</option>
                    <option value="temporary">Ideiglenes</option>
                  </Select>
                  <Select
                    label="Gyakorlati terület"
                    value={c.area}
                    onChange={(e) =>
                      constraint(i, {
                        area: e.target.value as Constraint["area"],
                      })
                    }
                  >
                    {Object.entries({
                      movement: "Mozgás",
                      vision: "Látás",
                      hearing: "Hallás",
                      medical: "Egészségi állapot / kezelés",
                      other: "Egyéb",
                    }).map(([k, v]) => (
                      <option value={k} key={k}>
                        {v}
                      </option>
                    ))}
                  </Select>
                  <Field
                    label="Érintett terület (opcionális)"
                    maxLength={200}
                    value={c.affected_area}
                    onChange={(e) =>
                      constraint(i, { affected_area: e.target.value })
                    }
                  />
                  <Field
                    label="Kezdete (ha ismert)"
                    type="date"
                    value={c.starts_on ?? ""}
                    onChange={(e) =>
                      constraint(i, { starts_on: e.target.value || null })
                    }
                  />
                  <Field
                    label="Felülvizsgálat napja (ha ismert)"
                    type="date"
                    value={c.review_on ?? ""}
                    onChange={(e) =>
                      constraint(i, { review_on: e.target.value || null })
                    }
                    hint="Ez nem automatikus gyógyulási vagy lejárati dátum."
                  />
                </div>
                <Field
                  label="Kerülendő / korlátozott tevékenységek (vesszővel elválasztva)"
                  maxLength={2000}
                  defaultValue={c.restricted_activities.join(", ")}
                  onChange={(e) =>
                    constraint(i, {
                      restricted_activities: list(e.target.value),
                    })
                  }
                />
                <Area
                  label="Szükséges segítség, eszköz vagy mozgásmódosítás (opcionális)"
                  maxLength={2000}
                  value={c.adaptations}
                  onChange={(e) =>
                    constraint(i, { adaptations: e.target.value })
                  }
                />
                <Area
                  label="Szakembertől kapott edzési keretek (ha vannak)"
                  maxLength={2000}
                  value={c.professional_guidance}
                  onChange={(e) =>
                    constraint(i, { professional_guidance: e.target.value })
                  }
                />
                <button
                  type="button"
                  className={secondaryClass}
                  onClick={() =>
                    edit({
                      constraints: value.constraints.filter((_, k) => k !== i),
                    })
                  }
                >
                  Korlátozás eltávolítása ebből a változatból
                </button>
              </div>
            ))}
            <button
              type="button"
              className={secondaryClass}
              disabled={value.constraints.length >= 32}
              onClick={() =>
                edit({
                  constraints: [
                    ...value.constraints,
                    {
                      key: "c-" + crypto.randomUUID(),
                      duration: "temporary",
                      area: "movement",
                      affected_area: "",
                      restricted_activities: [],
                      adaptations: "",
                      professional_guidance: "",
                      starts_on: null,
                      review_on: null,
                    },
                  ],
                })
              }
            >
              Korlátozás hozzáadása
            </button>
          </>
        )}
        <Select
          label="Jelenleg megadott részvételi keret"
          name="participation"
          value={value.participation}
          onChange={(e) =>
            edit({ participation: e.target.value as Profile["participation"] })
          }
        >
          {Object.entries({
            unknown: "Még nincs tisztázva",
            unrestricted: "Nincs ismert részvételi korlátozás",
            adapted: "Alkalmazkodással edzhetek",
            professional_review: "Szakemberrel tisztázandó",
            paused: "Jelenleg szüneteltetem az edzést",
          }).map(([k, v]) => (
            <option value={k} key={k}>
              {v}
            </option>
          ))}
        </Select>
        <Area
          label="Az app használatához szükséges hozzáférési segítség (opcionális)"
          maxLength={2000}
          value={value.accessibility_needs}
          onChange={(e) => edit({ accessibility_needs: e.target.value })}
        />
      </fieldset>
      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-3 font-semibold">
          Gyakorlati és regenerációs háttér
        </legend>
        <Field
          label="Általában hány napon tudsz edzeni hetente? (ha ismert)"
          type="number"
          min={0}
          max={7}
          step={1}
          value={value.typical_days_per_week ?? ""}
          onChange={(e) =>
            edit({
              typical_days_per_week:
                e.target.value === "" ? null : Number(e.target.value),
            })
          }
        />
        <Field
          label="Szokásos heti időkeret, percben (ha ismert)"
          type="number"
          min={0}
          max={10080}
          step={1}
          value={value.typical_minutes_per_week ?? ""}
          onChange={(e) =>
            edit({
              typical_minutes_per_week:
                e.target.value === "" ? null : Number(e.target.value),
            })
          }
        />
        <Select
          label="Kihagyás / visszatérés"
          value={value.interruption}
          onChange={(e) =>
            edit({ interruption: e.target.value as Profile["interruption"] })
          }
        >
          <option value="unknown">Még nincs megadva</option>
          <option value="none">Nincs jelenlegi kihagyás</option>
          <option value="returning">Kihagyás után térek vissza</option>
        </Select>
        <Field
          label="Legutóbbi edzés napja (ha ismert)"
          type="date"
          max={today}
          value={value.last_training_date ?? ""}
          onChange={(e) => edit({ last_training_date: e.target.value || null })}
        />
        <Field
          label="Általában elérhető eszközök, helyszínek (vesszővel elválasztva)"
          defaultValue={value.resources.join(", ")}
          onChange={(e) => edit({ resources: list(e.target.value) })}
        />
        <Area
          label="Alvás, munka, stressz és regeneráció körülményei (opcionális)"
          maxLength={2000}
          value={value.recovery_notes}
          onChange={(e) => edit({ recovery_notes: e.target.value })}
        />
      </fieldset>
      <p className="text-sm text-zinc-400">
        A közelmúlt edzéseit, alvását, lépéseit, pulzusát és kiinduló méréseit a
        „Mérések és órás adatok” részen veheted át vagy írhatod be kézzel. A
        felmérés önbevallott tervezési keret, nem orvosi engedély.
      </p>
    </div>
  );
}
