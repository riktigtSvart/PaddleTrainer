"use client";
import { useState } from "react";
import {
  Area,
  Field,
  Select,
  buttonClass,
  secondaryClass,
} from "@/components/planning-goals/fields";
import { emptyLocation, sportLabels } from "@/lib/training-options/contracts";
import type {
  Location,
  OptionsData,
  Sport,
} from "@/lib/training-options/contracts";

const resources = [
  "Kajak",
  "Kajakergométer",
  "Kézisúlyzó",
  "Futócipő",
  "Úszómedence",
  "Tornaszőnyeg",
];
export default function LocationEditor({
  data,
  disabled,
  save,
}: {
  data: OptionsData;
  disabled: boolean;
  save: (data: OptionsData) => Promise<boolean>;
}) {
  const [draft, setDraft] = useState<Location | null>(null),
    [extra, setExtra] = useState(""),
    [error, setError] = useState("");
  function open(value: Location) {
    setDraft(structuredClone(value));
    setExtra(value.resources.filter((r) => !resources.includes(r)).join(", "));
    setError("");
  }
  function preset(
    name: string,
    sports: Sport[],
    kind: Location["kind"] = "fixed",
  ) {
    open({
      ...emptyLocation(),
      name,
      sports,
      kind,
      combine_allowed: sports.length > 1,
    });
  }
  async function submit() {
    if (!draft) return;
    const value = {
      ...draft,
      name: draft.name.trim(),
      resources: [
        ...new Set([
          ...draft.resources.filter((r) => resources.includes(r)),
          ...extra
            .split(/[,;\n]/)
            .map((r) => r.trim())
            .filter(Boolean),
        ]),
      ],
    };
    if (!value.name || !value.sports.length) {
      setError("A név és legalább egy mozgásforma szükséges.");
      return;
    }
    if (
      data.locations.some(
        (location) =>
          location.id !== value.id &&
          !location.archived &&
          location.name.toLocaleLowerCase("hu") ===
            value.name.toLocaleLowerCase("hu"),
      )
    ) {
      setError("Ezzel a névvel már van aktív helyszín.");
      return;
    }
    const locations = data.locations.some((l) => l.id === value.id)
      ? data.locations.map((l) => (l.id === value.id ? value : l))
      : [...data.locations, value];
    if (await save({ ...data, locations })) setDraft(null);
  }
  return (
    <section className="pt-options-section">
      <div className="pt-section-heading">
        <div>
          <h2>Helyszínek</h2>
          <p>
            Az egyszer megadott lehetőségek minden ottani alkalomnál
            rendelkezésre állnak.
          </p>
        </div>
        <button
          type="button"
          className={buttonClass}
          disabled={disabled || !!draft}
          onClick={() => open(emptyLocation())}
        >
          + Helyszín hozzáadása
        </button>
      </div>
      {!data.locations.some((location) => !location.archived) && (
        <div className="pt-panel">
          <p>
            Még nincs mentett helyszín. Saját helyszínt szabadon felvehetsz,
            vagy ezekből a kitölthető alapokból indulhatsz:
          </p>
          <div className="pt-options-actions">
            <button
              className={secondaryClass}
              disabled={disabled || !!draft}
              onClick={() =>
                preset("Otthon", ["RUNNING", "GYMNASTICS", "STRETCHING"])
              }
            >
              Otthon
            </button>
            <button
              className={secondaryClass}
              disabled={disabled || !!draft}
              onClick={() =>
                preset("Változó futási helyszín", ["RUNNING"], "mobile")
              }
            >
              Változó futási helyszín
            </button>
            <button
              className={secondaryClass}
              disabled={disabled || !!draft}
              onClick={() =>
                preset("Változó evezési helyszín", ["KAYAK"], "mobile")
              }
            >
              Változó evezési helyszín
            </button>
          </div>
        </div>
      )}
      <div className="pt-location-grid">
        {data.locations
          .filter((l) => !l.archived)
          .map((location) => (
            <article className="pt-panel" key={location.id}>
              <p className="pt-options-meta">
                {location.kind === "mobile"
                  ? "Változó helyszín"
                  : "Állandó helyszín"}
              </p>
              <h3>{location.name}</h3>
              <div className="pt-option-tags">
                {location.sports.map((sport) => (
                  <span key={sport}>{sportLabels[sport]}</span>
                ))}
              </div>
              {!!location.resources.length && (
                <p className="pt-options-meta">
                  Felszerelés: {location.resources.join(", ")}
                </p>
              )}
              {location.notes && <p>{location.notes}</p>}
              {location.combine_allowed && (
                <p className="pt-options-meta">
                  A mozgásformák egy alkalmon belül kombinálhatók.
                </p>
              )}
              <div className="pt-options-actions">
                <button
                  type="button"
                  className={secondaryClass}
                  disabled={disabled || !!draft}
                  onClick={() => open(location)}
                >
                  Szerkesztés
                </button>
                <button
                  type="button"
                  className={`${secondaryClass} pt-options-delete`}
                  disabled={disabled || !!draft}
                  aria-label={`${location.name} törlése`}
                  onClick={() =>
                    void save({
                      ...data,
                      locations: data.locations.map((item) =>
                        item.id === location.id
                          ? { ...item, archived: true }
                          : item,
                      ),
                    })
                  }
                >
                  Törlés
                </button>
              </div>
            </article>
          ))}
      </div>
      {draft && (
        <form
          className="pt-panel pt-options-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="pt-section-heading">
            <h3>
              {data.locations.some((l) => l.id === draft.id)
                ? "Helyszín szerkesztése"
                : "Új helyszín"}
            </h3>
            <button
              type="button"
              className={secondaryClass}
              disabled={disabled}
              onClick={() => setDraft(null)}
            >
              Elvetés
            </button>
          </div>
          <fieldset disabled={disabled}>
            <div className="pt-options-columns">
              <Field
                label="Helyszín neve"
                required
                maxLength={100}
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
              <Select
                label="Helyszín típusa"
                value={draft.kind}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    kind: e.target.value as Location["kind"],
                  })
                }
              >
                <option value="fixed">Állandó helyszín</option>
                <option value="mobile">Változó / szabad helyszín</option>
              </Select>
            </div>
            <fieldset className="pt-options-checks">
              <legend>Itt elérhető mozgásformák · több is jelölhető</legend>
              {Object.entries(sportLabels).map(([key, label]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={draft.sports.includes(key as Sport)}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        sports: e.target.checked
                          ? [...draft.sports, key as Sport]
                          : draft.sports.filter((s) => s !== key),
                      })
                    }
                  />
                  {label}
                </label>
              ))}
            </fieldset>
            <fieldset className="pt-options-checks">
              <legend>Ténylegesen hozzáférhető felszerelés</legend>
              {resources.map((resource) => (
                <label key={resource}>
                  <input
                    type="checkbox"
                    checked={draft.resources.includes(resource)}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        resources: e.target.checked
                          ? [...draft.resources, resource]
                          : draft.resources.filter((r) => r !== resource),
                      })
                    }
                  />
                  {resource}
                </label>
              ))}
            </fieldset>
            <Field
              label="Egyéb felszerelés · vesszővel elválasztva"
              value={extra}
              onChange={(e) => setExtra(e.target.value)}
            />
            {draft.sports.length > 1 && (
              <label className="pt-options-check">
                <input
                  type="checkbox"
                  checked={draft.combine_allowed}
                  onChange={(e) =>
                    setDraft({ ...draft, combine_allowed: e.target.checked })
                  }
                />
                A mozgásformák egy alkalmon belül is kombinálhatók
              </label>
            )}
            {draft.kind === "mobile" && draft.sports.includes("KAYAK") && (
              <>
                <label className="pt-options-check">
                  <input
                    type="checkbox"
                    checked={draft.boat_transport}
                    onChange={(e) =>
                      setDraft({ ...draft, boat_transport: e.target.checked })
                    }
                  />
                  A hajó szállítása megoldható
                </label>
                {!draft.boat_transport && (
                  <p className="pt-options-meta">
                    A kajakos lehetőség a szállítás megadása után lesz
                    használható ezen a változó helyszínen.
                  </p>
                )}
              </>
            )}
            <Area
              label="Helyszíni feltételek és megjegyzések"
              maxLength={2000}
              value={draft.notes}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
            />
            {error && <p role="alert">{error}</p>}
            <p className="pt-options-meta">A szerkesztés még nincs mentve.</p>
            <button className={buttonClass} disabled={disabled}>
              Helyszín mentése
            </button>
          </fieldset>
        </form>
      )}
      {data.locations.some((l) => l.archived) && (
        <details>
          <summary>Törölt helyszínek · visszaállíthatók</summary>
          <p className="pt-options-meta">
            A törölt helyszín új edzéshez nem használható. A korábbi edzések és
            órarendek hivatkozásai megmaradnak.
          </p>
          {data.locations
            .filter((l) => l.archived)
            .map((l) => (
              <div className="pt-options-actions" key={l.id}>
                <span>{l.name}</span>
                <button
                  type="button"
                  className={secondaryClass}
                  disabled={disabled || !!draft}
                  onClick={() => open({ ...l, archived: false })}
                >
                  Visszaállítás
                </button>
              </div>
            ))}
        </details>
      )}
    </section>
  );
}
