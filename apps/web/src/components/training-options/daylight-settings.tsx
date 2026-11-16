"use client";
import { useState } from "react";
import { Field, Select, buttonClass, secondaryClass } from "@/components/planning-goals/fields";
import { sportLabels } from "@/lib/training-options/contracts";
import type { OptionsData, Sport } from "@/lib/training-options/contracts";
import { decimalCoordinate, lightModeLabels, readCoordinates, readDaylightRules } from "@/lib/training-options/daylight-rules";
import type { Coordinates, DaylightRule, LightMode } from "@/lib/training-options/daylight-rules";
import { loadDaylightPreview } from "@/lib/training-options/daylight";
import type { DaylightPreview, SolarDay } from "@/lib/training-options/daylight";
import { lightIntervals } from "@/lib/training-options/solar";

export function RuleFields({ rules, sports, defaults, onChange, disabled }: { rules: DaylightRule[]; sports: Sport[]; defaults?: DaylightRule[]; onChange: (rules: DaylightRule[]) => void; disabled: boolean }) {
  function change(sport: Sport, mode: string) {
    const other = rules.filter(r => r.sport !== sport), current = rules.find(r => r.sport === sport);
    onChange(mode === "inherit" ? other : [...other, { sport, mode: mode as LightMode, start_buffer_minutes: mode === "none" ? 0 : current?.start_buffer_minutes ?? 0, end_buffer_minutes: mode === "none" ? 0 : current?.end_buffer_minutes ?? 0 }]);
  }
  return <fieldset disabled={disabled} className="pt-options-form">
    {sports.map(sport => {
      const rule = rules.find(r => r.sport === sport), inherited = defaults?.find(r => r.sport === sport);
      return <div key={sport} className="pt-options-columns">
        <Select label={`${sportLabels[sport]} · napfény`} value={rule?.mode ?? (defaults ? "inherit" : "none")} onChange={e => change(sport, e.target.value)}>
          {defaults && <option value="inherit">Sportági alapbeállítás: {lightModeLabels[inherited?.mode ?? "none"]}</option>}
          {Object.entries(lightModeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </Select>
        {rule && rule.mode !== "none" && <>
          <Field label={`${sportLabels[sport]} · reggeli időráhagyás (perc)`} type="number" min={0} max={120} step={1} value={Number.isFinite(rule.start_buffer_minutes) ? rule.start_buffer_minutes : ""} onChange={e => onChange(rules.map(r => r.sport === sport ? { ...r, start_buffer_minutes: e.target.value === "" ? NaN : Number(e.target.value) } : r))} />
          <Field label={`${sportLabels[sport]} · esti időráhagyás (perc)`} type="number" min={0} max={120} step={1} value={Number.isFinite(rule.end_buffer_minutes) ? rule.end_buffer_minutes : ""} onChange={e => onChange(rules.map(r => r.sport === sport ? { ...r, end_buffer_minutes: e.target.value === "" ? NaN : Number(e.target.value) } : r))} />
        </>}
      </div>;
    })}
  </fieldset>;
}
export default function DaylightSettings({ data, disabled, save }: { data: OptionsData; disabled: boolean; save: (v: OptionsData) => Promise<boolean> }) {
  const [rules, setRules] = useState(data.daylight_rules ?? []), [message, setMessage] = useState("");
  return <details className="pt-panel"><summary>Sportági napfénykorlátok · {rules.filter(r => r.mode !== "none").length} aktív szabály</summary><form className="pt-options-form" aria-label="Sportági napfénykorlátok" onSubmit={async e => {
    e.preventDefault();
    try { readDaylightRules(rules); if (await save({ ...data, daylight_rules: rules })) setMessage("A sportági napfénykorlátok mentve. A terv frissítése már ezeket alkalmazza."); }
    catch (e) { setMessage(e instanceof Error ? e.message : "A korlátok hibásak."); }
  }}>
    <h3>Sportági napfénykorlátok</h3>
    <p>A teljes edzésnek a kijelölt világos időszakba kell férnie. A reggeli ráhagyás késlelteti a legkorábbi kezdést, az esti előrébb hozza a befejezést. Helyszínenként eltérő szabály is megadható, például beltéri edzéshez.</p>
    <RuleFields rules={rules} sports={Object.keys(sportLabels) as Sport[]} disabled={disabled} onChange={v => { setRules(v); setMessage(""); }} />
    <div className="pt-options-actions"><button className={buttonClass} disabled={disabled}>Napfénykorlátok mentése</button></div>
    {message && <p role="status">{message}</p>}
  </form></details>;
}
export function CoordinatesEditor({ value, defaultZone, owner, today, disabled, onChange, rules }: { value?: Coordinates; defaultZone: string; owner: string; today: string; disabled: boolean; onChange: (v?: Coordinates) => void; rules: DaylightRule[] }) {
  const point = value ?? { latitude: "", longitude: "", timezone_name: defaultZone };
  const normalizedPoint = { ...point, latitude: decimalCoordinate(point.latitude), longitude: decimalCoordinate(point.longitude) };
  const [date, setDate] = useState(today), [busy, setBusy] = useState(false), [failure, setFailure] = useState("");
  const [result, setResult] = useState<{ key: string; value: DaylightPreview } | null>(null);
  const key = JSON.stringify({ date, coordinates: normalizedPoint });
  const preview = result?.key === key ? result.value : null;
  const clock = (instant: string | number) => new Intl.DateTimeFormat("hu", { timeZone: point.timezone_name, hour: "2-digit", minute: "2-digit" }).format(new Date(typeof instant === "number" ? instant * 1000 : instant));
  const times = (d: SolarDay, side: "rises_at" | "sets_at") => d.state === "all_day" ? "Egész nap világos" : d.state === "no_light" ? "Nincs ilyen világos időszak" : d[side].length ? d[side].map(clock).join(", ") : "Ezen a helyi napon nincs átmenet";
  return <fieldset className="pt-options-form" disabled={disabled}>
    <legend>Földrajzi hely és napfény</legend>
    <p>A koordináták a napfény számításához és később az időjáráshoz használhatók. A pontos helyet térképen vagy tizedes fokban add meg. Változó helyszínhez fent edzési körzetet is választhatsz.</p>
    <div className="pt-options-columns">
      <Field label="Földrajzi szélesség (−90 … 90°)" inputMode="decimal" placeholder="47.500000" value={point.latitude} onChange={e => onChange({ ...point, latitude: e.target.value })} />
      <Field label="Földrajzi hosszúság (−180 … 180°)" inputMode="decimal" placeholder="19.040000" value={point.longitude} onChange={e => onChange({ ...point, longitude: e.target.value })} />
      <Field label="Helyszín időzónája (IANA)" placeholder="Europe/Budapest" value={point.timezone_name} onChange={e => onChange({ ...point, timezone_name: e.target.value })} />
      <Field label="Napfény ellenőrzésének dátuma" type="date" min="1900-01-01" max="2100-12-31" value={date} onChange={e => setDate(e.target.value)} />
    </div>
    <div className="pt-options-actions">
      <button type="button" className={secondaryClass} disabled={busy} onClick={async () => {
        setBusy(true); setFailure("");
        try { const request = JSON.parse(key); readCoordinates(request.coordinates); setResult({ key, value: await loadDaylightPreview(owner, request) }); }
        catch (e) { setFailure(e instanceof Error ? e.message : "A napfényadatok nem olvashatók."); }
        finally { setBusy(false); }
      }}>{busy ? "Számítás…" : "Napfényidők ellenőrzése"}</button>
      {value && <button type="button" className={secondaryClass} onClick={() => { onChange(undefined); setResult(null); }}>Koordináták törlése</button>}
    </div>
    {failure && <p role="alert">{failure}</p>}
    {preview && <div aria-live="polite">
      <p>{date} · {point.timezone_name}</p>
      <dl className="pt-options-columns">
        <div><dt>Polgári hajnal</dt><dd>{times(preview.civil_twilight, "rises_at")}</dd></div>
        <div><dt>Napkelte</dt><dd>{times(preview.daylight, "rises_at")}</dd></div>
        <div><dt>Napnyugta</dt><dd>{times(preview.daylight, "sets_at")}</dd></div>
        <div><dt>Polgári alkonyat vége</dt><dd>{times(preview.civil_twilight, "sets_at")}</dd></div>
      </dl>
      {rules.filter(r => r.mode !== "none").map(r => <p key={r.sport}>{sportLabels[r.sport]} · megengedett időszak a ráhagyással: {lightIntervals(Date.parse(preview.day_start_at) / 1000, Date.parse(preview.day_end_at) / 1000, normalizedPoint, r).map(([a, b]) => `${clock(a)}–${clock(b)}`).join(", ") || "Nincs megengedett időszak ezen a napon."}</p>)}
    </div>}
    <small>Számított időpontok sík horizontra. A terep, a felhőzet és a tényleges látási viszonyok ettől eltérhetnek. A koordináták mentése önmagában nem kapcsol be napfénykorlátot.</small>
  </fieldset>;
}
