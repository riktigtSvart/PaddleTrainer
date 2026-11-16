"use client";
import { useEffect, useState } from "react";
import { Field, buttonClass, secondaryClass } from "@/components/planning-goals/fields";
import { Choice, DecimalField, IntegerField } from "@/components/initial-assessment/fields";
import { newMeasurement, plateTotal, stopLabels, displayedProtocol } from "@/lib/guided-strength/calibration";
import type { Protocol } from "@/lib/guided-strength/calibration";
import type { Command, ExerciseResult, Observation } from "@/lib/guided-strength/contracts";

export const sideLabels = { unknown: "Még nincs megadva", both: "Kétoldali", left: "Bal oldal", right: "Jobb oldal", alternating: "Váltott oldal" };
export function CalibrationInstructions({ protocol, mode = "calibration" }: { protocol: Protocol; mode?: Command["measurement_mode"] }) {
  return <section className="pt-calibration-instructions" aria-label={`${protocol.label} felmérési utasítása`}>
    <h3>{mode === "repeatability" ? "Ismételt sorozatok menete" : "A felmérés menete"}</h3>
    {protocol.family === "bodyweight_repetitions" && <p><strong>A saját testsúlyod adott.</strong> Ebben az ismert gyakorlatváltozatban a szabályos ismétléseidet figyeljük meg. A felméréshez nem kell súlyt választanod vagy a testsúlyodat megváltoztatnod.</p>}
    <ol>{displayedProtocol(protocol, mode).steps.map((v, i) => <li key={i}>{v}</li>)}</ol>
  </section>;
}
export function MeasurementSummary({ value }: { value: Observation }) {
  const s = value;
  const amount = s.repetitions !== null ? `${s.repetitions} ismétlés` : s.hold_seconds !== null ? `${s.hold_seconds} másodperc tartás` :
    s.distance_m != null ? `${s.distance_m} méter${s.duration_seconds != null ? ` · ${s.duration_seconds} másodperc` : ""}` :
    s.measured_height_m != null ? `${s.measured_height_m} méter ugrásmagasság` : "mennyiség nincs megadva";
  return <p className="pt-calibration-summary">
    <strong>{s.trial_number}. próba</strong> · {s.performed_on} · {sideLabels[s.side ?? "unknown"]} · {amount}
    {" · "}{s.plate_configuration === "paired" ? `tárcsák: bal ${s.left_plates_kg ?? "?"} kg, jobb ${s.right_plates_kg ?? "?"} kg` : s.plate_configuration === "shared" ? `közös tüskén lévő tárcsák: ${s.shared_plates_kg ?? "?"} kg` : s.bar_kg != null || s.shared_plates_kg != null ? `rúd: ${s.bar_kg ?? "ismeretlen"} kg; rúdvégre tett tárcsák: ${s.shared_plates_kg ?? "ismeretlen"} kg` : s.load_kind === "bodyweight" ? "saját testsúly" : s.load_kind === "band" ? `szalag: ${s.load_note || "azonosító nincs megadva"}` : s.load_value === null ? "terhelés nincs megadva" : `${s.load_value} ${s.load_kind === "machine_level" ? "fokozat" : "kg"}${s.load_basis === "per_hand" ? " kézenként" : s.load_basis === "assistance" ? " rásegítés" : ""}`}
    {" · tartalék: "}{s.rir === "unknown" ? "ismeretlen" : s.rir === "5_plus" ? "legalább 5" : s.rir}
    {" · "}{stopLabels[s.stop_reason ?? "unknown"]}
    {" · kivitelezés: "}{{ unknown: "ismeretlen", stable: "stabil", uncertain: "bizonytalan", breakdown: "romlott" }[s.technique]}
    {" · panasz: "}{{ unknown: "ismeretlen", none: "nincs", discomfort: "kellemetlenség", pain: "fájdalom" }[s.symptoms]}
    {s.actual_rest_seconds != null && ` · tényleges pihenő: ${s.actual_rest_seconds} mp`}
    {s.setup_note && ` · ${s.setup_note}`}
    {s.metric_value != null && ` · ${s.metric_name}: ${s.metric_value} ${s.metric_unit}`}
    {!s.performed_confirmed && " · még nincs elvégzettként rögzítve"}
  </p>;
}
function Rest({ seconds, onActual }: { seconds: number; onActual: (v: number) => void }) {
  const [start, setStart] = useState<number | null>(null), [now, setNow] = useState(0);
  useEffect(() => { if (start === null) return; const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id); }, [start]);
  const elapsed = start === null ? 0 : Math.max(0, Math.floor((now - start) / 1000));
  return <aside className="pt-guided-rest">
    <p>{start === null ? `A következő próba előtt ${seconds / 60} perc a javasolt pihenő.` : elapsed < seconds ? `Pihenő: ${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")} eltelt.` : "Letelt a javasolt pihenő; szükség esetén pihenj tovább."}</p>
    <div className="pt-guided-actions">
      <button type="button" className={secondaryClass} onClick={() => { const n = Date.now(); setStart(n); setNow(n); }}>Pihenőmérés indítása</button>
      {start !== null && <button type="button" className={secondaryClass} onClick={() => { onActual(Math.max(0, Math.floor((Date.now() - start) / 1000))); setStart(null); }}>Eltelt pihenő beírása</button>}
    </div>
    <p className="pt-options-meta">A célidőt nem írjuk be automatikusan tényleges pihenőként.</p>
  </aside>;
}
export default function CalibrationMovement({ row, protocol, today, mode, onChange, onSave }: {
  row: ExerciseResult; protocol: Protocol; today: string; mode: Command["measurement_mode"];
  onChange: (v: ExerciseResult) => void; onSave: (v: ExerciseResult) => void;
}) {
  const blank = row.observations.find((v) => !v.performed_confirmed) ?? (row.observations.length ? null : newMeasurement(protocol, today, 1, mode));
  function update(value: Observation) {
    const found = row.observations.some((v) => v.id === value.id);
    onChange({ ...row, observations: found ? row.observations.map((v) => v.id === value.id ? value : v) : [...row.observations, value] });
  }
  const patch = (v: Partial<Observation>) => {
    if (!blank) return;
    const next = { ...blank, ...v };
    if (v.side !== undefined) next.trial_number = 1 + Math.max(0, ...row.observations.filter((s) => s.id !== next.id && s.side === v.side).map((s) => s.trial_number ?? 0));
    if (protocol.load_kind === "machine_plate_components") {
      next.load_value = next.plate_configuration === "shared" ? plateTotal([next.shared_plates_kg]) : next.plate_configuration === "paired" ? plateTotal([next.left_plates_kg, next.right_plates_kg]) : null;
    }
    update(next);
  };
  const actuals = row.observations.filter((v) => v.performed_confirmed);
  const targetRest = mode === "repeatability" ? 180 : protocol.planned_measurement.between_trials_rest_target_seconds ?? 180;
  const bodyweightTask = ["bodyweight_repetitions", "timed_hold"].includes(protocol.family);
  const loadChoice = blank && <Choice label="A használt terhelés típusa" value={blank.load_kind} options={protocol.load_kind === "machine_plate_components" || protocol.load_kind === "landmine_components" ? { external_kg: "A megadott eszköz és tárcsák tömege" } : { unknown: "Még nincs tisztázva", bodyweight: "Saját testsúly", external_kg: "Súly / gépi kg-kijelzés", machine_level: "Gépfokozat", assistance_kg: "Rásegítés kg-kijelzése", band: "Szalag" }} onChange={(v) => patch({ load_kind: v as Observation["load_kind"], load_value: null,
    load_basis: v === "bodyweight" || v === "band" ? "not_applicable" : v === "machine_level" ? "machine_display" : v === "assistance_kg" ? "assistance" : v === "external_kg" ? "total" : "unknown" })} />;
  return <>
    <CalibrationInstructions protocol={protocol} mode={mode} />
    <section aria-label={`${protocol.label} eredményei`} className="pt-calibration-results">
      <h3>Elvégzett próbák és eredménybevitel</h3>
      {actuals.map((s) => <article key={s.id} className="pt-guided-observation"><MeasurementSummary value={s} />
        {mode !== "repeatability" && protocol.family === "bodyweight_repetitions" && s.stop_reason === "planned_cap" && s.repetitions !== null && protocol.planned_measurement.repetition_cap !== null && s.repetitions >= protocol.planned_measurement.repetition_cap &&
          <p>A felmérési határig elvégzett {s.repetitions} ismétlés megőrzött eredmény. A maximális ismétlésszámod ebből még nem derül ki.</p>}
        <button type="button" className={secondaryClass} onClick={() => update({ ...s, performed_confirmed: false })} disabled={!!blank}>Próba adatainak javítása</button>
      </article>)}
      {blank ? <article className="pt-guided-observation">
        <h4>{actuals.length ? "Következő elvégzett próba adatai" : "Első próba eredménye"}</h4>
        <p>A ténylegesen elvégzett mennyiséget írd be. A tervezett határnál több ismétlés is menthető; az ismeretlen mezőt hagyd üresen.</p>
        <div className="pt-assessment-fields">
          <Field label="A teljesítés dátuma" type="date" max={today} value={blank.performed_on} onChange={(e) => patch({ performed_on: e.target.value })} />
          <Choice label="Ennek a próbának az oldala / végrehajtása" value={blank.side ?? "unknown"} options={sideLabels} onChange={(v) => patch({ side: v as Observation["side"] })} />
          {["each_side", "alternating_sides"].includes(protocol.side) && <p className="pt-options-meta">A kártya oldalankénti adatot kér: a bal és a jobb oldalt külön eredménysorban add meg. A két oldal ismétléseit ne add össze.</p>}
          <Field label="Gyakorlatváltozat, konkrét gép és beállítás" value={blank.setup_note ?? ""} maxLength={200} onChange={(e) => patch({ setup_note: e.target.value })} />
          {protocol.family === "timed_hold" ? <DecimalField label="Tényleges tartásidő (másodperc)" value={blank.hold_seconds} onChange={(v) => patch({ hold_seconds: v })} /> :
            protocol.family === "carry" ? <><DecimalField label="Ténylegesen megtett, mért távolság (m)" value={blank.distance_m ?? null} onChange={(v) => patch({ distance_m: v })} />
              <DecimalField label="Tényleges menetidő (másodperc)" value={blank.duration_seconds ?? null} onChange={(v) => patch({ duration_seconds: v })} /></> :
            <IntegerField label={protocol.family === "explosive_single_attempts" ? "Sikerült végrehajtás (0 vagy 1)" : "Tényleges szabályos ismétlésszám"} value={blank.repetitions} max={10000} onChange={(v) => patch({ repetitions: v })} />}
          {protocol.exercise_id === "jump_squat" && <DecimalField label="Mért ugrásmagasság (m) · ha valóban megmérted" value={blank.measured_height_m ?? null} onChange={(v) => patch({ measured_height_m: v })} />}
          {["rotational_throw", "forward_throw"].includes(protocol.exercise_id) && <DecimalField label="Mért dobástáv (m) · ha azonos módon megmérted" value={blank.distance_m ?? null} onChange={(v) => patch({ distance_m: v })} />}
          {bodyweightTask && blank.load_kind === "bodyweight" ? <div>
            <p><strong>Saját testsúly · külső súly nélkül</strong></p>
            <p>Nem kell terhelést vagy kg-értéket választanod. Az ismert változatban elvégzett {protocol.family === "timed_hold" ? "tartás idejét" : "szabályos ismétléseket"} rögzítsd.</p>
            <details><summary>Eltérő terheléssel elvégzett próba adatai</summary>{loadChoice}</details>
          </div> : loadChoice}
          {protocol.load_kind === "machine_plate_components" ? <>
            <Choice label="A tárcsák elhelyezése" value={blank.plate_configuration ?? "unknown"} options={{ unknown: "Még nincs tisztázva", shared: "Közös tüske / szán", paired: "Külön bal és jobb oldal" }} onChange={(v) => patch({ plate_configuration: v as Observation["plate_configuration"], left_plates_kg: null, right_plates_kg: null, shared_plates_kg: null })} />
            {blank.plate_configuration === "shared" && <DecimalField label="Közös tüskére tett tárcsák (kg)" value={blank.shared_plates_kg ?? null} onChange={(v) => patch({ shared_plates_kg: v })} />}
            {blank.plate_configuration === "paired" && <><DecimalField label="Bal oldalra tett tárcsák (kg)" value={blank.left_plates_kg ?? null} onChange={(v) => patch({ left_plates_kg: v })} /><DecimalField label="Jobb oldalra tett tárcsák (kg)" value={blank.right_plates_kg ?? null} onChange={(v) => patch({ right_plates_kg: v })} /></>}
            <p>A felrakott tárcsák összege: {blank.load_value ?? "még ismeretlen"} kg. Az üres gép ellenállását nem adjuk hozzá.</p>
          </> : protocol.load_kind !== "landmine_components" && ["external_kg", "machine_level", "assistance_kg"].includes(blank.load_kind) && <>
            <DecimalField label={blank.load_kind === "machine_level" ? "Tényleges gépfokozat" : blank.load_kind === "assistance_kg" ? "Tényleges rásegítés (kg-kijelzés)" : "Tényleges terhelés (kg)"} value={blank.load_value} onChange={(v) => patch({ load_value: v })} />
            <Choice label="A megadott terhelés jelentése" value={blank.load_basis} options={blank.load_kind === "assistance_kg" ? { assistance: "Rásegítés" } : blank.load_kind === "machine_level" ? { machine_display: "A konkrét gép kijelzése" } : { total: "Összesen · rúdnál a rúddal együtt", per_hand: "Kézenként", machine_display: "A konkrét gép kg-kijelzése" }} onChange={(v) => patch({ load_basis: v as Observation["load_basis"] })} />
          </>}
          {protocol.load_kind === "landmine_components" && <><DecimalField label="Rúd tömege (kg) · ha ismert" value={blank.bar_kg ?? null} onChange={(v) => patch({ bar_kg: v })} /><DecimalField label="Szabad rúdvégre tett tárcsák (kg)" value={blank.shared_plates_kg ?? null} onChange={(v) => patch({ shared_plates_kg: v })} /><p>A rúd és a tárcsák külön adat; ezekből nem számítunk szabadon emelt rúdsúlyt.</p></>}
          <Field label={blank.load_kind === "band" ? "Szalag azonosítója, rögzítése és megnyúlása" : "Terhelés / mérési mód megjegyzése"} value={blank.load_note} maxLength={200} onChange={(e) => patch({ load_note: e.target.value })} />
          <Choice label="Szabályos ismétléstartalék a végén" value={blank.rir} options={{ unknown: "Nem tudom megbecsülni / nem értelmezett", "0": "0", "1": "1", "2": "2", "3": "3", "4": "4", "5_plus": "Legalább 5" }} onChange={(v) => patch({ rir: v as Observation["rir"] })} />
          <Choice label="Kivitelezés" value={blank.technique} options={{ unknown: "Még nincs megadva", stable: "Végig stabil", uncertain: "Bizonytalan", breakdown: "Romlott / szétesett" }} onChange={(v) => patch({ technique: v as Observation["technique"] })} />
          <Choice label="Panasz a próba közben" value={blank.symptoms} options={{ unknown: "Még nincs megadva", none: "Panaszmentes", discomfort: "Kellemetlenség", pain: "Fájdalom" }} onChange={(v) => patch({ symptoms: v as Observation["symptoms"] })} />
          <Choice label="Miért fejezted be a próbát?" value={blank.stop_reason ?? "unknown"} options={stopLabels} onChange={(v) => patch({ stop_reason: v as Observation["stop_reason"] })} />
          <IntegerField label="Tényleges pihenő a próba előtt (másodperc) · ha ismert" value={blank.actual_rest_seconds ?? null} max={86400} onChange={(v) => patch({ actual_rest_seconds: v })} />
          {protocol.exercise_id === "slam" && <details><summary>Valóban mért szenzoradat · választható</summary><Field label="Mért mutató neve" value={blank.metric_name ?? ""} maxLength={200} onChange={(e) => patch({ metric_name: e.target.value })} /><Field label="Mértékegység" value={blank.metric_unit ?? ""} maxLength={200} onChange={(e) => patch({ metric_unit: e.target.value })} /><DecimalField label="Mért érték" value={blank.metric_value ?? null} onChange={(v) => patch({ metric_value: v })} /></details>}
          <button type="button" className={buttonClass} onClick={() => {
            const value = { ...blank, performed_confirmed: true };
            const observations = row.observations.some((s) => s.id === value.id) ? row.observations.map((s) => s.id === value.id ? value : s) : [...row.observations, value];
            onSave({ ...row, state: "recorded", observations });
          }}>Elvégzett próba rögzítése és mentése</button>
          <button type="button" className={secondaryClass} onClick={() => onChange({ ...row, state: actuals.length ? "recorded" : "pending", observations: row.observations.filter((s) => s.id !== blank.id) })}>Piszkozatpróba elvetése</button>
        </div>
      </article> : <>
        <button type="button" className={secondaryClass} disabled={row.observations.length >= 20} onClick={() => {
          const last = row.observations.at(-1)!;
          const next = newMeasurement(protocol, today, 1 + Math.max(0, ...row.observations.filter((s) => s.side === last.side).map((s) => s.trial_number ?? 0)), mode);
          Object.assign(next, { side: last.side, setup_note: last.setup_note, load_kind: last.load_kind, load_basis: last.load_basis });
          onChange({ ...row, observations: [...row.observations, next] });
        }}>Új elvégzett próba adatainak felvétele</button>
        <p className="pt-options-meta">A felmérési kártya határozza meg, indokolt-e új próba. A már elvégzett többletadat is megőrizhető.</p>
      </>}
      <Rest seconds={targetRest} onActual={(v) => {
        if (blank) patch({ actual_rest_seconds: v });
        else {
          const last = row.observations.at(-1)!;
          const next = newMeasurement(protocol, today, 1 + Math.max(0, ...row.observations.filter((s) => s.side === last.side).map((s) => s.trial_number ?? 0)), mode);
          Object.assign(next, { side: last.side, setup_note: last.setup_note, load_kind: last.load_kind, load_basis: last.load_basis, actual_rest_seconds: v });
          onChange({ ...row, observations: [...row.observations, next] });
        }
      }} />
    </section>
  </>;
}
