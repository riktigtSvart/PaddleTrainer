import { Field, Select } from "@/components/planning-goals/fields";
import { sportLabels } from "@/lib/training-options/contracts";
import type { Location, SlotDetails } from "@/lib/training-options/contracts";

export default function SlotFields({
  value,
  onChange,
  locations,
  disabled = false,
}: {
  value: SlotDetails;
  onChange: (value: SlotDetails) => void;
  locations: Location[];
  disabled?: boolean;
}) {
  return (
    <fieldset className="pt-options-form" disabled={disabled}>
      <div className="pt-options-columns">
        <Field
          label="Kezdés"
          type="time"
          required
          value={value.start_time}
          onChange={(e) => onChange({ ...value, start_time: e.target.value })}
        />
        <Field
          label="Befejezés"
          type="time"
          required
          value={value.end_time}
          onChange={(e) => onChange({ ...value, end_time: e.target.value })}
        />
        <Field
          label="Legfeljebb ennyi perc fordítható edzésre"
          type="number"
          min={1}
          max={1440}
          required
          value={value.max_minutes}
          onChange={(e) =>
            onChange({ ...value, max_minutes: Number(e.target.value) })
          }
        />
        <Select
          label="Megengedett terhelés · specializáció hiányában általános"
          value={value.effort_cap}
          onChange={(e) =>
            onChange({
              ...value,
              effort_cap: e.target.value as SlotDetails["effort_cap"],
            })
          }
        >
          <option value="any">Általános lehetőség</option>
          <option value="easy">Csak könnyű</option>
          <option value="moderate">Legfeljebb mérsékelt</option>
        </Select>
      </div>
      <fieldset className="pt-options-checks">
        <legend>Választható helyszínek · ezek egymás alternatívái</legend>
        {locations
          .filter((l) => !l.archived || value.location_ids.includes(l.id))
          .map((location) => (
            <label key={location.id}>
              <input
                type="checkbox"
                checked={value.location_ids.includes(location.id)}
                onChange={(e) =>
                  onChange({
                    ...value,
                    location_ids: e.target.checked
                      ? [...value.location_ids, location.id]
                      : value.location_ids.filter((id) => id !== location.id),
                  })
                }
              />
              <span>
                {location.name}
                {location.archived ? " · törölt, jelenleg nem használható" : ""}
                <small>
                  {location.sports.map((s) => sportLabels[s]).join(" / ")}
                </small>
              </span>
            </label>
          ))}
      </fieldset>
      <label className="pt-options-check">
        <input
          type="checkbox"
          checked={value.combine_allowed}
          onChange={(e) =>
            onChange({ ...value, combine_allowed: e.target.checked })
          }
        />
        Az adott helyszínen megengedett mozgásformák egy alkalmon belül
        kombinálhatók
      </label>
      <label className="pt-options-check">
        <input
          type="checkbox"
          checked={value.ends_next_day}
          onChange={(e) =>
            onChange({ ...value, ends_next_day: e.target.checked })
          }
        />
        A befejezés másnapra esik
      </label>
      <details>
        <summary>Óraátállítás · ismétlődő helyi óra esetén</summary>
        <div className="pt-options-columns">
          {(["start_fold", "end_fold"] as const).map((key, i) => (
            <Select
              key={key}
              label={i ? "Befejezés előfordulása" : "Kezdés előfordulása"}
              value={value[key] ?? ""}
              onChange={(e) =>
                onChange({
                  ...value,
                  [key]: e.target.value === "" ? null : Number(e.target.value),
                })
              }
            >
              <option value="">Nincs külön megadva</option>
              <option value="0">Első előfordulás</option>
              <option value="1">Második előfordulás</option>
            </Select>
          ))}
        </div>
      </details>
    </fieldset>
  );
}
