"use client";
import PerformanceFields from "./performance-fields";
import { changePerformanceProtocol } from "@/lib/athlete-setup/sport-history";
import type { SportHistory } from "@/lib/athlete-setup/contracts";
import { emptySportPlanning, trainingPurposes } from "@/lib/athlete-setup/sport-history";
import type { SportPerformance, SportPlanning } from "@/lib/athlete-setup/sport-history";
import { Field, Select, secondaryClass } from "@/components/planning-goals/fields";

export default function SportContext({ value, change, primarySports, today }: {
  value: SportHistory; change: (patch: Partial<SportHistory>) => void; primarySports: string[]; today: string;
}) {
  const planning = value.planning ?? emptySportPlanning(), results = value.performances ?? [];
  const edit = (patch: Partial<SportPlanning>) => change({ planning: { ...planning, ...patch } });
  const result = (id: string, patch: SportPerformance) => change({ performances: results.map((row) => row.result_id === id ? patch as SportPerformance : row) });
  return <div className="pt-sport-context space-y-4">
    {value.role === "secondary" && <fieldset className="space-y-4">
      <legend className="font-semibold">Szerepe a felkészülésben</legend>
      <p className="pt-options-meta">Add meg, melyik fő sportod felkészülését támogatja, és mit szeretnél vele fejleszteni.</p>
      {primarySports.length ? <div className="space-y-2"><p className="text-sm">Támogatott fő sportágak</p>{primarySports.map((sport) => <label key={sport} className="flex gap-2 text-sm"><input type="checkbox" checked={planning.supported_sports.includes(sport)} onChange={(e) => edit({ supported_sports: e.target.checked ? [...planning.supported_sports, sport] : planning.supported_sports.filter((v) => v !== sport) })} />{sport}</label>)}</div> : <p className="pt-options-meta">A kapcsolat megadásához előbb nevezd meg a fő sportodat.</p>}
      {planning.supported_sports.filter((v) => !primarySports.includes(v)).map((sport) => <p key={sport} className="pt-options-meta">Korábban megadott kapcsolat: {sport} <button type="button" className="underline" onClick={() => edit({ supported_sports: planning.supported_sports.filter((v) => v !== sport) })}>Kapcsolat törlése</button></p>)}
      <div className="grid gap-2 sm:grid-cols-2">{Object.entries(trainingPurposes).map(([key, title]) => <label key={key} className="flex gap-2 text-sm"><input type="checkbox" checked={planning.purposes.includes(key as keyof typeof trainingPurposes)} onChange={(e) => edit({ purposes: e.target.checked ? [...planning.purposes, key as keyof typeof trainingPurposes] : planning.purposes.filter((v) => v !== key) })} />{title}</label>)}</div>
    </fieldset>}
    {["secondary", "recreation"].includes(value.role ?? "") && <>
      {value.role === "recreation" && <p className="pt-options-meta">Kedvelt, szabadidős mozgás. Felvétele nem kapcsolja be a felkészülési programba.</p>}
      <Select label="Gyakorlati jártasság ebben a mozgásformában" value={planning.proficiency} onChange={(e) => edit({ proficiency: e.target.value as SportPlanning["proficiency"] })}>
        <option value="unknown">Még nincs megadva</option><option value="learning">Még tanulom / segítséggel végzem</option><option value="independent">Önállóan, biztonsággal végzem</option><option value="experienced">Rutinos vagyok, több változatát is ismerem</option>
      </Select>
      {["úszás", "uszas", "swimming", "swim"].includes(value.sport.split("/")[0].trim().toLocaleLowerCase("hu")) && ["independent", "experienced"].includes(planning.proficiency) && <p className="pt-options-meta">A tervező az itt elmentett önálló/rutinos úszástudást is felhasználja a könnyű úszóedzéshez. Az úszásnemet és a kényelmes folyamatos távot vagy időt opcionálisan pontosíthatod a „Jelenlegi edzésmennyiség és úszási kiindulópont” részben.</p>}
    </>}
    <details className="pt-sport-results" open={results.length ? true : undefined}>
      <summary>Sporteredmények · {results.length ? `${results.length} megadva` : "egyéni csúcsok és friss eredmények, opcionális"}</summary>
      <p className="pt-options-meta">Az eredmény az adott sporthoz és szakághoz tartozik. A korábbi csúcs tájékozódási pont; az aktuális terheléshez a friss felmérési és edzésadatok szükségesek. A dátum ismeretlenül is hagyható.</p>
      {results.map((row, i) => <fieldset key={row.result_id} className="pt-result-card grid gap-3 sm:grid-cols-2">
        <legend className="font-medium">{i + 1}. eredmény</legend>
        <Select label="Az eredmény jellege" value={row.kind} onChange={(e) => result(row.result_id, { ...row, kind: e.target.value as SportPerformance["kind"] })}><option value="personal_best">Korábbi egyéni legjobb</option><option value="recent">Friss teljesítmény</option></Select>
        <PerformanceFields value={row} change={value => result(row.result_id, value)} />
        <Field label="Eredmény dátuma (ha ismert)" type="date" max={today} value={row.recorded_on ?? ""} onChange={(e) => result(row.result_id, { ...row, recorded_on: e.target.value || null, year: null })} />
        <Field label="Év (ha a pontos nap nem ismert)" type="number" min={1900} max={Number(today.slice(0, 4))} disabled={!!row.recorded_on} value={row.year ?? ""} onChange={(e) => result(row.result_id, { ...row, year: e.target.value === "" ? null : Number(e.target.value) })} />
        <Select label="Az eredmény forrása" value={row.source} onChange={(e) => result(row.result_id, { ...row, source: e.target.value as SportPerformance["source"] })}><option value="self_report">Saját adat / visszaemlékezés</option><option value="official">Hivatalos eredmény</option><option value="device">Eszközzel rögzített eredmény</option></Select>
        <Field label="Változat és körülmények (opcionális)" maxLength={200} placeholder="Például K1, állóvíz; 25 m-es medence; sík út" value={row.conditions} onChange={(e) => result(row.result_id, { ...row, conditions: e.target.value })} />
        <button className={secondaryClass} type="button" onClick={() => change({ performances: results.filter((v) => v.result_id !== row.result_id) })}>Eredmény törlése</button>
      </fieldset>)}
      <button className={secondaryClass} type="button" disabled={results.length >= 16} onClick={() => change({ performances: [...results, { result_id: crypto.randomUUID(), kind: "personal_best", distance_m: "", time: "", recorded_on: null, year: null, conditions: "", source: "self_report" }] })}>Időeredmény hozzáadása</button>
      <button className={secondaryClass} type="button" disabled={results.length >= 16} onClick={() => change({ performances: [...results, changePerformanceProtocol({result_id: crypto.randomUUID(), kind: "personal_best", recorded_on: null, year: null, conditions: "", source: "self_report"}, "repetitions")] })}>Erő- vagy ismétléseredmény hozzáadása</button>
    </details>
  </div>;
}
