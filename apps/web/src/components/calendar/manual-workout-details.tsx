import type { ManualDraft } from "@/lib/calendar/manual-workouts";
import { phaseLabels, manualPhaseSeconds } from "@/lib/calendar/manual-workouts";
import { formatDuration } from "@/lib/calendar/contracts";

export default function ManualWorkoutDetails({ value }: { value: ManualDraft }) {
  return <section className="pt-data-panel pt-manual-details"><h3>Saját edzésterv</h3>
    {value.location && <p>Helyszín: {value.location}</p>}
    {value.intensity_type && <p>Intenzitás: {value.intensity_type}</p>}
    {value.phases.length > 0 && <><h4>Edzésszakaszok</h4><ol>{value.phases.map((p, i) => <li key={i}><strong>{p.name}</strong> · {phaseLabels[p.block_type]}{p.repeat_count > 1 && ` · ${p.repeat_count} ×`}{p.duration_sec !== null && ` · ${formatDuration(p.duration_sec)}`}{p.distance_m !== null && ` · ${p.distance_m} m`}{p.recovery_duration_sec != null && <p>Pihenő az ismétlések között: {formatDuration(p.recovery_duration_sec)} · {Math.max(0, p.repeat_count - 1)} pihenő. Az utolsó ismétlés után nincs külön pihenő.{p.duration_sec !== null && ` Összesen: ${formatDuration(manualPhaseSeconds(p))}.`}</p>}{p.intensity_type && <p>{p.intensity_type}{p.intensity_min != null && ` · ${p.intensity_min}`}{p.intensity_max != null && ` – ${p.intensity_max}`}</p>}{p.notes && <p>{p.notes}</p>}</li>)}</ol></>}
    {value.exercises.length > 0 && <><h4>Előírt munkasorozatok · összesen {value.exercises.reduce((n, e) => n + e.sets, 0)} sorozat</h4><div className="pt-manual-table"><table><thead><tr><th>Gyakorlat</th><th>Munkasorozatok</th><th>Terhelés</th><th>Pihenő</th><th>Tartalék</th></tr></thead><tbody>{value.exercises.map((e, i) => <tr key={i}><td><strong>{e.name}</strong>{e.notes && <p>{e.notes}</p>}</td><td>{e.sets} × {e.reps !== null ? `${e.reps} ismétlés` : `${formatDuration(e.hold_seconds)} tartás`}</td><td>{e.load_mode === "kg" ? `${e.weight_kg} kg · ${e.load_basis === "per_hand" ? "kézenként" : "összesen"}` : e.load_mode === "bodyweight" ? "Saját testsúly" : "Külön terhelés nélkül"}</td><td>{formatDuration(e.rest_seconds)}</td><td>{e.reserve_reps === null ? "Nincs megadva" : `${e.reserve_reps} ismétlés`}</td></tr>)}</tbody></table></div></>}
  </section>;
}
