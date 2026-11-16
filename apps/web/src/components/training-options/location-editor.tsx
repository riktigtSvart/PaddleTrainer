"use client";
import { SaveActionButton } from "@/components/planning-data/save-actions";
import { useState } from "react";
import {
  Area,
  Field,
  Select,
  buttonClass,
  secondaryClass,
} from "@/components/planning-goals/fields";
import { emptyLocation, sportLabels } from "@/lib/training-options/contracts";
import {
  availableExercises,
  managedResource,
  selectedEquipment,
} from "@/lib/training-options/strength-catalog";
import type { StrengthCatalog } from "@/lib/training-options/strength-catalog";
import StrengthEquipment from "./strength-equipment";
import ExerciseConfirmations from "./exercise-confirmations";
import { RuleFields } from "./daylight-settings";
import LocationGeography from "./location-geography";
import { decimalCoordinate, readCoordinates, readGeographicArea } from "@/lib/training-options/daylight-rules";
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
  catalog,
  disabled,
  save,
  owner,
  today,
}: {
  data: OptionsData;
  catalog?: StrengthCatalog;
  disabled: boolean;
  save: (data: OptionsData) => Promise<boolean>;
  owner: string;
  today: string;
}) {
  const [draft, setDraft] = useState<Location | null>(null),
    [extra, setExtra] = useState(""),
    [error, setError] = useState("");
  const [editingCatalog, setEditingCatalog] = useState(catalog);
  function open(value: Location) {
    setDraft(structuredClone(value));
    setEditingCatalog(catalog);
    setExtra("");
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
          ...draft.resources,
          ...(extra.trim() ? [extra.trim()] : []),
        ]),
      ],
    };
    if (value.coordinates) {
      const point = { ...value.coordinates, latitude: decimalCoordinate(value.coordinates.latitude), longitude: decimalCoordinate(value.coordinates.longitude), timezone_name: value.coordinates.timezone_name.trim() };
      if (!point.latitude && !point.longitude) delete value.coordinates;
      else {
        try { value.coordinates = readCoordinates(point); }
        catch { setError("Adj meg érvényes szélességet, hosszúságot és IANA időzónát; mindkét koordináta szükséges. Példa: 47.5, 19.04, Europe/Budapest."); return; }
      }
    }
    if (value.area) {
      try {
        value.area = readGeographicArea({ ...value.area, ...Object.fromEntries(["south","north","west","east"].map(k=>[k,decimalCoordinate(value.area![k as "south"|"north"|"west"|"east"])])), timezone_name:value.area.timezone_name.trim() });
        if(value.kind!=="mobile"||value.coordinates)throw Error();
      } catch { setError("A körzethez négy rendezett földrajzi határ és érvényes időzóna kell. Körzet csak változó helyszínhez adható meg, konkrét pont helyett."); return; }
    }
    if(value.pool_length_m!==undefined){value.pool_length_m=decimalCoordinate(value.pool_length_m);if(!value.pool_length_m)delete value.pool_length_m;else if(!/^(?:[1-9][0-9]?|100)(?:\.[0-9]{1,6})?$/.test(value.pool_length_m)||Number(value.pool_length_m)<10||Number(value.pool_length_m)>100){setError("A medence pontos hossza 10 és 100 méter közötti érték legyen.");return;}}
    if(!value.sports.includes("SWIMMING"))delete value.pool_length_m;
    if (!value.name || !value.sports.length) {
      setError("A név és legalább egy mozgásforma szükséges.");
      return;
    }
    if (value.resources.length > 128) {
      setError("Egy helyszínen legfeljebb 128 felszereléstípus adható meg.");
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
  const editor = draft && (
        <form
          className="pt-options-form"
          id={`pt-location-editor-${draft.id}`}
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
                    ...(e.target.value === "fixed" ? {area: undefined} : {}),
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
                        ...(e.target.checked ? {} : { daylight_overrides: draft.daylight_overrides?.filter(r => r.sport !== key) }),
                      })
                    }
                  />
                  {label}
                </label>
              ))}
            </fieldset>
            <LocationGeography key={`${draft.id}:${draft.kind}`} value={draft} defaultZone={data.timezone_name} owner={owner} today={today} disabled={disabled}
              change={setDraft}
              rules={draft.sports.map(s => draft.daylight_overrides?.find(r => r.sport === s) ?? data.daylight_rules?.find(r => r.sport === s)).filter((r): r is NonNullable<typeof r> => !!r)} />
            {draft.sports.includes("SWIMMING")&&<Field label="Medence pontos hossza (m) · például 25, 33 vagy 50" inputMode="decimal" placeholder="25" value={draft.pool_length_m??""} onChange={e=>setDraft({...draft,pool_length_m:e.target.value})} hint="A 33 méteres és a 33⅓ méteres medence eltér. A pontos hossz a távos mintához szükséges; az időalapú kezdő úszáshoz elég a medence megadása."/>}
            <details>
              <summary>Napfénykorlát ezen a helyszínen · sportági alapbeállítás felülbírálása</summary>
              <p>Beltéri mozgásformához választhatod a „Nincs napfénykorlát” beállítást. A többi sport megtartja a saját szabályát.</p>
              <RuleFields sports={draft.sports} rules={draft.daylight_overrides ?? []} defaults={data.daylight_rules ?? []} disabled={disabled} onChange={daylight_overrides => setDraft({ ...draft, daylight_overrides })} />
            </details>
            <fieldset className="pt-options-checks">
              <legend>Ténylegesen hozzáférhető felszerelés</legend>
              {resources
                .filter(
                  (resource) =>
                    !draft.sports.includes("STRENGTH") ||
                    !editingCatalog ||
                    !managedResource(editingCatalog, resource),
                )
                .map((resource) => (
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
            {draft.sports.includes("STRENGTH") && editingCatalog && (
              <>
                <ExerciseConfirmations
                  key={draft.id + "-declarations"}
                  catalog={editingCatalog}
                  resources={draft.resources}
                  value={draft.exercise_confirmations ?? []}
                  onChange={(values) =>
                    setDraft({ ...draft, exercise_confirmations: values })
                  }
                />
                <StrengthEquipment
                  key={draft.id}
                  catalog={editingCatalog}
                  resources={draft.resources}
                  onChange={(values) =>
                    setDraft({ ...draft, resources: values })
                  }
                />
              </>
            )}
            {draft.sports.includes("STRENGTH") && !editingCatalog && (
              <p className="pt-options-meta">
                A képes eszközkatalógus a helyszínadatok frissítésével tölthető
                be.
              </p>
            )}
            {!!draft.resources.filter(
              (r) =>
                !resources.includes(r) &&
                (!editingCatalog || !managedResource(editingCatalog, r)),
            ).length && (
              <div>
                <p className="pt-options-meta">Egyedi felszerelések</p>
                <div className="pt-options-actions">
                  {draft.resources
                    .filter(
                      (r) =>
                        !resources.includes(r) &&
                        (!editingCatalog ||
                          !managedResource(editingCatalog, r)),
                    )
                    .map((resource) => (
                      <button
                        key={resource}
                        type="button"
                        className={secondaryClass}
                        aria-label={`${resource} eltávolítása`}
                        onClick={() =>
                          setDraft({
                            ...draft,
                            resources: draft.resources.filter(
                              (r) => r !== resource,
                            ),
                          })
                        }
                      >
                        {resource} ×
                      </button>
                    ))}
                </div>
              </div>
            )}
            <Field
              label="Saját felszerelés hozzáadása"
              maxLength={200}
              value={extra}
              onChange={(e) => setExtra(e.target.value)}
            />
            <button
              type="button"
              className={secondaryClass}
              disabled={!extra.trim() || disabled}
              onClick={() => {
                setDraft({
                  ...draft,
                  resources: [...new Set([...draft.resources, extra.trim()])],
                });
                setExtra("");
              }}
            >
              Felszerelés hozzáadása
            </button>
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
            <SaveActionButton saveLabel="Helyszín mentése" type="submit" saveHint={disabled ? "A folyamatban lévő helyszínmentés befejezése után használható." : "Az éppen szerkesztett helyszín adatait menti."} className={buttonClass} disabled={disabled}>
              Helyszín mentése
            </SaveActionButton>
          </fieldset>
        </form>
  );
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
        {draft && !data.locations.some((l) => l.id === draft.id && !l.archived) && <article className="pt-panel" data-editing="true">{editor}</article>}
        {data.locations
          .filter((l) => !l.archived)
          .map((location) => (
            <article className="pt-panel" key={location.id} data-editing={draft?.id === location.id} aria-label={location.name}>
              <p className="pt-options-meta">
                {location.kind === "mobile"
                  ? "Változó helyszín"
                  : "Állandó helyszín"}
              </p>
              <h3>{location.name}</h3>
              <p className="pt-options-meta">{location.area ? `Körzet: ${location.area.south}°–${location.area.north}°, ${location.area.west}°–${location.area.east}° · ${location.area.timezone_name}` : location.coordinates ? `${location.coordinates.latitude}°, ${location.coordinates.longitude}° · ${location.coordinates.timezone_name}` : "Földrajzi hely még nincs megadva."}</p>
              {location.pool_length_m && <p className="pt-options-meta">Medencehossz: {location.pool_length_m} m.</p>}
              <div className="pt-option-tags">
                {location.sports.map((sport) => (
                  <span key={sport}>{sportLabels[sport]}</span>
                ))}
              </div>
              {catalog && location.sports.includes("STRENGTH") && (
                <p className="pt-options-meta">
                  {selectedEquipment(catalog, location.resources).length}{" "}
                  erősítő eszköztípus ·{" "}
                  {availableExercises(catalog, location).length} kapcsolódó
                  gyakorlat
                </p>
              )}
              {!!location.exercise_confirmations?.length && (
                <p className="pt-options-meta">
                  Saját helyszíni megadás:{" "}
                  {location.exercise_confirmations
                    .map(
                      (c) =>
                        catalog?.exercises.find((e) => e.id === c.exercise_id)
                          ?.label ?? c.exercise_id,
                    )
                    .join(", ")}
                  .
                </p>
              )}
              {location.resources.length > 6 ? (
                <details>
                  <summary>
                    Felszerelés · {location.resources.length} típus
                  </summary>
                  <p className="pt-options-meta">
                    {location.resources.join(", ")}
                  </p>
                </details>
              ) : (
                !!location.resources.length && (
                  <p className="pt-options-meta">
                    Felszerelés: {location.resources.join(", ")}
                  </p>
                )
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
                  aria-expanded={draft?.id === location.id}
                  aria-controls={`pt-location-editor-${location.id}`}
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
              {draft?.id === location.id && editor}
            </article>
          ))}
      </div>
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
