"use client";
import { useState } from "react";
import {
  Field,
  Select,
  buttonClass,
  secondaryClass,
} from "@/components/planning-goals/fields";
import { matchingExercises } from "@/lib/training-options/strength-catalog";
import type { StrengthCatalog } from "@/lib/training-options/strength-catalog";
import type { ExerciseConfirmation } from "@/lib/training-options/contracts";
export default function ExerciseConfirmations({
  catalog,
  value,
  onChange,
  resources,
}: {
  catalog: StrengthCatalog;
  value: ExerciseConfirmation[];
  onChange: (v: ExerciseConfirmation[]) => void;
  resources: string[];
}) {
  const [query, setQuery] = useState(""),
    [selected, setSelected] = useState(""),
    [note, setNote] = useState(""),
    [confirmed, setConfirmed] = useState(false);
  const known = new Set(value.map((v) => v.exercise_id)),
    physical = new Set(matchingExercises(catalog, resources).map((e) => e.id));
  const choices = catalog.exercises.filter(
    (e) =>
      !known.has(e.id) &&
      `${e.label} ${e.english}`
        .toLocaleLowerCase("hu")
        .includes(query.trim().toLocaleLowerCase("hu")),
  );
  const selectedExercise = catalog.exercises.find((e) => e.id === selected);
  function add() {
    if (
      !selectedExercise ||
      known.has(selected) ||
      !confirmed ||
      value.length >= 128
    )
      return;
    onChange([
      ...value,
      { exercise_id: selected, source_kind: "self_report", note: note.trim() },
    ]);
    setSelected("");
    setConfirmed(false);
    setNote("");
  }
  return (
    <section
      className="pt-exercise-confirmations"
      aria-label="Gyakorlatok saját helyszíni megadása"
    >
      <h4>Gyakorlat megadása ezen a helyszínen</h4>
      <p>
        Ha itt egy gyakorlatot el tudsz végezni, közvetlenül is megadhatod. Nem
        kell hozzá az eszközkatalógusban minden tartozékot külön megtalálnod. A
        helyszíni lehetőséget ilyenkor a saját megadásod igazolja.
      </p>
      {value.length > 0 && (
        <ul>
          {value.map((v) => (
            <li key={v.exercise_id}>
              <strong>
                {catalog.exercises.find((e) => e.id === v.exercise_id)?.label ??
                  v.exercise_id}
              </strong>
              <span className="pt-plan-badge">Saját helyszíni megadás</span>
              {v.note && <p>{v.note}</p>}
              <button
                type="button"
                className={secondaryClass}
                aria-label={`${catalog.exercises.find((e) => e.id === v.exercise_id)?.label ?? v.exercise_id} helyszíni megadásának törlése`}
                onClick={() =>
                  onChange(value.filter((c) => c.exercise_id !== v.exercise_id))
                }
              >
                Megadás törlése
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="pt-options-columns">
        <Field
          label="Megadható gyakorlat keresése"
          type="search"
          placeholder="Például fekvenyomás"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Select
          label="Helyszínen elvégezhető gyakorlat"
          value={selected}
          onChange={(e) => {
            setSelected(e.target.value);
            setConfirmed(false);
          }}
        >
          <option value="">Válassz gyakorlatot</option>
          {choices.map((e) => (
            <option key={e.id} value={e.id}>
              {e.label}
            </option>
          ))}
        </Select>
      </div>
      {selectedExercise && (
        <p className="pt-options-meta">
          {physical.has(selected)
            ? "Az eszközlista alapján is elérhető. A külön saját megadást ettől még megőrizheted."
            : "Az eszközlista alapján az elérhetőség még nem állapítható meg. A mentés a saját helyszíni megadásodat fogja használni."}
        </p>
      )}
      <Field
        label="Megjegyzés a helyszíni megoldáshoz · választható"
        placeholder="Például saját rúdtartós fekvenyomó pad, rúd és súlytárcsák"
        maxLength={500}
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <label className="pt-options-check">
        <input
          type="checkbox"
          checked={confirmed}
          disabled={!selected}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        Megerősítem, hogy ehhez a gyakorlathoz ezen a helyszínen rendelkezésemre
        áll a megfelelő felszerelés és hely.
      </label>
      <button
        type="button"
        className={buttonClass}
        disabled={!selected || !confirmed || known.has(selected)}
        onClick={add}
      >
        Gyakorlat helyszíni hozzáadása
      </button>
      <p className="pt-options-meta">
        A hozzáadást a helyszín mentése véglegesíti. A jártasságot és a
        panaszmentes végrehajtást a kezdeti felmérésben adod meg; a gyakorlat
        elérhetősége ezeket nem írja át.
      </p>
    </section>
  );
}
