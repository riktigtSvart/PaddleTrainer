"use client";
import { capabilityLabels } from "@/lib/planning-goals/labels";
import {
  emptyProfile,
} from "@/lib/planning-cycles/contracts";
import { autoEventProfile, demandSources, demandSuggestion } from "@/lib/planning-cycles/event-demands";
import type { EventProfile } from "@/lib/planning-cycles/contracts";
import {
  Area,
  Field,
  Select,
  secondaryClass,
} from "@/components/planning-goals/fields";

export default function EventProfileEditor({
  value,
  change,
  index,
  sport = "",
}: {
  value?: EventProfile;
  change: (p: EventProfile) => void;
  index: number;
  sport?: string;
}) {
  const p = autoEventProfile(value ?? emptyProfile(sport), sport);
  const suggested = demandSuggestion(p, sport);
  function patch(patch: Partial<EventProfile>) {
    const structural = ["discipline", "event_type", "distance_status", "distance_value", "distance_unit"].some((key) => key in patch);
    const next = { ...p, ...patch };
    if (structural) { next.capability_basis = "unassessed"; next.capability_keys = []; delete next.capability_weights; }
    change(autoEventProfile(next, sport));
  }
  return (
    <div className="space-y-4 border-t border-zinc-700 pt-4">
      <p className="font-medium">Versenyszám és követelmények</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Versenyszám / szakág"
          name={`event.${index}.discipline`}
          value={p.discipline}
          required
          maxLength={200}
          placeholder="Pl. síkvízi kajak K1, terepfutás, országúti kerékpár"
          onChange={(e) => patch({ discipline: e.target.value })}
        />
        <Select
          label="Verseny jellege"
          name={`event.${index}.event_type`}
          value={p.event_type}
          onChange={(e) =>
            patch({ event_type: e.target.value as EventProfile["event_type"] })
          }
        >
          <option value="other">Egyéb / később pontosítandó</option>
          <option value="sprint">
            Sprint / rövid, nagy intenzitású verseny
          </option>
          <option value="endurance">Állóképességi / hosszú verseny</option>
          <option value="technical">Technikai / ügyességi verseny</option>
          <option value="strength">Erőverseny</option>
          <option value="mixed">Összetett / több versenyszám</option>
        </Select>
        <Select
          label="Versenytáv megadása"
          name={`event.${index}.distance_status`}
          value={p.distance_status}
          onChange={(e) => {
            const status = e.target.value as EventProfile["distance_status"];
            patch({
              distance_status: status,
              distance_value: status === "specified" ? "" : null,
              distance_unit: status === "specified" ? "m" : null,
            });
          }}
        >
          <option value="specified">Megadom a távot</option>
          <option value="unknown">Még nem ismert</option>
          <option value="not_applicable">Ennél a versenynél nincs táv</option>
        </Select>
        {p.distance_status === "specified" && (
          <div className="grid grid-cols-2 gap-3">
            <Field
              label="Versenytáv"
              name={`event.${index}.distance_value`}
              value={p.distance_value ?? ""}
              inputMode="decimal"
              required
              maxLength={13}
              onChange={(e) => patch({ distance_value: e.target.value })}
            />
            <Select
              label="Táv mértékegysége"
              name={`event.${index}.distance_unit`}
              value={p.distance_unit ?? "m"}
              onChange={(e) =>
                patch({ distance_unit: e.target.value as "m" | "km" })
              }
            >
              <option value="m">m</option>
              <option value="km">km</option>
            </Select>
          </div>
        )}
        <Field
          label="Várható versenyidő (perc, ha ismert)"
          name={`event.${index}.duration`}
          inputMode="decimal"
          value={p.expected_duration_minutes ?? ""}
          maxLength={13}
          onChange={(e) =>
            patch({ expected_duration_minutes: e.target.value || null })
          }
        />
      </div>
      <Area
        label="Pálya, körülmények, további követelmények (ha ismert)"
        name={`event.${index}.course`}
        maxLength={500}
        value={p.course_description}
        onChange={(e) => patch({ course_description: e.target.value })}
      />
      {p.capability_basis === "paddling_demands_v0_1" ? <div className="pt-event-demands-summary"><p><strong>A képességigény automatikusan kitöltve.</strong> Relatív igény: 1–5. A pontok a verseny követelményeit súlyozzák; az edzésarány a sportoló állapotától és a felkészülési szakasztól is függ.</p><p className="text-xs">Szakirodalomra támaszkodó, szerkeszthető alkalmazásjavaslat. {demandSources.map((source, n) => <a className="underline mr-3" key={source.key} href={source.url} target="_blank" rel="noreferrer">Forrás {n + 1}</a>)}</p></div> : <p className="text-xs text-zinc-400">{p.capability_basis === "coach_declared" ? "Kézzel megadott képességigények és relatív súlyok." : "Ehhez a versenyszámhoz még nincs automatikus képességprofil. Az igények kézzel megadhatók."}</p>}
      {suggested && p.capability_basis === "coach_declared" && <button type="button" className={secondaryClass} onClick={() => change(autoEventProfile({ ...p, capability_basis: "unassessed" }, sport))}>Forrásalapú súlyozás visszaállítása</button>}
      <details open={p.capability_basis === "paddling_demands_v0_1" ? true : undefined}>
        <summary className="cursor-pointer text-sm text-teal-200">
          Képességigények áttekintése és kézi módosítása
        </summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {Object.entries(capabilityLabels).map(([key, label]) => (
            <label key={key} className="flex gap-2 text-sm">
              <input
                type="checkbox"
                checked={p.capability_keys.includes(key)}
                disabled={p.capability_keys.length === 1 && p.capability_keys.includes(key)}
                onChange={(e) => {
                  const keys = e.target.checked
                    ? [...p.capability_keys, key]
                    : p.capability_keys.filter((k) => k !== key);
                  change({
                    ...p,
                    capability_keys: keys,
                    ...(p.capability_weights && keys.length ? { capability_weights: Object.fromEntries(keys.map((k) => [k, p.capability_weights?.[k] ?? 3])) } : {}),
                    capability_basis: keys.length
                      ? "coach_declared"
                      : "unassessed",
                  });
                }}
              />
              {label}
              {p.capability_keys.includes(key) && <select aria-label={`${label} relatív igénye`} value={p.capability_weights?.[key] ?? ""} onChange={(e) => {
                const weights = Object.fromEntries(p.capability_keys.map((k) => [k, p.capability_weights?.[k] ?? 3])); weights[key] = Number(e.target.value);
                change({ ...p, capability_basis: "coach_declared", capability_weights: weights });
              }}><option value="" disabled>Nincs súly megadva</option>{[1, 2, 3, 4, 5].map((weight) => <option key={weight} value={weight}>{weight} / 5</option>)}</select>}
            </label>
          ))}
        </div>
      </details>
    </div>
  );
}
