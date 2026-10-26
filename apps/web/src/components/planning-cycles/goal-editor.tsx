import { Area, Field, Select } from "@/components/planning-goals/fields";
import type {
  Goal,
  GoalDetails,
  Competition,
} from "@/lib/planning-cycles/contracts";
export function newGoal(key: string): Goal {
  return {
    key,
    target_description: "",
    details: {
      version: "cycle-goal-fields-v0.1",
      direction: ["aerobic_fitness", "strength", "mobility"].includes(key)
        ? "improve"
        : null,
      weekly_sessions: null,
      event_keys: [],
      result_target: "",
      notes: "",
    },
    ...(["weight_loss", "weight_maintenance"].includes(key)
      ? {
          body_mass: {
            current_kg: "",
            ...(key === "weight_loss" ? { target_kg: "" } : {}),
          },
        }
      : {}),
  };
}
export default function GoalEditor({
  value,
  onChange,
  events = [],
}: {
  value: Goal;
  onChange: (v: Goal) => void;
  events?: Competition[];
}) {
  const details: GoalDetails = value.details ?? newGoal(value.key).details!;
  const edit = (change: Partial<GoalDetails>) =>
    onChange({ ...value, details: { ...details, ...change } });
  return (
    <div className="mt-4 space-y-4">
      {!value.details && value.target_description && (
        <p className="text-sm text-zinc-300">
          Korábban megadott cél: {value.target_description}. Új irány
          választásáig ezt őrizzük meg.
        </p>
      )}
      {value.body_mass && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Jelenlegi testsúly (kg)"
            name={`goal.${value.key}.current_kg`}
            inputMode="decimal"
            required
            maxLength={13}
            value={value.body_mass.current_kg}
            onChange={(e) =>
              onChange({
                ...value,
                body_mass: { ...value.body_mass!, current_kg: e.target.value },
              })
            }
          />
          {value.key === "weight_loss" ? (
            <Field
              label="Céltestsúly (kg)"
              name={`goal.${value.key}.target_kg`}
              inputMode="decimal"
              required
              maxLength={13}
              value={value.body_mass.target_kg ?? ""}
              onChange={(e) =>
                onChange({
                  ...value,
                  body_mass: { ...value.body_mass!, target_kg: e.target.value },
                })
              }
            />
          ) : (
            <p className="self-center text-sm text-zinc-300">
              A megadott jelenlegi testsúly megtartása a cél.
            </p>
          )}
        </div>
      )}
      {["aerobic_fitness", "strength", "mobility"].includes(value.key) && (
        <Select
          label="Fejlesztés vagy szinten tartás"
          value={value.details ? (details.direction ?? "improve") : ""}
          onChange={(e) =>
            edit({ direction: e.target.value as "improve" | "maintain" })
          }
        >
          {!value.details && (
            <option value="">A korábbi célleírás marad érvényben</option>
          )}
          <option value="improve">Fejlesztés</option>
          <option value="maintain">Szinten tartás</option>
        </Select>
      )}
      {value.key === "regular_activity" && (
        <Field
          label="Heti edzésszám célja (opcionális)"
          type="number"
          min={1}
          max={28}
          step={1}
          value={details.weekly_sessions ?? ""}
          onChange={(e) =>
            edit({
              weekly_sessions:
                e.target.value === "" ? null : Number(e.target.value),
            })
          }
          hint="Ez szándék; a tényleges napokat és lehetőségeket a naptárban adhatod meg."
        />
      )}
      {value.key === "performance" && (
        <>
          <p className="text-sm text-zinc-300">
            A cél a kiválasztott versenyekhez kapcsolódik. Külön kijelölés
            hiányában a főversenyeket vesszük át.
          </p>
          {!!events.length && (
            <fieldset className="space-y-2">
              <legend className="mb-2 text-sm">
                Célversenyek (opcionális szűkítés)
              </legend>
              {events
                .filter((e) => e.status === "planned")
                .map((event) => (
                  <label className="flex gap-2 text-sm" key={event.key}>
                    <input
                      type="checkbox"
                      checked={details.event_keys.includes(event.key)}
                      onChange={(e) =>
                        edit({
                          event_keys: e.target.checked
                            ? [...details.event_keys, event.key]
                            : details.event_keys.filter((k) => k !== event.key),
                        })
                      }
                    />
                    {event.title || event.key}
                  </label>
                ))}
            </fieldset>
          )}
          <Field
            label="Eredménycél (opcionális)"
            maxLength={500}
            value={details.result_target}
            onChange={(e) => edit({ result_target: e.target.value })}
            hint="Például egy időeredmény vagy helyezés; később pontosítható."
          />
        </>
      )}
      {value.key === "wellbeing" && (
        <p className="text-sm text-zinc-300">
          Általános közérzet és a rendszeres mozgás támogatása. A cél
          kiválasztása önmagában elegendő.
        </p>
      )}
      <Area
        label="Kiegészítés a célhoz (opcionális)"
        maxLength={1500}
        value={details.notes}
        onChange={(e) => edit({ notes: e.target.value })}
      />
    </div>
  );
}
