"use client";
import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import {
  Field,
  Select,
  secondaryClass,
} from "@/components/planning-goals/fields";
import {
  matchingExercises,
  selectedEquipment,
  toggleEquipment,
} from "@/lib/training-options/strength-catalog";
import type { StrengthCatalog } from "@/lib/training-options/strength-catalog";
import EquipmentIllustration from "./equipment-illustration";

type Guide = StrengthCatalog["guides"][number];
export default function StrengthEquipment({
  catalog,
  resources,
  onChange,
}: {
  catalog: StrengthCatalog;
  resources: string[];
  onChange: (resources: string[]) => void;
}) {
  const chosen = selectedEquipment(catalog, resources),
    selected = new Set(chosen.map((e) => e.id));
  const [category, setCategory] = useState("all"),
    [query, setQuery] = useState(""),
    [selectedOnly, setSelectedOnly] = useState(false);
  const [exerciseQuery, setExerciseQuery] = useState(""),
    [movement, setMovement] = useState("all"),
    [compatibleOnly, setCompatibleOnly] = useState(true),
    [guide, setGuide] = useState<Guide | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const guideOpener = useRef<HTMLElement | null>(null);
  function openGuide(value: Guide | null, opener: HTMLElement) {
    guideOpener.current = opener;
    setGuide(value);
  }
  useEffect(() => {
    if (!guide || !dialog.current) return;
    const element = dialog.current;
    const previousFocus = guideOpener.current;
    element.showModal();
    return () => {
      element.close();
      previousFocus?.focus();
    };
  }, [guide]);
  const search = query.trim().toLocaleLowerCase("hu"),
    exSearch = exerciseQuery.trim().toLocaleLowerCase("hu");
  const visible = catalog.equipment.filter(
    (e) =>
      (!selectedOnly || selected.has(e.id)) &&
      (category === "all" || e.category === category) &&
      `${e.label} ${e.aliases.join(" ")} ${e.hint}`
        .toLocaleLowerCase("hu")
        .includes(search),
  );
  const matches = matchingExercises(catalog, resources),
    matchIds = new Set(matches.map((e) => e.id));
  const exercises = catalog.exercises.filter(
    (e) =>
      (!compatibleOnly || matchIds.has(e.id)) &&
      (movement === "all" || e.movement === movement) &&
      `${e.label} ${e.english}`.toLocaleLowerCase("hu").includes(exSearch),
  );
  const resourceNames = new Map(catalog.equipment.map((e) => [e.id, e.label]));
  function showCategory(value: string) {
    setCategory(value);
    setQuery("");
    setSelectedOnly(false);
  }
  return (
    <section
      className="pt-strength-inventory"
      aria-label="Erősítéshez elérhető felszerelés"
    >
      <header className="pt-section-heading">
        <div>
          <h4>Erősítéshez elérhető felszerelés</h4>
          <p className="pt-options-meta">
            Jelöld be, ami ezen a helyszínen ténylegesen hozzáférhető. Több
            eszköz is választható.
          </p>
        </div>
        <span className="pt-plan-badge" role="status">
          {chosen.length} kijelölt eszköztípus
        </span>
      </header>
      <div className="pt-options-columns">
        <Field
          label="Eszköz keresése"
          type="search"
          value={query}
          placeholder="Például mellhezhúzó pad, evezőgép, csiga…"
          onChange={(e) => {
            if (!query && e.target.value) setCategory("all");
            setQuery(e.target.value);
          }}
        />
        <Select
          label="Eszközcsoport"
          value={category}
          onChange={(e) => showCategory(e.target.value)}
        >
          <option value="all">
            Összes eszköz · {catalog.equipment.length}
          </option>
          {catalog.categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </Select>
      </div>
      <div
        className="pt-equipment-groups"
        role="group"
        aria-label="Eszközcsoportok"
      >
        {[{ id: "all", label: "Minden eszköz" }, ...catalog.categories].map(
          (group) => (
            <button
              type="button"
              key={group.id}
              className={secondaryClass}
              aria-pressed={category === group.id}
              onClick={() => showCategory(group.id)}
            >
              {group.label} ·{" "}
              {group.id === "all"
                ? catalog.equipment.length
                : catalog.equipment.filter((item) => item.category === group.id)
                    .length}
            </button>
          ),
        )}
      </div>
      <label className="pt-options-check">
        <input
          type="checkbox"
          checked={selectedOnly}
          onChange={(e) => {
            setSelectedOnly(e.target.checked);
            if (e.target.checked) setCategory("all");
          }}
        />
        Csak a kijelölt eszközök
      </label>
      <div className="pt-equipment-filter-status">
        <p className="pt-options-meta" role="status">
          Megjelenítve: {visible.length} / {catalog.equipment.length}{" "}
          eszköztípus.
        </p>
        {(query || selectedOnly || category !== "all") && (
          <button
            type="button"
            className={secondaryClass}
            onClick={() => showCategory("all")}
          >
            Szűrők törlése
          </button>
        )}
      </div>
      <div className="pt-equipment-grid">
        {visible.map((item) => (
          <label
            className="pt-equipment-card"
            data-selected={selected.has(item.id)}
            key={item.id}
          >
            <input
              type="checkbox"
              checked={selected.has(item.id)}
              onChange={(e) =>
                onChange(
                  toggleEquipment(
                    catalog,
                    resources,
                    item.id,
                    e.target.checked,
                  ),
                )
              }
            />
            <EquipmentIllustration kind={item.illustration} />
            <strong>{item.label}</strong>
            <small>{item.hint}</small>
          </label>
        ))}
      </div>
      {!visible.length && (
        <p role="status">
          Nincs ilyen eszköz a szűrésben. Egyedi felszerelést az alábbi mezőben
          is megadhatsz.
        </p>
      )}
      {!!chosen.length && (
        <p className="pt-options-meta">
          Kijelölve: {chosen.map((e) => e.label).join(", ")}.
        </p>
      )}
      <details className="pt-strength-exercises">
        <summary>
          Kapcsolódó gyakorlatok · {matches.length} eszközegyezés /{" "}
          {catalog.exercises.length} gyakorlat
        </summary>
        <p className="pt-options-meta">
          A lista a helyszíni eszközöket egyezteti. Az eszköz elérhetősége és a
          gyakorlat ismerete külön adat.
        </p>
        <div className="pt-options-columns">
          <Field
            label="Gyakorlat keresése"
            type="search"
            value={exerciseQuery}
            placeholder="Magyar vagy angol név"
            onChange={(e) => setExerciseQuery(e.target.value)}
          />
          <Select
            label="Gyakorlatcsoport"
            value={movement}
            onChange={(e) => setMovement(e.target.value)}
          >
            <option value="all">Minden gyakorlatcsoport</option>
            {catalog.movements.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </Select>
        </div>
        <label className="pt-options-check">
          <input
            type="checkbox"
            checked={compatibleOnly}
            onChange={(e) => setCompatibleOnly(e.target.checked)}
          />
          Csak a kijelölt felszereléshez kapcsolódók
        </label>
        <div className="pt-strength-exercise-grid">
          {exercises.map((exercise) => (
            <article key={exercise.id} className="pt-strength-exercise-card">
              <header>
                <h5>{exercise.label}</h5>
                <span className="pt-plan-badge">
                  {matchIds.has(exercise.id)
                    ? "Eszközei megvannak"
                    : "További eszköz szükséges"}
                </span>
              </header>
              {exercise.english && (
                <p className="pt-options-meta">{exercise.english}</p>
              )}
              <p>
                Eszközök:{" "}
                {exercise.requirements
                  .map((group) =>
                    group.map((id) => resourceNames.get(id)).join(" + "),
                  )
                  .join(" vagy ")}
                .
              </p>
              {exercise.guide_id && (
                <button
                  className={secondaryClass}
                  type="button"
                  onClick={(event) =>
                    openGuide(
                      catalog.guides.find((g) => g.id === exercise.guide_id) ??
                        null,
                      event.currentTarget,
                    )
                  }
                >
                  Kapcsolódó szemléltető lap
                </button>
              )}
            </article>
          ))}
        </div>
        {!exercises.length && (
          <p role="status">
            Jelöld be a rendelkezésre álló felszerelést, vagy kapcsold ki az
            eszközszűrést a teljes gyakorlatkatalógushoz.
          </p>
        )}
      </details>
      <details className="pt-strength-guides">
        <summary>Képes segítség · a feltöltött szemléltető lapok</summary>
        <div className="pt-options-actions">
          {catalog.guides.map((item) => (
            <button
              type="button"
              key={item.id}
              className={secondaryClass}
              onClick={(event) => openGuide(item, event.currentTarget)}
            >
              {item.page}. {item.title}
            </button>
          ))}
        </div>
        <p className="pt-options-meta">
          A lapok szemléltető anyagok. A rajtuk jelölt izommunka-értékek nem
          mért személyes adatok.
        </p>
      </details>
      {guide && (
        <dialog
          ref={dialog}
          className="pt-strength-guide-dialog"
          aria-labelledby="pt-strength-guide-title"
          onCancel={() => setGuide(null)}
          onClick={(e) => {
            if (e.target === e.currentTarget) setGuide(null);
          }}
        >
          <header>
            <h4 id="pt-strength-guide-title">
              {guide.page}. {guide.title}
            </h4>
            <button
              autoFocus
              className={secondaryClass}
              type="button"
              onClick={() => setGuide(null)}
            >
              Bezárás
            </button>
          </header>
          <Image
            src={guide.src}
            alt={guide.title + " – feltöltött szemléltető infografika"}
            width={guide.width}
            height={guide.height}
            unoptimized
          />
          <p className="pt-options-meta">
            Szemléltető referencia, nem személyre szabott edzéselőírás.
          </p>
        </dialog>
      )}
    </section>
  );
}
