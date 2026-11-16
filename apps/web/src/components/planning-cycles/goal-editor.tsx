import Link from "next/link";
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
  if (value.body_mass) return <div className="pt-legacy-weight-goal"><p>Korábban edzéscélként megadott testsúlyszándék: {value.key === "weight_loss" ? "testsúlycsökkentés" : "testsúlytartás"}.</p><p>A rögzítéskor megadott tömeg: {value.body_mass.current_kg} kg{value.body_mass.target_kg ? ` · akkori cél: ${value.body_mass.target_kg} kg` : ""}.</p><Link className="underline" href="/nutrition#body-goals">Testsúlycél kezelése a táplálkozásnál</Link></div>;
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
