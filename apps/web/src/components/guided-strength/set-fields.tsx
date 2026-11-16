"use client";
import { Field } from "@/components/planning-goals/fields";
import {
  Choice,
  DecimalField,
  IntegerField,
  unknown,
} from "@/components/initial-assessment/fields";
import type { Observation } from "@/lib/guided-strength/contracts";
const basis = {
  unknown: ["unknown"],
  bodyweight: ["not_applicable"],
  band: ["not_applicable"],
  external_kg: ["unknown", "total", "per_hand", "machine_display"],
  assistance_kg: ["assistance"],
  machine_level: ["machine_display"],
} as const;
export default function SetFields({
  value,
  onChange,
  today,
}: {
  value: Observation;
  onChange: (v: Observation) => void;
  today: string;
}) {
  const patch = (v: Partial<Observation>) => onChange({ ...value, ...v });
  return (
    <div className="pt-guided-set">
      <Field
        label="Valós teljesítés napja"
        type="date"
        value={value.performed_on}
        max={today}
        onChange={(e) => patch({ performed_on: e.target.value })}
      />
      <Choice
        label="Rögzítés módja"
        value={value.hold_seconds !== null ? "hold" : "reps"}
        options={{ reps: "Ismétlések", hold: "Ismert statikus tartás" }}
        onChange={(v) =>
          patch({ repetitions: null, hold_seconds: v === "hold" ? "" : null })
        }
      />
      {value.hold_seconds !== null ? (
        <DecimalField
          label="Tényleges tartás · másodperc"
          value={value.hold_seconds}
          onChange={(v) => patch({ hold_seconds: v ?? "" })}
        />
      ) : (
        <IntegerField
          label="Tényleges szabályos ismétlések"
          value={value.repetitions}
          max={10000}
          onChange={(v) => patch({ repetitions: v })}
        />
      )}
      <Choice
        label="Használt terhelés"
        value={value.load_kind}
        options={{
          unknown,
          bodyweight: "Saját testsúly",
          external_kg: "Külső súly · kg",
          assistance_kg: "Rásegítés · kg",
          machine_level: "Gépfokozat",
          band: "Gumiszalag",
        }}
        onChange={(v) =>
          patch({
            load_kind: v as Observation["load_kind"],
            load_value: null,
            load_basis: basis[v as keyof typeof basis][0],
            load_note: "",
          })
        }
      />
      {["external_kg", "assistance_kg", "machine_level"].includes(
        value.load_kind,
      ) && (
        <>
          <DecimalField
            label={
              value.load_kind === "machine_level"
                ? "Gépen beállított fokozat"
                : "Ténylegesen használt kg"
            }
            value={value.load_value}
            onChange={(v) => patch({ load_value: v })}
          />
          <Choice
            label="A terhelés jelentése"
            value={value.load_basis}
            options={Object.fromEntries(
              basis[value.load_kind].map((v) => [
                v,
                {
                  unknown,
                  total: "Összesen",
                  per_hand: "Kézenként",
                  machine_display: "Gép kijelzése",
                  assistance: "Rásegítés",
                  not_applicable: "Nem értelmezett",
                }[v],
              ]),
            )}
            onChange={(v) =>
              patch({ load_basis: v as Observation["load_basis"] })
            }
          />
        </>
      )}
      <Field
        label={
          value.load_kind === "band"
            ? "Szalag azonosítója / erőssége"
            : "Terhelés megjegyzése · ha szükséges"
        }
        maxLength={200}
        value={value.load_note}
        onChange={(e) => patch({ load_note: e.target.value })}
      />
      <Choice
        label="Szabályos ismétléstartalék a végén"
        value={value.rir}
        options={{
          unknown: "Nem tudom megbecsülni",
          "0": "0 · elfogyott",
          "1": "1",
          "2": "2",
          "3": "3",
          "4": "4",
          "5_plus": "Legalább 5",
        }}
        onChange={(v) => patch({ rir: v as Observation["rir"] })}
      />
      <Choice
        label="Kivitelezés"
        value={value.technique}
        options={{
          unknown,
          stable: "Végig stabil",
          uncertain: "Bizonytalan",
          breakdown: "Romlott / szétesett",
        }}
        onChange={(v) => patch({ technique: v as Observation["technique"] })}
      />
      <Choice
        label="Panasz a sorozat közben"
        value={value.symptoms}
        options={{
          unknown,
          none: "Panaszmentes",
          discomfort: "Kellemetlenség",
          pain: "Fájdalom",
        }}
        onChange={(v) => patch({ symptoms: v as Observation["symptoms"] })}
      />
    </div>
  );
}
