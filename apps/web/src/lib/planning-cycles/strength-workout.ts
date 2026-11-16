import { canonical, object } from "./contracts";
import { evaluateStrength, usableSets } from "./strength-assessment";
import type { StrengthEvidence, StrengthMovement } from "./strength-assessment";
import { availableExercises } from "@/lib/training-options/strength-catalog";
import { receipt } from "@/lib/session-analysis/strength-log";
import type { StrengthLogReceipt } from "@/lib/session-analysis/strength-log";
import { artifact as readFeedback } from "@/lib/session-analysis/feedback";
import type { Artifact as FeedbackArtifact } from "@/lib/session-analysis/feedback";
import type { SetRecord, Ref } from "@/lib/initial-assessment/contracts";
import type { StarterTarget } from "@/lib/guided-strength/calibration";
type Row = Record<string, unknown>;
export type WorkoutContext = {
    schema_version: "strength-workout-context-v0.1";
    athlete_id: string;
    logs: {
        log: StrengthLogReceipt;
        feedback: {
            artifact: FeedbackArtifact;
            durable_available_at: string;
        }[];
    }[];
};
type Entry = StrengthMovement & {
    source: Ref & {
        kind: "assessment" | "workout_log";
    };
    observed_work_sets: number | null;
    feedback_reduced: boolean;
    calibration_derivation?: StarterTarget["derivation"];
};
export type WorkMovement = Omit<StrengthMovement, "sets"> & {
    role: "main" | "accessory";
    reference: Entry["source"] & {
        set_id: string;
    };
    reference_set: SetRecord;
    target: Pick<SetRecord, "repetitions" | "hold_seconds" | "load_kind" | "load_value" | "load_basis" | "load_note">;
    work_sets: number;
    volume_basis: "feedback_reduced" | "observed_workout" | "literature_starting_rule";
    observed_work_sets: number | null;
    minimum_rir: 3;
    rest_seconds: number;
    execution_seconds_per_set: number;
    calibration_derivation: StarterTarget["derivation"] | null;
};
export type StrengthWorkoutDose = {
    schema_version: "strength-workout-dose-v0.1";
    rules_version: "strength-workout-policy-v0.1";
    assessment_reference: Ref;
    movements: WorkMovement[];
    duration_sec: number;
    desired_duration_sec: number;
    warmup_seconds: number;
    cooldown_seconds: 300;
    work_seconds: number;
    shortened_for_time: boolean;
    omitted_accessory_ids: string[];
    minimum_rir: 3;
    max_pattern_sets: 7;
    rest_between_sets_preserved: true;
    load_increased: false;
    one_rm_estimated: false;
    personal_response_model_applied: false;
    source_url: string;
};
const check = (v: unknown) => { if (!v)
    throw Error("Az erősítő munkamennyiség vagy naplóforrás nem ellenőrizhető."); };
export const strengthWorkSource = "https://pmc.ncbi.nlm.nih.gov/articles/PMC12965823/";
export async function validateWorkoutContext(review: Row) {
    const inputs = object(review.inputs), v = object(inputs.strength_workout_context);
    check(v.schema_version === "strength-workout-context-v0.1" && v.athlete_id === review.athlete_id && Array.isArray(v.logs));
    const cutoff = Date.parse(String(inputs.captured_at)), seen = new Set<string>(), recent = (inputs.recent_sessions as unknown[]).map(object);
    const guided = object(inputs.strength_assessment).guided_activities as {
        artifact: {
            workout_session_id?: string;
        };
    }[];
    for (const raw of v.logs as unknown[]) {
        const item = object(raw), r = await receipt(item.log, String(review.athlete_id)), a = r.artifact, s = recent.find(s => s.id === a.session_id);
        check(!seen.has(a.session_id) && a.proposal.purpose === "training" && s && s.sport === "STRENGTH" && !s.reference_occasion && !(guided ?? []).some(g => g.artifact.workout_session_id === a.session_id) && Date.parse(a.submitted_at) <= cutoff && Date.parse(r.durable_available_at) <= cutoff);
        check(canonical(a.session) === canonical(Object.fromEntries(["id", "sport", "started_at", "ended_at", "duration_sec"].map(k => [k, s![k]]))));
        const strength = object(inputs.strength_assessment) as unknown as StrengthEvidence;
        check(a.proposal.exercises.every(e => strength.receipt?.artifact.snapshot.registry.patterns.find(p => p.key === e.pattern)?.exercise_ids.includes(e.exercise_id!)));
        seen.add(a.session_id);
        check(Array.isArray(item.feedback));
        const timings = new Set<string>();
        for (const raw of item.feedback as unknown[]) {
            const f = object(raw), a = await readFeedback(f.artifact, String(review.athlete_id), r.artifact.session_id);
            check(!timings.has(a.proposal.timing) && Date.parse(a.submitted_at) <= Date.parse(String(f.durable_available_at)) && Date.parse(String(f.durable_available_at)) <= cutoff && Date.parse(a.proposal.observed_at) <= Date.parse(a.submitted_at) && Date.parse(a.proposal.observed_at) >= Date.parse(r.artifact.session.ended_at!));
            timings.add(a.proposal.timing);
        }
    }
}
const patterns = ["pull", "push", "knee", "hip", "core"], vertical = new Set(["pullup", "lat_pulldown", "chinup", "assisted_pullup"]);
export function selectWorkout(context: StrengthEvidence, inputs: Row, day: string, location: string, resources: string[]) {
    const evaluated = evaluateStrength(context, inputs, day, location, resources), a = context.receipt!.artifact;
    check(!evaluated.issues.length);
    const place = a.snapshot.locations.find(p => p.id === location), catalog = a.snapshot.catalog, available = new Set(place ? availableExercises(catalog, place, resources).map(e => e.id) : []), pool = new Map<string, Entry>(), key = (e: {
        exercise_id: string | null;
        side: string;
    }) => `${e.exercise_id}:${e.side}`;
    for (const e of evaluated.entries)
        if (e.eligible)
            pool.set(key(e), { ...structuredClone(e), source: { kind: "assessment", artifact_id: a.artifact_id, content_hash: a.content_hash }, observed_work_sets: null, feedback_reduced: false });
    const preferred = new Set(pool.keys());
    const logs = [...(inputs.strength_workout_context as WorkoutContext).logs].sort((a, b) => a.log.artifact.session.started_at.localeCompare(b.log.artifact.session.started_at) || a.log.artifact.artifact_id.localeCompare(b.log.artifact.artifact_id));
    for (const record of logs) {
        const a = record.log.artifact;
        if (a.proposal.purpose !== "training")
            continue;
        const reduced = record.feedback.some(({ artifact: { proposal: f } }) => (f.rpe !== null && f.rpe >= 9) || (f.fatigue !== null && f.fatigue >= 7) || (f.soreness !== null && f.soreness >= 7) || (f.recovery !== null && f.recovery <= 3));
        for (const e of a.proposal.exercises) {
            const age = (Date.parse(day) - Date.parse(e.performed_on!)) / 86400000;
            if (e.location_id !== location || age < 0 || age > 56 || !available.has(e.exercise_id!))
                continue;
            const k = key(e);
            if (pool.has(k) && e.performed_on! < pool.get(k)!.performed_on!)
                continue;
            if (["symptoms", "avoid"].includes(e.comfort) || e.sets.some(s => ["pain", "discomfort"].includes(s.symptoms) || s.technique === "breakdown")) {
                for (const [old,value] of pool) if(value.exercise_id===e.exercise_id) pool.delete(old);
                continue;
            }
            const all = e.sets.filter(s => usableSets({ ...e, sets: [s] }).length), safe = all.slice(0, 1);
            if (!["independent", "regular"].includes(e.familiarity) || e.comfort !== "none" || !safe.length) {
                const old = pool.get(k);
                if (old)
                    old.feedback_reduced = true;
                continue;
            }
            const signature = (s: SetRecord) => canonical([s.load_kind, s.load_value === null ? null : Number(s.load_value), s.load_basis, s.load_note]), matching = all.filter(s => signature(s) === signature(safe[0]) && (s.repetitions === null) === (safe[0].repetitions === null)), reference = [...matching].sort((a, b) => Number(a.repetitions ?? a.hold_seconds) - Number(b.repetitions ?? b.hold_seconds))[0];
            pool.set(k, { entry_id: e.id, exercise_id: e.exercise_id, label: catalog.exercises.find(x => x.id === e.exercise_id)!.label, pattern: e.pattern, location_id: location, performed_on: e.performed_on, side: e.side, machine_note: e.machine_note, sets: [structuredClone(reference)], source: { kind: "workout_log", artifact_id: a.artifact_id, content_hash: a.content_hash }, observed_work_sets: matching.length, feedback_reduced: reduced || all.length !== e.sets.length });
        }
    }
    const offset = (Math.floor(Date.parse(day + "T00:00:00Z") / 86400000) + 719163) % patterns.length, priority = [...patterns.slice(offset), ...patterns.slice(0, offset)];
    const ordered = [...pool.values()].sort((a, b) => priority.indexOf(a.pattern) - priority.indexOf(b.pattern) || Number(!preferred.has(key(a))) - Number(!preferred.has(key(b))) || String(b.performed_on).localeCompare(String(a.performed_on)) || String(a.exercise_id).localeCompare(String(b.exercise_id)) || a.entry_id.localeCompare(b.entry_id)), mains: Entry[] = [], used = new Set<string>();
    for (const e of ordered) {
        if (!used.has(e.pattern)) {
            mains.push(e);
            used.add(e.pattern);
        }
        if (mains.length === 2)
            break;
    }
    check(mains.length === 2);
    const accessories: Entry[] = [];
    for (const main of mains) {
        const candidates = ordered.filter(e => ![...mains, ...accessories].some(m => key(m) === key(e)) && e.pattern === main.pattern);
        candidates.sort((a, b) => Number(vertical.has(a.exercise_id!) === vertical.has(main.exercise_id!)) - Number(vertical.has(b.exercise_id!) === vertical.has(main.exercise_id!)) || String(a.exercise_id).localeCompare(String(b.exercise_id)));
        if (candidates.length)
            accessories.push(candidates[0]);
    }
    return [...mains, ...accessories].map(entry => ({ entry, role: (mains.includes(entry) ? "main" : "accessory") as "main" | "accessory" }));
}
export function workSeconds(m: WorkMovement[]) { const count = m.reduce((s, m) => s + m.work_sets, 0); return m.reduce((s, m) => s + m.execution_seconds_per_set * m.work_sets, 0) + Math.max(0, count - 1) * Math.max(120, ...m.map(m => m.rest_seconds)) + Math.max(0, m.length - 1) * 60; }
export function workoutDose(context: StrengthEvidence, chosen: ReturnType<typeof selectWorkout>, cap: number): StrengthWorkoutDose | null {
    const regular = context.receipt!.artifact.proposal.data.experience === "regular", movements: WorkMovement[] = chosen.map(({ entry: e, role }) => {
        const s = e.sets[0];
        let count = role === "main" ? (e.observed_work_sets !== null && e.observed_work_sets >= 2 ? Math.min(5, Math.max(2, e.observed_work_sets)) : regular ? 3 : 2) : 2;
        if (e.feedback_reduced)
            count = Math.max(1, count - 1);
        return { entry_id: e.entry_id, exercise_id: e.exercise_id, label: e.label, pattern: e.pattern, location_id: e.location_id, performed_on: e.performed_on, side: e.side, machine_note: e.machine_note, role, reference: { ...e.source, set_id: s.id }, reference_set: structuredClone(s), target: { repetitions: s.repetitions, hold_seconds: s.hold_seconds, load_kind: s.load_kind, load_value: s.load_value, load_basis: s.load_basis, load_note: s.load_note }, work_sets: count, volume_basis: e.feedback_reduced ? "feedback_reduced" : e.observed_work_sets !== null && e.observed_work_sets >= 2 && role === "main" ? "observed_workout" : "literature_starting_rule", observed_work_sets: e.observed_work_sets, minimum_rir: 3, rest_seconds: e.calibration_derivation ? 180 : 120, execution_seconds_per_set: Math.max(45, Math.trunc(Number(s.hold_seconds ?? 0)) * (e.side === "alternating" ? 2 : 1)), calibration_derivation: e.calibration_derivation ?? null };
    });
    const duration = () => { const warm = movements.reduce((s, m) => s + m.work_sets, 0) >= 6 ? 600 : 300; return { seconds: Math.ceil((warm + workSeconds(movements) + 300) / 300) * 300, warm }; }, desired = duration().seconds, omitted: string[] = [];
    while (duration().seconds > cap && movements.some(m => m.role === "accessory"))
        omitted.push(movements.pop()!.exercise_id!);
    while (duration().seconds > cap && movements.some(m => m.work_sets > 1)) {
        const m = [...movements].reverse().sort((a, b) => b.work_sets - a.work_sets)[0];
        m.work_sets--;
    }
    const { seconds, warm } = duration();
    if (seconds > cap)
        return null;
    return { schema_version: "strength-workout-dose-v0.1", rules_version: "strength-workout-policy-v0.1", assessment_reference: { artifact_id: context.receipt!.artifact.artifact_id, content_hash: context.receipt!.artifact.content_hash }, movements, duration_sec: Math.max(1200, seconds), desired_duration_sec: Math.max(1200, desired), warmup_seconds: warm, cooldown_seconds: 300, work_seconds: workSeconds(movements), shortened_for_time: seconds < desired, omitted_accessory_ids: omitted, minimum_rir: 3, max_pattern_sets: 7, rest_between_sets_preserved: true, load_increased: false, one_rm_estimated: false, personal_response_model_applied: false, source_url: strengthWorkSource };
}
export function workoutPresentation(d: StrengthWorkoutDose) {
    const text = (m: WorkMovement) => { const t = m.target, reps = t.repetitions !== null ? `${t.repetitions} ismétlés` : `${t.hold_seconds} mp tartás`, bases: Record<string, string> = { total: "összesen", per_hand: "kézenként", machine_display: "gép kijelzése", assistance: "rásegítés", not_applicable: "", unknown: "" }, basis = m.calibration_derivation?.load_kind === "machine_plate_components" ? "felrakott tárcsák össztömege" : bases[t.load_basis], load = t.load_kind === "bodyweight" ? "saját testsúly" : t.load_kind === "band" ? t.load_note : `${t.load_value} ${t.load_kind === "machine_level" ? "fokozat" : "kg"} · ${basis}`; return `${m.label}: ${m.work_sets} × ${reps}, ${load}` + (m.machine_note ? `. Gép/beállítás: ${m.machine_note}` : ""); };
    let description = `${d.warmup_seconds / 60} perc bemelegítés és ismert, könnyű rávezetés. ` + d.movements.map(text).join(" | ") + ". A sorozatok között a táblázat szerinti teljes pihenő; legalább 3 szabályos ismétlés maradjon tartalékban. A terhelés saját referencia, a sorozatszám külön tervezett munkamennyiség. Az ismétlésszám felső cél, nem kifáradásig végzett teszt. Romló technika vagy panasz esetén állj meg. 5 perc levezetés. A megmaradt idő miatt ne adj hozzá sorozatot; nincs automatikus súlyemelés.";
    if (d.shortened_for_time)
        description += " Az időkeret miatt rövidített edzés: először a kiegészítők, majd munkasorozatok maradtak ki; a pihenő nem rövidült.";
    return { title: `Erőfejlesztés · ${d.duration_sec / 60} perc`, description, names: ["Bemelegítés és rávezető mozgások", "Főgyakorlatok és saját referenciájú kiegészítők", "Levezetés és edzésnapló"] };
}
export async function validateWorkoutCandidate(review: Row, context: StrengthEvidence, c: Row, metadata: unknown) {
    check(object(object(review.result).policy).version === "training-plan-policy-v0.15");
    const inputs = object(review.inputs), day = (inputs.days as Row[]).find(d => d.date === c.date), group = (day?.opportunities as Row[]).find(g => g.key === c.opportunity_key), constraints = object(group?.constraints);
    check(c.sport === "STRENGTH" && c.template_key === "STRENGTH_REFERENCE_AND_DEVELOPMENT" && ["MAX_STRENGTH", "MUSCULOSKELETAL_ROBUSTNESS"].includes(String(c.capability_key)) && c.location_id === constraints.location_id && c.location === constraints.location && ["moderate", "any"].includes(String(constraints.effort_cap)) && (constraints.sport_scope === "any" || (constraints.sports as string[]).some(s => ["strength", "kondi", "erősítés", "erőnlét", "erőedzés"].includes(s.toLocaleLowerCase("hu")))));
    const dose = workoutDose(context, selectWorkout(context, inputs, String(c.date), String(c.location_id), constraints.resources as string[]), Number(c.duration_sec));
    check(dose && canonical(c.strength_prescription) === canonical(dose));
    if (!dose)
        return;
    const p = workoutPresentation(dose);
    check(c.template_version === "v0.5" && c.title === p.title && c.description === p.description && Number(c.duration_sec) >= 1200 && Number(c.duration_sec) <= 4500 && Number(c.duration_sec) % 300 === 0 && Number(c.duration_sec) <= Number(group!.max_minutes) * 60 && (day!.daily_max_minutes === null || Number(c.duration_sec) <= Number(day!.daily_max_minutes) * 60) && (group!.intervals as Row[]).some(i => Date.parse(String(i.start_at)) <= Date.parse(String(c.start_at)) && Date.parse(String(c.end_at)) <= Date.parse(String(i.end_at))));
    // The cycle's duration-history reference is frozen by the backend. Current
    // opportunities, assessments and work logs above still govern eligibility
    // and the dose; importing a new workout cannot rewrite this old reference.
    const referenceInputs = object(review.calibration_review ? object(review.calibration_review).inputs : review.inputs);
    const cutoff = Date.parse(String(referenceInputs.captured_at)), refs = (referenceInputs.recent_sessions as Row[]).filter(s => s.sport === "STRENGTH" && !s.reference_occasion && s.ended_at && Date.parse(String(s.ended_at)) <= cutoff && Date.parse(String(s.started_at)) <= Date.parse(String(s.ended_at)) && Number(s.duration_sec) > 0 && Number.isSafeInteger(s.duration_sec) && Number(s.duration_sec) * 1000 <= Date.parse(String(s.ended_at)) - Date.parse(String(s.started_at))).sort((a, b) => String(b.started_at).localeCompare(String(a.started_at)) || String(b.id).localeCompare(String(a.id))).slice(0, 3), cap = refs.length ? Math.min(...refs.map(s => Number(s.duration_sec))) : null;
    const expected = { schema_version: "training-prescription-v0.6", family_key: c.template_key, duration_sec: c.duration_sec, minimum_seconds: 1200, maximum_seconds: 4500, reference_session_ids: refs.map(s => s.id), reference_cap_seconds: cap, assessment_duration_minutes: context.receipt!.artifact.proposal.data.usual_strength_minutes, product_default_used: dose.movements.some(m => m.volume_basis === "literature_starting_rule"), soft_duration_reduced: dose.shortened_for_time, progression_applied: false, personal_response_model_applied: false, intensity_basis: "own_reference_independent_volume", strength: dose };
    check(canonical(metadata) === canonical(expected) && c.duration_reference_session_id === (refs.find(s => s.duration_sec === cap)?.id ?? null));
    check(Array.isArray(c.blocks) && c.blocks.length === 3);
    (c.blocks as Row[]).forEach((b, i) => check(b.position === i + 1 && b.name === p.names[i] && b.block_type === ["WARMUP", "WORK", "COOLDOWN"][i] && b.duration_sec === [dose.warmup_seconds, dose.duration_sec - dose.warmup_seconds - 300, 300][i] && ["distance_m", "intensity_type", "intensity_min", "intensity_max", "repeat_count", "parent_block_id"].every(k => b[k] === null)));
}
