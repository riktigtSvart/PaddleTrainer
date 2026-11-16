"use client";
import Link from "next/link";
import type { ReactNode } from "react";
import { Choice } from "@/components/initial-assessment/fields";
import { buttonClass } from "@/components/planning-goals/fields";
import {
  choiceState,
  entryReasons,
  startIssues,
} from "@/lib/guided-strength/preparation";
import { equipmentGaps } from "@/lib/training-options/strength-catalog";
import type { Context } from "@/lib/guided-strength/contracts";
import ProtocolPreview from "./protocol-preview";
import { recommendationsForContext } from "@/lib/guided-strength/recommendations";
import { dynamicFamilies, protocolFor, forMeasurementMode } from "@/lib/guided-strength/calibration";
import { CalibrationInstructions } from "./calibration-movement";
export default function GuidedPreparation({
  context,
  locked,
  place,
  ids,
  mode,
  precheck,
  onPlace,
  onIds,
  onMode,
  onPrecheck,
  onBegin,
  onResolveIntake,
  intakeEditor,
  onCloseIntake,
  measurementMode = "calibration",
  onMeasurementMode,
}: {
  context: Context;
  locked: boolean;
  place: string;
  ids: string[];
  mode: "device" | "manual";
  precheck: boolean;
  onPlace: (v: string) => void;
  onIds: (v: string[]) => void;
  onMode: (v: "device" | "manual") => void;
  onPrecheck: (v: boolean) => void;
  onBegin: () => void;
  onResolveIntake?: () => void;
  intakeEditor?: ReactNode;
  onCloseIntake?: () => void;
  measurementMode?: "calibration" | "repeatability";
  onMeasurementMode?: (v: "calibration" | "repeatability") => void;
}) {
  const issues = startIssues(context),
    chosen = context.preparation.locations.find((p) => p.location_id === place);
  const location = context.intake.sources.locations.find((p) => p.id === place);
  const recommendations = recommendationsForContext(context.intake, place);
  const repeatabilityUnsupported = measurementMode === "repeatability" && chosen?.entries.some((e) => ids.includes(e.entry_id) && !dynamicFamilies.has(protocolFor(e.exercise_id)?.family ?? ""));
  return (
    <section
      className="pt-panel pt-assessment-fields"
      aria-label="Felmérés előkészítése"
    >
      <h2>Kezdő felmérőalkalom előkészítése</h2>
      <p>
        Most hozzuk létre az első saját referenciákat. Korábbi friss eredmény
        nem szükséges. Csak már ismert, panaszmentes gyakorlatot válassz; amihez
        betanulás kell, azt egyelőre hagyd ki.
      </p>
      <p>
        A felmérést egy szokásos erősítő edzés elején is elvégezheted; nem kell
        külön edzésnap. Itt először a gyakorlatokat választod ki. A súlyt,
        ismétlést és a többi eredményt az indítás után tudod beírni.
      </p>
      {!!issues.length && (
        <aside
          id="pt-guided-start-issues"
          className="pt-guided-blockers"
          aria-label="Az indítás előfeltételei"
        >
          <h3>Mi hiányzik még az indításhoz?</h3>
          <p>
            Az alábbi mentett adatok akadályozzák az indítást. Az előkészítéshez
            közben kiválaszthatod a megfelelő gyakorlatokat.
          </p>
          <ul>
            {issues.map((i) => (
              <li key={i.code}>
                <strong>{i.title}</strong>
                {i.details.map((d, n) => (
                  <p key={n}>{d}</p>
                ))}
                <Link href={i.href}>{i.action}</Link>
              </li>
            ))}
          </ul>
          {onResolveIntake && !intakeEditor ? (
            <>
              <button
                type="button"
                className={buttonClass}
                disabled={locked}
                onClick={onResolveIntake}
              >
                Kezdeti válaszok ellenőrzése és mentése itt
              </button>
              <p>
                A szerkesztő ezen az oldalon nyílik meg. A már kiválasztott
                gyakorlatok megmaradnak. A válaszok mentése után az indíthatóság
                is frissül.
              </p>
            </>
          ) : !intakeEditor ? (
            <p className="pt-options-meta">
              Az adatok ellenőrzése és mentése után itt kattints a
              „Szerverállapot frissítése” gombra.
            </p>
          ) : null}
        </aside>
      )}
      {!issues.length && onResolveIntake && !intakeEditor && (
        <button
          type="button"
          className={buttonClass}
          disabled={locked}
          onClick={onResolveIntake}
        >
          Kezdeti válaszok ellenőrzése és mentése itt
        </button>
      )}
      {intakeEditor}
      <fieldset disabled={locked || !!intakeEditor}>
        <Choice
          label="Az alkalom helyszíne"
          value={place}
          options={Object.fromEntries(
            context.preparation.locations.map((p) => [p.location_id, p.name]),
          )}
          onChange={onPlace}
        />
        <p>
          Válassz 1–5 különböző mozgásmintát. A kezdő edzéstervhez legalább két
          különböző mintából kell használható referencia; nem szükséges mindet
          ma felmérni.
        </p>
        {context.calibration_protocols && <>
          <p>Első alkalomra 1–2 ismert gyakorlat is elegendő. Az ajánlás a meglévő választási lehetőségeket egészíti ki.</p>
          {!!recommendations.length && <aside className="pt-guided-recommendation" aria-label="Sportági felmérési ajánlások">
            <h3>Most ezt érdemes felmérned</h3>
            {recommendations.map((r) => <p key={r.entryId}><strong>{context.intake.sources.registry.patterns.find((p) => p.key === r.pattern)?.label}: {r.label}</strong><br />{r.reasons.join(" ")}</p>)}
          </aside>}
          <Choice label="A mérés célja" value={measurementMode} options={{ calibration: "Kezdő terheléskalibrálás / saját referencia", repeatability: "Ismételt sorozatok megfigyelése · már ismert terheléssel" }} onChange={(v) => onMeasurementMode?.(v as "calibration" | "repeatability")} />
        </>}
        <div className="pt-guided-choices">
          {chosen?.entries.map((e) => {
            const state = choiceState(e, chosen.entries, ids);
            const confirmation = location?.exercise_confirmations?.find(
              (c) => c.exercise_id === e.exercise_id,
            );
            const gaps =
              e.exercise_id &&
              location &&
              e.issues.includes("GUIDED_EQUIPMENT_MISSING")
                ? equipmentGaps(
                    context.intake.sources.catalog,
                    e.exercise_id,
                    location.resources,
                  )
                : [];
            return (
              <div className="pt-guided-option" key={e.entry_id}>
                <label className="pt-guided-choice">
                  <input
                    type="checkbox"
                    checked={ids.includes(e.entry_id)}
                    disabled={!state.selectable}
                    aria-describedby={`pt-guided-entry-${e.entry_id}`}
                    onChange={(ev) =>
                      onIds(
                        ev.target.checked
                          ? [...ids, e.entry_id]
                          : ids.filter((id) => id !== e.entry_id),
                      )
                    }
                  />
                  <span>
                    <span className="pt-options-meta">{context.intake.sources.registry.patterns.find((p) => p.key === e.pattern)?.label}</span>
                    <strong>{e.label}</strong>
                    {context.calibration_protocols && recommendations.some((r) => r.entryId === e.entry_id) && <span className="pt-badge">Most ajánlott felmérés</span>}
                    <span
                      id={`pt-guided-entry-${e.entry_id}`}
                      className="pt-guided-choice-reasons"
                    >
                      {e.issues.map((code) => (
                        <span className="pt-options-meta" key={code}>
                          {entryReasons[code] ?? code}
                        </span>
                      ))}
                      {confirmation && (
                        <span className="pt-options-meta">
                          Helyszíni elérhetőség: saját megadás alapján.
                          {confirmation.note ? " " + confirmation.note : ""}
                        </span>
                      )}
                      {gaps.map((g, i) => (
                        <span className="pt-options-meta" key={i}>
                          {gaps.length > 1
                            ? `${i + 1}. eszközváltozatból hiányzik: `
                            : "Az eszközlistából hiányzik: "}
                          {g.join(", ") || "nincs hiányzó elem"}.
                        </span>
                      ))}
                      {state.samePattern && (
                        <span>
                          Ehhez a mozgásmintához már választottál másik
                          gyakorlatot.
                        </span>
                      )}
                      {state.selectable && issues.length > 0 && (
                        <span>
                          Az előkészítéshez kiválasztható. Az indítás közös
                          előfeltétele még hiányzik.
                        </span>
                      )}
                      {state.selectable && !issues.length && (
                        <span className="pt-options-meta">
                          Kiválasztható a mentett jártasság és helyszíni
                          lehetőség alapján.
                        </span>
                      )}
                    </span>
                  </span>
                </label>
                {e.issues.includes("GUIDED_EQUIPMENT_MISSING") && (
                  <Link
                    className="pt-guided-entry-action"
                    href="/training-options/locations"
                  >
                    Helyszíni felszerelés vagy saját gyakorlatmegadás
                  </Link>
                )}
                {e.issues.some((c) => c !== "GUIDED_EQUIPMENT_MISSING") && (
                  <Link
                    className="pt-guided-entry-action"
                    href="/initial-assessment?step=4"
                  >
                    Gyakorlat és jártasság ellenőrzése
                  </Link>
                )}
              </div>
            );
          })}
        </div>
        {!chosen?.entries.length && (
          <p>
            Ezen a helyszínen még nincs kiválasztott erőgyakorlat. Add meg a
            kezdeti felmérésben.
          </p>
        )}
        <h3>Gyakorlatadatok: mindkét esetben kézzel</h3>
        <p>
          Az ismétlésszámot, a használt súlyt, a tartalékot és a kivitelezést
          itt te rögzíted. Nem várunk az órától gyakorlatfelismerést vagy
          ismétlésszámlálást. Az alábbi választás csak az egész edzés
          naplóbejegyzéséről szól.
        </p>
        <Choice
          label="Az egész edzés naplózása"
          value={mode}
          options={{
            device: "Meglévő vagy órával rögzített edzéshez kapcsolom",
            manual: "Új edzésnapló-bejegyzést készítek kézzel",
          }}
          onChange={(v) => onMode(v as "device" | "manual")}
        />
        <p className="pt-options-meta">
          {mode === "device"
            ? "A teljes erősítő edzés saját felvételét a végén kapcsolod hozzá. Az óra az egész alkalom idejét és az általa mért adatokat adja; a sorozatok eredményeit itt írod be."
            : "Az egész edzés valós kezdését és befejezését a végén ellenőrzöd. Csak akkor készíts új kézi bejegyzést, ha ugyanerről az edzésről nincs már órás vagy másik naplóbejegyzés."}
        </p>
        <label className="pt-guided-check">
          <input
            type="checkbox"
            checked={precheck}
            onChange={(e) => onPrecheck(e.target.checked)}
          />
          A mentett állapotom és a helyszín adatai aktuálisak. A kiválasztott
          gyakorlatokat ismerem, panaszmentesen végzem, és szükség esetén tudok
          segítséget kérni.
        </label>
        <p id="pt-guided-start-status" role="status">
          {intakeEditor
            ? "A kezdeti válaszok szerkesztője nyitva van. Mentsd a válaszokat, vagy térj vissza a gyakorlatválasztáshoz a fenti gombbal."
            : issues.length
              ? "A gyakorlatokat előkészítheted; az indítás előtt a fent jelzett mentett adatokat kell tisztázni."
              : !ids.length
                ? "Az indításhoz válassz legalább egy gyakorlatot."
                : !precheck
                  ? "Az indításhoz még jelöld az aktuális állapotról szóló nyilatkozatot."
                  : "A kiválasztott gyakorlatokkal elindítható a felmérés."}
        </p>
        <button
          type="button"
          className={buttonClass}
          aria-describedby="pt-guided-start-status"
          disabled={
            !precheck || !ids.length || !!issues.length || !!intakeEditor || !!repeatabilityUnsupported
          }
          onClick={onBegin}
        >
          Felmérőalkalom indítása
        </button>
        {repeatabilityUnsupported && <p role="status">Az ismételt sorozatok menete a dinamikus erőgyakorlatokhoz használható. A kijelölt kitartás, cipelés vagy robbanékony próba saját referenciafelvételéhez válaszd a kezdő módot.</p>}
      </fieldset>
      {intakeEditor && onCloseIntake && (
        <aside
          className="pt-guided-blockers"
          aria-label="Visszatérés az indításhoz"
        >
          <p>
            A kezdeti szerkesztő nyitva van. A lenti gomb bezárja és frissen
            ellenőrzi az indíthatóságot. A szerkesztett válaszok helyi
            piszkozatban megmaradnak; az indítás a szerveren mentett adatokra
            támaszkodik.
          </p>
          <button
            type="button"
            className={buttonClass}
            disabled={locked}
            onClick={onCloseIntake}
          >
            Vissza a gyakorlatválasztáshoz
          </button>
        </aside>
      )}
      {!!issues.length && (
        <aside
          className="pt-guided-blockers"
          aria-label="Még hiányzó mentett adatok az indításnál"
        >
          <h3>A mentett adatokból még ez hiányzik az indításhoz</h3>
          <ul>
            {issues.map((i) => (
              <li key={i.code}>
                <strong>{i.title}</strong>
                {i.details.map((d, n) => (
                  <p key={n}>{d}</p>
                ))}
                <Link href={i.href}>{i.action}</Link>
              </li>
            ))}
          </ul>
        </aside>
      )}
      {context.calibration_protocols ? <section className="pt-calibration-preview" aria-label="A kiválasztott gyakorlatok felmérési menete">
        <h3>A kiválasztott gyakorlatok felmérési menete</h3>
        <p>Az indítás után ugyanitt nyílnak meg a súly, ismétlés, idő és megállási ok mezői. A mérés után minden tényleges próba külön menthető.</p>
        {ids.flatMap((id) => { const e = chosen?.entries.find((v) => v.entry_id === id); return e ? [e] : []; }).map((e) => {
          const p = protocolFor(e.exercise_id, context.calibration_protocols);
          return p ? <details key={e.entry_id}><summary>{e.label}</summary><CalibrationInstructions protocol={forMeasurementMode(p, measurementMode, context.calibration_protocols)} mode={measurementMode} /></details> : null;
        })}
      </section> : <ProtocolPreview
        preparation={context.preparation}
        locationId={place}
        selectedIds={ids}
        catalog={context.intake.sources.catalog}
      />}
    </section>
  );
}
