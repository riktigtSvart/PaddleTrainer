import type {StrengthWorkoutDose} from "@/lib/planning-cycles/strength-workout";
import Link from "next/link";
import type {WorkoutInstructions} from "@/lib/planning-cycles/workout-instructions";
import type {SetRecord} from "@/lib/initial-assessment/contracts";
import type {StrengthMovement} from "@/lib/planning-cycles/strength-assessment";
import { durationHMS as time } from '@/lib/duration';
const number=(v:string|null)=>v===null?"—":Number(v).toLocaleString("hu-HU",{maximumFractionDigits:6});
function load(row:SetRecord,plateComponents=false) {
  if(row.load_kind==="bodyweight")return "Saját testsúly";
  if(row.load_kind==="band")return row.load_note||"Rögzített gumiszalag";
  const basis:Record<string,string>={total:"összesen",per_hand:"kézenként",machine_display:"gép kijelzése",assistance:"rásegítés"};
  return `${number(row.load_value)} ${row.load_kind==="machine_level"?"fokozat":"kg"} · ${plateComponents?"felrakott tárcsák össztömege":basis[row.load_basis]??"rögzített terhelés"}`;
}
const reserve=(rir:string)=>rir==="5_plus"?"Legalább 5 ismétlés":rir==="unknown"?"Nincs mérve":`${rir} ismétlés`;
function setSummary(movement:StrengthMovement) {
  const amounts=movement.sets.map(s=>s.repetitions===null?`${number(s.hold_seconds)} mp tartás`:`${s.repetitions} ismétlés`);
  return new Set(amounts).size===1?`${amounts.length} × ${amounts[0]}`:`${amounts.length} sorozat: ${amounts.join("; ")}`;
}
export default function WorkoutInstructionDetails({value}:{value:WorkoutInstructions}) {
  const raw=value.main.strength,dose=raw?.schema_version==="assessed-strength-dose-v0.1"?raw:null,workout=raw?.schema_version==="strength-workout-dose-v0.1"?raw:null,intro=value.main.introductory_strength;
  return <section className="pt-workout-instructions" aria-label="Részletes edzésutasítás">
    <h3>Edzés lépésről lépésre · {time(value.duration_sec)}</h3>
    <p className="pt-options-meta">A bemelegítés és levezetés az edzés teljes idejének része. Az átmozgató sor általános minta; az ismeretlen vagy panaszt okozó mozdulatot hagyd ki.</p>
    <section className="pt-data-panel"><h4>1. Bemelegítés és gimnasztika · {time(value.warmup.duration_sec)}</h4><p>{value.warmup.purpose}</p><ol>{value.warmup.steps.map(s=><li key={s.name}><strong>{s.name} · {time(s.duration_sec)}</strong><p>{s.instruction}</p></li>)}</ol></section>
    <section className="pt-data-panel"><h4>2. Főrész · {time(value.main.duration_sec)}</h4>
      {workout?<IndependentStrength dose={workout}/>:dose?<><p>{dose.calibration_derivations?.length?"A mentett felmérésből levezetett kezdő sorozatok.":"A mentett saját sorozataid alapján."} A felsorolt ismétlésszám felső cél; korábban is állj meg, ha a szabályos végrehajtás vagy a legalább {dose.minimum_rir} ismétlésnyi tartalék nem tartható.</p>
        <div aria-label="Előírt munkasorozatok"><h4>Előírt munkasorozatok · összesen {dose.movements.reduce((sum,m)=>sum+m.sets.length,0)} sorozat</h4><ul>{dose.movements.map(m=><li key={m.entry_id}><strong>{m.label}: {setSummary(m)}</strong></li>)}</ul><p>A sorozatszám rögzített. A megmaradó idő miatt ne adj hozzá új sorozatot; az edzésidőt nem kell kitölteni.</p></div>
        <div className="pt-cycle-table-scroll"><table className="pt-cycle-table"><thead><tr><th>Gyakorlat</th><th>Sorozat</th><th>Ismétlés / tartás</th><th>Terhelés</th><th>Tartalék a referenciában</th><th>Pihenő</th></tr></thead><tbody>{dose.movements.flatMap(m=>m.sets.map((s,i)=>{
          const derivation=dose.calibration_derivations?.find(d=>d.entry_id===m.entry_id);
          return <tr key={`${m.entry_id}:${s.id}`}><th scope="row">{m.label}<small>{m.side==="both"?"Kétoldali":m.side==="left"?"Bal oldal":m.side==="right"?"Jobb oldal":"Váltott oldal"}</small></th><td>{i+1}. / {m.sets.length}</td><td>{s.repetitions??`${number(s.hold_seconds)} mp`}</td><td>{load(s,derivation?.load_kind==="machine_plate_components")}</td><td>{reserve(derivation?.source_rir??s.rir)}</td><td>{time(dose.rest_seconds)}</td></tr>;
        }))}</tbody></table></div>
        {!!dose.calibration_derivations?.length&&<p>A táblázat a felmérésből levezetett, csökkentett ismétlésszámot mutatja. A referencia tartaléka a mért sorozathoz tartozik; az új kezdősorozat tényleges tartaléka még nincs megmérve. Végrehajtás közben legalább {dose.minimum_rir} szabályos ismétlésnyi tartalék maradjon.</p>}
        {dose.movements.map(m=><p key={m.entry_id} className="pt-options-meta">{m.label} · referencia: {m.performed_on}{m.machine_note?` · Gép/beállítás: ${m.machine_note}`:""}</p>)}
        <p>A tartalék azt jelenti, hány további szabályos ismétlés menne még. A sorozat végét a technika és a tartalék határozza meg; ne dolgozz kifáradásig. A pihenőt az idő kitöltése érdekében se rövidítsd.</p><Link href="/strength-assessment">Saját erőreferenciák és felmérőalkalom →</Link>
      </>:intro?<><p>Bevezető, külső súly nélküli gyakorlás. Gyakorlatonként {intro.sets_per_movement} sorozat, legfeljebb {intro.max_repetitions} könnyű ismétlés.</p><ul>{intro.movements.map(m=><li key={m.key}><strong>{m.label}</strong><p>{m.instruction}</p></li>)}</ul><p>A gyakorlatok között 1–2 perc pihenő. Az időkeretet nem kell kitölteni.</p><Link href="/strength-assessment">Ismert terhelések és tényleges ismétlések rögzítése →</Link></>:<><p className="pt-options-meta">A sportági utasítás az egész edzést írja le. Az abban szereplő bemelegítést és levezetést a külön jelzett szakaszok tartalmazzák; ezeket egyszer végezd el.</p><p>{value.main.instruction}</p></>}
    </section>
    <section className="pt-data-panel"><h4>3. Levezetés · {time(value.finish.duration_sec)}</h4><p>{value.finish.instruction}</p><details><summary>Választható nyújtó gyakorlatsor · 2 perc a levezetésen belül</summary><p>{value.finish.purpose} A sor nem igazol regenerációs hatást.</p><ol>{value.finish.stretches.map(s=><li key={s.key}><strong>{s.name} · {time(s.duration_sec)}</strong><p>{s.instruction}</p></li>)}</ol></details></section>
    <p className="pt-notice">{value.stop_rule}</p>
  </section>;
}

function IndependentStrength({dose:d}:{dose:StrengthWorkoutDose}){
 const basis={literature_starting_rule:"Általános kezdőszabály",observed_workout:"Saját edzésnapló",feedback_reduced:"Visszajelzés / bizonytalan végrehajtás miatt csökkentett"};
 return <><p><strong>Előírt munkasorozatok · összesen {d.movements.reduce((s,m)=>s+m.work_sets,0)} sorozat</strong></p><p>A referencia a terhelést és az ismétléscélt adja. A munkasorozatok száma külön tervezett adag; a felmérés egyetlen sorozata nem egyetlen sorozatnyi edzéskapacitást jelent.</p>
 <div className="pt-cycle-table-scroll"><table className="pt-cycle-table"><thead><tr><th>Gyakorlat</th><th>Munkasorozatok</th><th>Terhelés</th><th>Előírt tartalék</th><th>Pihenő</th><th>A sorozatszám alapja</th></tr></thead><tbody>{d.movements.map(m=><tr key={m.entry_id}><th scope="row">{m.label}<small>{m.role==="main"?"Főgyakorlat":"Kiegészítő"} · {m.side==="both"?"kétoldali":m.side==="left"?"bal oldal":m.side==="right"?"jobb oldal":"váltott oldal"}</small></th><td>{m.work_sets} × {m.target.repetitions??`${number(m.target.hold_seconds)} mp tartás`}</td><td>{load(m.reference_set,m.calibration_derivation?.load_kind==="machine_plate_components")}</td><td>{m.target.hold_seconds!==null?"Kényelmes tartás, kifáradás nélkül":"Legalább 3 szabályos ismétlés"}</td><td>{time(m.rest_seconds)}</td><td>{basis[m.volume_basis]}{m.observed_work_sets!==null?<small>{m.observed_work_sets} használható sorozat a legutóbbi naplóban</small>:null}</td></tr>)}</tbody></table></div>
 {d.shortened_for_time&&<p role="status">Rövidített edzés: az eredeti {time(d.desired_duration_sec)} helyett {time(d.duration_sec)} fér el. Először a kiegészítők, majd munkasorozatok maradtak ki; a pihenő nem rövidült.</p>}
 <p>Becsült munkavégzés, teljes pihenők és eszközváltások: {time(d.work_seconds)}. A fennmaradó idő ráhagyás; nem további sorozat.</p>
 {d.movements.length===2&&!d.omitted_accessory_ids.length&&<p>Kiegészítő csak saját, használható gyakorlati referenciával kerül be. Más gyakorlat súlyát nem visszük át; új kiegészítő saját edzésnaplóból is megismerhető, külön felmérés nélkül.</p>}
 {d.movements.map(m=><p className="pt-options-meta" key={m.entry_id}>{m.label} · {m.reference.kind==="workout_log"?"edzésnapló":"felmérési referencia"}: {m.performed_on}{m.machine_note?` · Gép/beállítás: ${m.machine_note}`:""}</p>)}
 <p>Az ismétlésszám felső cél. Állj meg korábban, ha a legalább 3 ismétlésnyi tartalék vagy a szabályos technika nem tartható. A rávezető sorozatok ezen felül, a bemelegítési időben vannak. A megmaradt idő miatt ne adj hozzá munkasorozatot.</p><Link href="/coach">Tényleges gyakorlatok naplózása a teljesített edzés adatlapján →</Link>
 </>;
}
