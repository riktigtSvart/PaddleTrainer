"use client";
import Link from "next/link";
import type { ReactNode } from "react";
import { gateLabels } from "@/lib/athlete-setup/contracts";
import type { Profile } from "@/lib/athlete-setup/contracts";
import {
  Area,
  Field,
  Select,
  secondaryClass,
} from "@/components/planning-goals/fields";
import { availableExercises } from "@/lib/training-options/strength-catalog";
import {
  loadBases,
  newExercise,
  newSet,
  summarize,
} from "@/lib/initial-assessment/contracts";
import type {
  Context,
  Data,
  Exercise,
  SetRecord,
  Sport,
  SportReference,
} from "@/lib/initial-assessment/contracts";
import { Choice, DecimalField, IntegerField, unknown } from "./fields";
import { assessmentRecommendations } from "@/lib/guided-strength/recommendations";

export const titles = [
  "Állapot és keretek",
  "Erőedzés-előzmények",
  "Sportágak, cél és helyszín",
  "Gyakorlatok és jártasság",
  "Ismert teljesítések",
  "Összegzés és mentés",
];
export const stateLabels: Record<string, string> = {
  review: "Állapot vagy profil egyeztetése szükséges",
  avoid: "Jelenleg kerülendő / egyeztetendő",
  needs_instruction: "Technikai betanulás szükséges",
  unassessed: "Még felmérendő",
  needs_reference: "Ismert gyakorlat, referencia pontosítandó",
  recorded_reference: "Rögzített kiinduló referencia",
};
const reasons: Record<string, string> = {
  EXERCISE_MISSING: "Gyakorlat még nincs kiválasztva.",
  INSTRUCTION_OR_FAMILIARITY_NEEDED: "A jártasságot még tisztázni kell.",
  COMFORT_UNRESOLVED: "A mozgás közbeni komfort még nem tisztázott.",
  LOCATION_REVIEW:
    "A felmérés helyszíne vagy annak erősítési lehetősége pontosítandó.",
  EQUIPMENT_MISSING: "A helyszíni felszerelésből nem áll össze ez a gyakorlat.",
  RECENT_REFERENCE_MISSING:
    "Nincs az elmúlt 56 napból dátummal ellátott saját referencia.",
  SET_REFERENCE_INCOMPLETE:
    "A sorozat teljesítése, terhelése, tartaléka vagy kivitelezése még hiányos.",
};
const blankSport = (key: string): Sport => ({
  sport_key: key,
  role: "unknown",
  discipline: "",
  goal: "",
  notes: "",
});
const familiarity = {
  unknown,
  unfamiliar: "Nem ismerem",
  assisted: "Segítséggel végeztem",
  independent: "Önállóan végzem",
  regular: "Rendszeresen végzem",
};
const comfort = {
  unknown,
  none: "Panaszmentesen végzem",
  uncertain: "Bizonytalan a kivitelezés",
  symptoms: "Panaszt okoz",
  avoid: "Jelenleg kerülöm",
  no_experience: "Nincs még tapasztalatom",
};
function Place({
  context,
  value,
  onChange,
}: {
  context: Context;
  value: string | null;
  onChange: (value: string | null) => void;
}) {
  return (
    <Select
      label="Helyszín"
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value || null)}
    >
      <option value="">Még nincs megadva</option>
      {context.sources.locations.map((l) => (
        <option key={l.id} value={l.id}>
          {l.name}
          {l.archived ? " · törölt helyszín" : ""}
        </option>
      ))}
    </Select>
  );
}

export default function AssessmentEditor({
  context,
  data,
  open,
  onOpen,
  onChange,
  disabled,
  notice,
}: {
  context: Context;
  data: Data;
  open: number;
  onOpen: (i: number) => void;
  onChange: (value: Data) => void;
  disabled: boolean;
  notice?: ReactNode;
}) {
  const summary = summarize(data, context.sources, context.local_today),
    registry = context.sources.registry,
    catalog = context.sources.catalog;
  const patch = (p: Partial<Data>) =>
    onChange({ ...data, ...p, reviewed: p.reviewed ?? false });
  const editSport = (key: string, p: Partial<Sport>) =>
    patch({
      sports: data.sports.map((s) =>
        s.sport_key === key ? { ...s, ...p } : s,
      ),
    });
  const editExercise = (id: string, p: Partial<Exercise>) =>
    patch({
      exercises: data.exercises.map((e) => (e.id === id ? { ...e, ...p } : e)),
    });
  const editSet = (exercise: Exercise, id: string, p: Partial<SetRecord>) =>
    editExercise(exercise.id, {
      sets: exercise.sets.map((s) => (s.id === id ? { ...s, ...p } : s)),
    });
  const editReference = (id: string, p: Partial<SportReference>) =>
    patch({
      sport_references: data.sport_references.map((r) =>
        r.id === id ? { ...r, ...p } : r,
      ),
      references_reviewed: false,
    });
  const currentProfile = context.sources.profile_receipt?.artifact.proposal
    .data as Profile | undefined;
  const panels: ReactNode[] = [
    <div key="state" className="pt-assessment-fields">
      <p>
        A mentett személyes adatokat átvesszük. Itt a változást és az
        erőfelmérés szempontjából fontos megjegyzést rögzíted.
      </p>
      <div className="pt-options-message">
        <strong>Mentett sportolói keret</strong>
        <p>
          {context.sources.profile_review
            ? (gateLabels[context.sources.profile_review.global_entry_gate] ??
              "A mentett profil áttekintést igényel.")
            : "Még nincs mentett személyes profil."}
        </p>
        {currentProfile && (
          <p>
            Fő sportág:{" "}
            {"target_sport" in currentProfile
              ? String(currentProfile.target_sport)
              : "—"}
            .
          </p>
        )}
        {currentProfile?.constraints.map((c) => (
          <p key={c.key}>
            <strong>{c.affected_area || "Mentett mozgáskorlát"}:</strong>{" "}
            {[
              ...c.restricted_activities,
              c.adaptations,
              c.professional_guidance,
            ]
              .filter(Boolean)
              .join(" · ") || "A gyakorlati alkalmazkodás még pontosítandó."}
          </p>
        ))}
        <Link href="/athlete-setup#profile" className="underline">
          Személyes adatok és mozgáskorlátok áttekintése
        </Link>
      </div>
      <Field
        label="Felmérés dátuma"
        type="date"
        max={context.local_today}
        value={data.assessment_date}
        onChange={(e) => {
          if (e.target.value) patch({ assessment_date: e.target.value });
        }}
      />
      <Choice
        label="Változott az állapotod a mentett profil óta?"
        value={data.state_change}
        options={{
          unknown,
          unchanged: "Nincs ismert változás",
          changed: "Változás vagy új panasz van",
          review_needed: "Előbb szakemberrel szeretném tisztázni",
        }}
        onChange={(v) => patch({ state_change: v as Data["state_change"] })}
      />
      <Area
        label="Kerülendő mozgás, új panasz vagy szakember által megadott korlátozás"
        maxLength={2000}
        value={data.state_notes}
        onChange={(e) => patch({ state_notes: e.target.value })}
      />
      {["changed", "review_needed"].includes(data.state_change) && (
        <p>
          Az új állapotot a személyes adatoknál is vezesd át, hogy a tervező a
          friss kereteket kapja. Ez a felmérés külön mentési változatot készít.
        </p>
      )}
      {summary.state_review_required && (
        <p role="status">
          Az állapotot vagy a mentett profil kereteit még egyeztetni kell. Az
          adatmegadás és részleges mentés folytatható; ez nem egészségügyi
          alkalmassági igazolás.
        </p>
      )}
    </div>,
    <div key="history" className="pt-assessment-fields">
      <p>
        A válaszok önbevallott előzmények. A hiányzó adatot hagyd ismeretlenül.
      </p>
      <Choice
        label="Milyen erőedzés-előzménnyel rendelkezel?"
        value={data.experience}
        options={{
          unknown,
          none: "Még nincs tapasztalatom",
          occasional: "Alkalmanként erősítettem",
          returning: "Hosszabb kihagyás után térek vissza",
          regular: "Rendszeresen erősítek",
        }}
        onChange={(v) => patch({ experience: v as Data["experience"] })}
      />
      <Choice
        label="Milyen gyakran erősítettél az elmúlt három hónapban?"
        value={data.strength_frequency}
        options={{
          unknown,
          none: "Nem végeztem erőedzést",
          less_than_weekly: "Ritkábban, mint hetente",
          weekly_1: "Heti 1 alkalom",
          weekly_2: "Heti 2 alkalom",
          weekly_3_plus: "Heti 3 vagy több alkalom",
        }}
        onChange={(v) =>
          patch({ strength_frequency: v as Data["strength_frequency"] })
        }
      />
      <div className="pt-options-columns">
        <Field
          label="Utolsó erőedzés dátuma · ha ismert"
          type="date"
          max={data.assessment_date}
          value={data.last_strength_date ?? ""}
          onChange={(e) =>
            patch({ last_strength_date: e.target.value || null })
          }
        />
        <IntegerField
          label="Szokásos időtartam (perc) · ha ismert"
          value={data.usual_strength_minutes}
          max={1440}
          onChange={(v) => patch({ usual_strength_minutes: v })}
        />
      </div>
      <Choice
        label="Hogyan végezted / végeznéd az erősítést?"
        value={data.supervision}
        options={{
          unknown,
          self: "Önállóan",
          supervised: "Edzővel / segítséggel",
          mixed: "Vegyesen",
          needed: "Betanuláshoz segítségre van szükségem",
        }}
        onChange={(v) => patch({ supervision: v as Data["supervision"] })}
      />
    </div>,
    <div key="sports" className="pt-assessment-fields">
      <p>
        A sportágak szerepe az itt kiválasztott felkészüléshez tartozik. A közös
        adatok egyszer szerepelnek.
      </p>
      <p>
        Ha erőedzést is szeretnél a tervben, jelöld az Erősítés / kondi
        sportágat fő vagy kiegészítő szereppel, a felkészülés sportágát pedig fő
        sportágként.
      </p>
      <Select
        label="Melyik mentett felkészüléshez kapcsolódik?"
        value={data.program_reference?.artifact_id ?? ""}
        onChange={(e) => {
          const p = context.sources.programs.find(
            (p) => p.reference.artifact_id === e.target.value,
          );
          patch({
            program_reference: p?.reference ?? null,
            goal_label: p?.title ?? data.goal_label,
          });
        }}
      >
        <option value="">Általános kiindulófelmérés</option>
        {context.sources.programs.map((p) => (
          <option key={p.reference.artifact_id} value={p.reference.artifact_id}>
            {p.title} · {p.sport}
          </option>
        ))}
      </Select>
      {!data.program_reference && (
        <Field
          label="Cél megnevezése · ha szeretnéd pontosítani"
          maxLength={200}
          value={data.goal_label}
          onChange={(e) => patch({ goal_label: e.target.value })}
        />
      )}
      <Place
        context={context}
        value={data.default_location_id}
        onChange={(v) => patch({ default_location_id: v })}
      />
      <p className="pt-options-meta">
        Ez lesz az új gyakorlatkártyák javasolt helyszíne. A már felvett kártyák
        saját helyszíne megmarad.
      </p>
      <div className="pt-assessment-sports">
        {registry.sports.map((s) => {
          const selected = data.sports.find((x) => x.sport_key === s.key),
            locked = data.sport_references.some((r) => r.sport_key === s.key);
          return (
            <label key={s.key}>
              <input
                type="checkbox"
                checked={!!selected}
                disabled={!!selected && locked}
                onChange={(e) =>
                  patch({
                    sports: e.target.checked
                      ? [...data.sports, blankSport(s.key)]
                      : data.sports.filter((v) => v.sport_key !== s.key),
                  })
                }
              />
              {s.label}
              {locked && <small> · van hozzá teljesítményadat</small>}
            </label>
          );
        })}
      </div>
      {data.sports.map((s) => {
        const sportModule = registry.sports.find((m) => m.key === s.sport_key);
        return (
          <article className="pt-panel pt-assessment-fields" key={s.sport_key}>
            <h3>{sportModule?.label ?? s.sport_key}</h3>
            <Choice
              label="Szerepe ebben a felkészülésben"
              value={s.role}
              options={{
                unknown,
                primary: "Fő sportág",
                secondary: "Kiegészítő sportág",
                recreation: "Szabadidős / alkalomszerű",
                paused: "Jelenleg szünetel",
              }}
              onChange={(v) =>
                editSport(s.sport_key, { role: v as Sport["role"] })
              }
            />
            <Field
              label="Szakág / változat"
              maxLength={200}
              list={`disciplines-${s.sport_key}`}
              value={s.discipline}
              onChange={(e) =>
                editSport(s.sport_key, { discipline: e.target.value })
              }
            />
            <datalist id={`disciplines-${s.sport_key}`}>
              {sportModule?.disciplines.map((d) => (
                <option key={d} value={d} />
              ))}
            </datalist>
            <Field
              label="Sportági cél / céltáv"
              maxLength={200}
              value={s.goal}
              onChange={(e) => editSport(s.sport_key, { goal: e.target.value })}
            />
            <p>
              Felmérési hangsúlyok:{" "}
              {sportModule?.focus.join("; ") ?? "általános kiindulópont"}.
            </p>
            <p className="pt-options-meta">
              Adatrögzítés és saját referenciák: támogatott.{" "}
              {sportModule?.planning_support === "sample_family" || ["KAYAK", "RUNNING", "STRENGTH", "SWIMMING"].includes(s.sport_key)
                ? "Az edzéstervezőben ehhez a sportághoz kezdő minták is elérhetők, a megadott lehetőségek és korlátok szerint."
                : "Az önálló sportági edzésgenerálás még nincs bekötve."}{" "}
              Ezek a felmérési modulok nem adnak automatikus tesztnormát vagy
              edzésdózist.
            </p>
          </article>
        );
      })}
    </div>,
    <div key="exercises" className="pt-assessment-fields">
      <p>
        Kiindulásként az öt mozgásmintához válassz gyakorlatot és add meg a
        jártasságodat. A hiányzó referencia később pótolható.
      </p>
      {registry.patterns.map((pattern) => (
        <section key={pattern.key} className="pt-assessment-fields">
          <div className="pt-section-heading">
            <h3>{pattern.label}</h3>
            <button
              type="button"
              className={secondaryClass}
              disabled={data.exercises.length >= 64}
              onClick={() =>
                patch({
                  exercises: [
                    ...data.exercises,
                    newExercise(pattern.key, data.default_location_id),
                  ],
                })
              }
            >
              + Gyakorlat hozzáadása
            </button>
          </div>
          {assessmentRecommendations(context.sources, data, context.local_today).filter((r) => r.pattern === pattern.key).map((r) => (
            <aside key={r.entryId} className="pt-guided-recommendation" aria-label={`${pattern.label} felmérési ajánlása`}>
              <strong>Most ajánlott: {r.label}</strong>
              <p>{r.reasons.join(" ")}</p>
              <p className="pt-options-meta">A többi gyakorlatból felvett saját eredmény is megmarad.</p>
            </aside>
          ))}
          {data.exercises
            .filter((e) => e.pattern === pattern.key)
            .map((e) => {
              const place = context.sources.locations.find(
                  (l) => l.id === e.location_id,
                ),
                possible = new Set(
                  place
                    ? availableExercises(catalog, place).map((x) => x.id)
                    : [],
                ),
                selected = catalog.exercises.find(
                  (x) => x.id === e.exercise_id,
                ),
                state = summary.exercise_states.find((x) => x.id === e.id);
              return (
                <article key={e.id} className="pt-panel pt-assessment-fields">
                  <Place
                    context={context}
                    value={e.location_id}
                    onChange={(v) => editExercise(e.id, { location_id: v })}
                  />
                  <Select
                    label="Gyakorlat"
                    value={e.exercise_id ?? ""}
                    onChange={(event) =>
                      editExercise(e.id, {
                        exercise_id: event.target.value || null,
                      })
                    }
                  >
                    <option value="">Még nem tudok választani</option>
                    {pattern.exercise_ids.map((id) => {
                      const x = catalog.exercises.find((x) => x.id === id);
                      return (
                        <option key={id} value={id}>
                          {x?.label ?? id}
                          {possible.has(id)
                            ? place?.exercise_confirmations?.some(
                                (c) => c.exercise_id === id,
                              )
                              ? " · helyszíni saját megadás"
                              : " · eszközei megvannak"
                            : " · helyszíni eszközegyezés pontosítandó"}
                        </option>
                      );
                    })}
                  </Select>
                  {selected && (
                    <p className="pt-options-meta">
                      {selected.english} · Eszközök:{" "}
                      {selected.requirements
                        .map((g) =>
                          g
                            .map(
                              (id) =>
                                catalog.equipment.find((x) => x.id === id)
                                  ?.label ?? id,
                            )
                            .join(" + "),
                        )
                        .join(" vagy ")}
                    </p>
                  )}
                  {place?.exercise_confirmations?.some(
                    (c) => c.exercise_id === e.exercise_id,
                  ) && (
                    <p className="pt-options-meta">
                      Helyszíni elérhetőség: saját megadás alapján.
                    </p>
                  )}
                  <div className="pt-options-columns">
                    <Choice
                      label="Mennyire ismered ezt a gyakorlatot?"
                      value={e.familiarity}
                      options={familiarity}
                      onChange={(v) =>
                        editExercise(e.id, {
                          familiarity: v as Exercise["familiarity"],
                        })
                      }
                    />
                    <Choice
                      label="Tapasztalatod a mozgás közben"
                      value={e.comfort}
                      options={comfort}
                      onChange={(v) =>
                        editExercise(e.id, {
                          comfort: v as Exercise["comfort"],
                        })
                      }
                    />
                  </div>
                  <Area
                    label="Segítségigény, kerülendő mozdulat vagy megjegyzés"
                    maxLength={2000}
                    value={e.notes}
                    onChange={(event) =>
                      editExercise(e.id, { notes: event.target.value })
                    }
                  />
                  {state && <p role="status">{stateLabels[state.state]}</p>}
                  {selected?.guide_id && (
                    <a
                      className="underline"
                      href={
                        catalog.guides.find((g) => g.id === selected.guide_id)
                          ?.src
                      }
                      target="_blank"
                      rel="noreferrer"
                    >
                      Kapcsolódó szemléltető lap megnyitása
                    </a>
                  )}
                  <button
                    type="button"
                    className={secondaryClass}
                    onClick={() =>
                      patch({
                        exercises: data.exercises.filter((x) => x.id !== e.id),
                      })
                    }
                  >
                    Gyakorlatkártya eltávolítása
                  </button>
                </article>
              );
            })}
        </section>
      ))}
    </div>,
    <div key="references" className="pt-assessment-fields">
      <p>
        Ha még nincs friss saját sorozateredményed, a válaszok mentése után{" "}
        <Link href="/strength-assessment" className="underline">
          vezetett kezdő felmérőalkalmat indíthatsz
        </Link>
        . Itt a korábbi ismert eredményeket is megadhatod.
      </p>
      <p>
        Korábban elvégzett, ismert teljesítést írj be. Egy sor egy elvégzett
        sorozat. Ha nincs ilyen adatod, hagyd üresen; a kitöltés most nem kér
        maximális próbát.
      </p>
      {data.exercises.map((e) => (
        <article className="pt-panel pt-assessment-fields" key={e.id}>
          <h3>
            {catalog.exercises.find((x) => x.id === e.exercise_id)?.label ??
              registry.patterns.find((p) => p.key === e.pattern)?.label}
          </h3>
          <div className="pt-options-columns">
            <Field
              label="Teljesítés dátuma · ha ismert"
              type="date"
              max={data.assessment_date}
              value={e.performed_on ?? ""}
              onChange={(event) =>
                editExercise(e.id, { performed_on: event.target.value || null })
              }
            />
            <Choice
              label="Oldal / végrehajtás"
              value={e.side}
              options={{
                unknown,
                both: "Kétoldali",
                left: "Bal",
                right: "Jobb",
                alternating: "Váltott",
              }}
              onChange={(v) =>
                editExercise(e.id, { side: v as Exercise["side"] })
              }
            />
          </div>
          <Field
            label="Konkrét gép, fogantyú és beállítás · ha releváns"
            maxLength={200}
            value={e.machine_note}
            onChange={(event) =>
              editExercise(e.id, { machine_note: event.target.value })
            }
          />
          {e.sets.map((s, i) => (
            <fieldset className="pt-assessment-set" key={s.id}>
              <legend>{i + 1}. elvégzett sorozat · saját megadás</legend>
              <div className="pt-options-columns">
                <IntegerField
                  label="Ismétlésszám · vagy tartási idő"
                  value={s.repetitions}
                  max={10000}
                  onChange={(v) =>
                    editSet(e, s.id, {
                      repetitions: v,
                      ...(v !== null ? { hold_seconds: null } : {}),
                    })
                  }
                />
                <DecimalField
                  label="Tartási idő (másodperc)"
                  value={s.hold_seconds}
                  onChange={(v) =>
                    editSet(e, s.id, {
                      hold_seconds: v,
                      ...(v !== null ? { repetitions: null } : {}),
                    })
                  }
                />
                <Choice
                  label="Terhelés típusa"
                  value={s.load_kind}
                  options={{
                    unknown,
                    bodyweight: "Saját testsúly",
                    external_kg: "Külső teher (kg)",
                    assistance_kg: "Rásegítés (kg)",
                    machine_level: "Gép fokozata",
                    band: "Szalag / egyéb ellenállás",
                  }}
                  onChange={(v) =>
                    editSet(e, s.id, {
                      load_kind: v as SetRecord["load_kind"],
                      load_value: null,
                      load_basis:
                        v === "bodyweight"
                          ? "not_applicable"
                          : v === "assistance_kg"
                            ? "assistance"
                            : "unknown",
                    })
                  }
                />
                {["external_kg", "assistance_kg", "machine_level"].includes(
                  s.load_kind,
                ) && (
                  <DecimalField
                    label={
                      s.load_kind === "machine_level"
                        ? "Fokozat"
                        : "Teher / rásegítés (kg)"
                    }
                    value={s.load_value}
                    onChange={(v) => editSet(e, s.id, { load_value: v })}
                  />
                )}
                <Choice
                  label="A megadott terhelés jelentése"
                  value={s.load_basis}
                  options={Object.fromEntries(
                    loadBases[s.load_kind].map((b) => [
                      b,
                      (
                        {
                          unknown,
                          total: "Összsúly",
                          per_hand: "Kézisúlyzónként / kézenként",
                          machine_display: "Gép kijelzett értéke",
                          assistance: "Rásegítés mértéke",
                          not_applicable: "Nincs kg-érték / saját testsúly",
                        } as Record<string, string>
                      )[b],
                    ]),
                  )}
                  onChange={(v) =>
                    editSet(e, s.id, {
                      load_basis: v as SetRecord["load_basis"],
                    })
                  }
                />
                <Choice
                  label="Becsült szabályos ismétléstartalék (RIR)"
                  value={s.rir}
                  options={{
                    unknown,
                    "0": "0",
                    "1": "1",
                    "2": "2",
                    "3": "3",
                    "4": "4",
                    "5_plus": "5 vagy több",
                  }}
                  onChange={(v) =>
                    editSet(e, s.id, { rir: v as SetRecord["rir"] })
                  }
                />
                <Choice
                  label="Kivitelezés a sorozatban"
                  value={s.technique}
                  options={{
                    unknown,
                    stable: "Stabil",
                    uncertain: "Bizonytalan",
                    breakdown: "A technika romlott",
                  }}
                  onChange={(v) =>
                    editSet(e, s.id, { technique: v as SetRecord["technique"] })
                  }
                />
                <Choice
                  label="Panasz a sorozat közben"
                  value={s.symptoms}
                  options={{
                    unknown,
                    none: "Panaszmentes",
                    discomfort: "Kellemetlenség",
                    pain: "Fájdalom",
                  }}
                  onChange={(v) =>
                    editSet(e, s.id, { symptoms: v as SetRecord["symptoms"] })
                  }
                />
              </div>
              <Field
                label="Teher vagy szalag pontosítása"
                maxLength={200}
                value={s.load_note}
                onChange={(event) =>
                  editSet(e, s.id, { load_note: event.target.value })
                }
              />
              <button
                type="button"
                className={secondaryClass}
                onClick={() =>
                  editExercise(e.id, {
                    sets: e.sets.filter((x) => x.id !== s.id),
                  })
                }
              >
                Sorozat eltávolítása
              </button>
            </fieldset>
          ))}
          <button
            type="button"
            className={secondaryClass}
            disabled={e.sets.length >= 20}
            onClick={() => editExercise(e.id, { sets: [...e.sets, newSet()] })}
          >
            + Elvégzett sorozat
          </button>
        </article>
      ))}
      <h3>Sportági teljesítményreferenciák</h3>
      <p className="pt-options-meta">
        Ezek önbevallott hivatkozások. A felmérésből nem keletkezik új naptári
        edzés, így egy korábbi alkalom nem számítódik be még egyszer.
      </p>
      {data.sport_references.map((r) => (
        <article className="pt-panel pt-assessment-fields" key={r.id}>
          <Choice
            label="Sportág"
            value={r.sport_key}
            options={Object.fromEntries(
              data.sports.map((s) => [
                s.sport_key,
                registry.sports.find((m) => m.key === s.sport_key)?.label ??
                  s.sport_key,
              ]),
            )}
            onChange={(v) => editReference(r.id, { sport_key: v })}
          />
          <p>
            {registry.sports.find((s) => s.key === r.sport_key)?.reference_help}
          </p>
          <div className="pt-options-columns">
            <Field
              label="Teljesítés dátuma"
              type="date"
              max={data.assessment_date}
              value={r.performed_on ?? ""}
              onChange={(e) =>
                editReference(r.id, { performed_on: e.target.value || null })
              }
            />
            <Field
              label="Mérés / alkalom megnevezése"
              maxLength={200}
              value={r.protocol}
              onChange={(e) =>
                editReference(r.id, { protocol: e.target.value })
              }
            />
            <DecimalField
              label="Táv (méter)"
              value={r.distance_m}
              onChange={(v) => editReference(r.id, { distance_m: v })}
            />
            <DecimalField
              label="Időtartam (perc)"
              value={r.duration_minutes}
              onChange={(v) => editReference(r.id, { duration_minutes: v })}
            />
            <Choice
              label="Az időtartam értelmezése"
              value={r.duration_basis}
              options={{
                unknown,
                elapsed: "Teljes eltelt idő",
                active: "Aktív idő",
              }}
              onChange={(v) =>
                editReference(r.id, {
                  duration_basis: v as SportReference["duration_basis"],
                })
              }
            />
            <DecimalField
              label="Mért teljesítmény (watt) · ha ismert"
              value={r.power_w}
              onChange={(v) => editReference(r.id, { power_w: v })}
            />
            <IntegerField
              label="Pulzus (bpm) · ha ismert"
              value={r.heart_rate_bpm}
              max={300}
              onChange={(v) => editReference(r.id, { heart_rate_bpm: v })}
            />
            <IntegerField
              label="Érzékelt erőfeszítés (RPE, 0–10) · ha ismert"
              value={r.rpe}
              max={10}
              onChange={(v) => editReference(r.id, { rpe: v })}
            />
            <DecimalField
              label="Szintemelkedés (méter)"
              value={r.elevation_gain_m}
              onChange={(v) => editReference(r.id, { elevation_gain_m: v })}
            />
            <DecimalField
              label="Medencehossz (méter)"
              value={r.pool_length_m}
              onChange={(v) => editReference(r.id, { pool_length_m: v })}
            />
          </div>
          <Place
            context={context}
            value={r.location_id}
            onChange={(v) => editReference(r.id, { location_id: v })}
          />
          <Field
            label="Konkrét hajó, kerékpár, görgő, gép vagy rajtmód"
            maxLength={200}
            value={r.equipment}
            onChange={(e) => editReference(r.id, { equipment: e.target.value })}
          />
          <Area
            label="Körülmények, terep, úszásnem vagy további megjegyzés"
            maxLength={2000}
            value={r.conditions}
            onChange={(e) =>
              editReference(r.id, { conditions: e.target.value })
            }
          />
          <button
            type="button"
            className={secondaryClass}
            onClick={() =>
              patch({
                sport_references: data.sport_references.filter(
                  (x) => x.id !== r.id,
                ),
                references_reviewed: false,
              })
            }
          >
            Referencia eltávolítása
          </button>
        </article>
      ))}
      <button
        type="button"
        className={secondaryClass}
        disabled={!data.sports.length || data.sport_references.length >= 100}
        onClick={() =>
          patch({
            sport_references: [
              ...data.sport_references,
              {
                id: crypto.randomUUID(),
                sport_key: data.sports[0].sport_key,
                performed_on: null,
                protocol: "",
                location_id: data.default_location_id,
                distance_m: null,
                duration_minutes: null,
                duration_basis: "unknown",
                power_w: null,
                heart_rate_bpm: null,
                rpe: null,
                elevation_gain_m: null,
                pool_length_m: null,
                equipment: "",
                conditions: "",
                source: "self_report",
              },
            ],
            references_reviewed: false,
          })
        }
      >
        + Sportági referencia
      </button>
      <label className="pt-options-check">
        <input
          type="checkbox"
          checked={data.references_reviewed}
          onChange={(e) => patch({ references_reviewed: e.target.checked })}
        />
        Átnéztem az ismert teljesítéseimet; a hiányzó adatok egyelőre
        ismeretlenek.
      </label>
    </div>,
    <div key="summary" className="pt-assessment-fields">
      <p>
        <strong>{summary.completed_steps} / 6 kitöltési lépés kész.</strong>{" "}
        {summary.recorded_reference_count} gyakorlatnál van az itteni szabályok
        szerint rögzített kiinduló referencia.
      </p>
      {summary.state_review_required && (
        <p role="status">Az állapot vagy a profil egyeztetése még szükséges.</p>
      )}
      {!data.exercises.length && (
        <p>
          Még nincs kiválasztott gyakorlat. Részleges felmérésként ez is
          menthető.
        </p>
      )}
      {summary.exercise_states.map((state) => {
        const e = data.exercises.find((e) => e.id === state.id)!;
        return (
          <article className="pt-panel" key={state.id}>
            <h3>
              {catalog.exercises.find((x) => x.id === e.exercise_id)?.label ??
                registry.patterns.find((p) => p.key === e.pattern)?.label}
            </h3>
            <p>
              <strong>{stateLabels[state.state]}</strong>
            </p>
            {state.reasons.length > 0 && (
              <ul>
                {state.reasons.map((r) => (
                  <li key={r}>{reasons[r] ?? r}</li>
                ))}
              </ul>
            )}
          </article>
        );
      })}
      <p>
        Az 56 napos referenciakeresés átlátható kezdőszabály. A felmérés
        önbevallott kiindulóadatokat rögzít; a mentés nem hoz létre edzéstervet,
        nem számol 1RM-et és nem ír elő súlyt.
      </p>
      <label className="pt-options-check">
        <input
          type="checkbox"
          checked={data.reviewed}
          onChange={(e) => patch({ reviewed: e.target.checked })}
        />
        Átnéztem a felmérés adatait és a még hiányzó részeket.
      </label>
    </div>,
  ];
  return (
    <div className="pt-assessment-steps">
      <p className="pt-assessment-progress" role="status">
        Kitöltés: {summary.completed_steps} / 6 lépés · Referenciák:{" "}
        {summary.recorded_reference_count} gyakorlat
      </p>
      {titles.map((title, i) => (
        <section className="pt-panel pt-assessment-step" key={title}>
          <button
            type="button"
            className="pt-assessment-step-title"
            aria-expanded={open === i}
            aria-controls={`assessment-step-${i}`}
            onClick={() => onOpen(i)}
          >
            <span>
              {i + 1}. {title}
            </span>
            <small>
              {summary.steps[i]
                ? "Kitöltve"
                : open === i
                  ? "Most következik"
                  : "Pontosítandó"}
            </small>
          </button>
          {open === i && (
            <div id={`assessment-step-${i}`}>
              {notice}
              <fieldset disabled={disabled}>{panels[i]}</fieldset>
              <div className="pt-options-actions">
                {i > 0 && (
                  <button
                    type="button"
                    className={secondaryClass}
                    onClick={() => onOpen(i - 1)}
                  >
                    Vissza
                  </button>
                )}
                {i < 5 && (
                  <button
                    type="button"
                    className={secondaryClass}
                    onClick={() => onOpen(i + 1)}
                  >
                    Tovább
                  </button>
                )}
              </div>
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
