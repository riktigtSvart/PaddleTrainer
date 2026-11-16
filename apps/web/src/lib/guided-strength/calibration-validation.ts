import { requireValue as check } from "@/lib/initial-assessment/contracts";
import { calibrationStopped, dynamicFamilies } from "./calibration";
import type { SelectedProtocols } from "./calibration";
import type { Command } from "./contracts";

export function validateCalibrationProgress(c: Command, snapshot: SelectedProtocols, start: string, end: string, zone: string) {
  const localDay = (v: string) => new Intl.DateTimeFormat("sv-SE", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(v));
  const low = localDay(start), high = localDay(end), ids = new Set<string>();
  check(c.protocol_hash === snapshot.protocol_hash);
  if (["finish", "apply"].includes(c.action)) check(c.progress.results.every((r) => r.observations.every((v) => v.performed_confirmed)));
  check(c.progress.phase === "warmup" || c.progress.warmup_completed || calibrationStopped(c.progress));
  for (const row of c.progress.results) {
    const p = snapshot.entries.find((v) => v.entry_id === row.entry_id)?.protocol;
    check(p && p.scope !== "sport_route");
    if (c.measurement_mode === "repeatability") check(dynamicFamilies.has(p!.family));
    for (const v of row.observations) {
      check(!ids.has(v.id) && low <= v.performed_on && v.performed_on <= high);
      ids.add(v.id);
      const purpose = c.measurement_mode === "repeatability" ? "repeatability" : dynamicFamilies.has(p!.family) || ["timed_hold", "carry"].includes(p!.family) ? "calibration" : "quality";
      check(v.purpose === purpose && (v.load_value === null || Number(v.load_value) <= 100000));
      if (p!.family === "timed_hold") check([v.repetitions, v.duration_seconds, v.distance_m, v.measured_height_m].every((n) => n === null));
      if (p!.family === "carry") check([v.repetitions, v.hold_seconds, v.measured_height_m].every((n) => n === null));
      if (dynamicFamilies.has(p!.family) || ["controlled_repetitions", "ballistic_short_set"].includes(p!.family))
        check([v.hold_seconds, v.duration_seconds, v.distance_m, v.measured_height_m].every((n) => n === null));
      if (p!.family === "explosive_single_attempts") {
        check(v.hold_seconds === null && v.duration_seconds === null);
        if (p!.exercise_id !== "jump_squat") check(v.measured_height_m === null);
        if (!["rotational_throw", "forward_throw"].includes(p!.exercise_id)) check(v.distance_m === null);
      }
    }
    if (row.state === "recorded") check(row.observations.some((v) => v.performed_confirmed));
  }
}
