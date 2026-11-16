"use client";
import type { SportPerformance, PerformanceProtocol } from "@/lib/athlete-setup/sport-history";
import { changePerformanceProtocol, performanceProtocols } from "@/lib/athlete-setup/sport-history";
import { Field, Select } from "@/components/planning-goals/fields";
export default function PerformanceFields({value: row, change}: {value: SportPerformance; change: (value: SportPerformance) => void}) {
  const protocol = row.protocol ?? "distance_time", distance = ["distance_time", "cooper_12min"].includes(protocol);
  const edit = (patch: Partial<SportPerformance>) => change(Object.fromEntries(Object.entries({...row, ...patch}).filter(([, value]) => value !== undefined)) as SportPerformance);
  return <>
    <Select label="Eredmény típusa" value={protocol} onChange={e => change(changePerformanceProtocol(row, e.target.value as PerformanceProtocol))}>{Object.entries(performanceProtocols).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</Select>
    {distance ? <>
      <Field label={protocol === "cooper_12min" ? "12 perc alatt megtett táv (méter)" : "Táv (méter)"} inputMode="decimal" required value={row.distance_m ?? ""} onChange={e => edit({distance_m: e.target.value})} />
      <Field label={protocol === "cooper_12min" ? "Cooper-teszt időtartama" : "Időeredmény (p:ss vagy ó:pp:ss)"} placeholder="Például 1:42,500" readOnly={protocol === "cooper_12min"} required maxLength={24} value={row.time ?? ""} onChange={e => edit({time: e.target.value})} />
      {protocol === "cooper_12min" && <p className="pt-options-meta sm:col-span-2">Az idő rögzített 12:00; a teljesített távolságot add meg. A tárolt eredményt a rendszer nem alakítja át laboratóriumi VO₂max-méréssé.</p>}
    </> : <>
      <Field label="Gyakorlat neve és változata" required maxLength={200} placeholder="Például fekvenyomás rúddal; szigorú húzódzkodás" value={row.exercise ?? ""} onChange={e => edit({exercise: e.target.value})} />
      <Field label={protocol === "strength_1rm" ? "Teljesített ismétlés · rögzített 1RM" : "Szabályosan teljesített ismétlések"} type="number" min={protocol === "strength_1rm" ? 1 : 0} max={100000} step={1} required readOnly={protocol === "strength_1rm"} value={row.repetitions ?? ""} onChange={e => edit({repetitions: e.target.value === "" ? undefined : Number(e.target.value)})} />
      {protocol === "timed_repetitions" && <Field label="Próba időtartama (p:ss vagy ó:pp:ss)" placeholder="Például 1:00" required maxLength={24} value={row.time ?? ""} onChange={e => edit({time: e.target.value})} />}
      <Select label="A terhelés típusa" value={row.load_kind ?? "bodyweight"} onChange={e => edit(e.target.value === "bodyweight" ? {load_kind: "bodyweight", load_kg: undefined, load_basis: undefined} : {load_kind: "external_kg", load_kg: "", load_basis: "total_external"})}>
        {protocol !== "strength_1rm" && <option value="bodyweight">Saját testsúly · hozzáadott külső súly nélkül</option>}
        <option value="external_kg">Külső súly vagy hozzáadott súly (kg)</option>
      </Select>
      {row.load_kind === "external_kg" && <>
        <Field label={protocol === "strength_1rm" ? "Teljesített maximális súly (kg)" : "A próbában használt külső súly (kg)"} required inputMode="decimal" value={row.load_kg ?? ""} onChange={e => edit({load_kg: e.target.value})} />
        <Select label="A kilogramm értelmezése" value={row.load_basis ?? "total_external"} onChange={e => edit({load_basis: e.target.value as SportPerformance["load_basis"]})}><option value="total_external">Teljes külső súly · rúddal és tárcsákkal együtt</option><option value="per_hand">Kézenkénti súly</option><option value="additional_to_bodyweight">Saját testsúlyhoz hozzáadott súly</option><option value="machine_display">A gépen jelzett kilogramm</option></Select>
      </>}
      <p className="pt-options-meta sm:col-span-2">Korábban már teljesített eredményt rögzíts. A korábbi csúcs tájékozódási adat; a friss erőfelmérő sorozatoknál külön szerepel a tartalék, a kivitelezés és a panasz is.</p>
    </>}
  </>;
}
