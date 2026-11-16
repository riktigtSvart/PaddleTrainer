import { canonical, object, sha } from "@/lib/planning-cycles/contracts";
import { readData, requireValue as check } from "@/lib/initial-assessment/contracts";
import type { Exercise, Registry } from "@/lib/initial-assessment/contracts";
import type { StrengthCatalog as Catalog } from "@/lib/training-options/strength-catalog";
import type { Location } from "@/lib/training-options/contracts";
export type StrengthLogProposal = {
    request_id: string;
    expected_revision: number;
    purpose: "training" | "assessment";
    exercises: Exercise[];
    note: string;
    confirmed_actual: true;
};
export type StrengthLogArtifact = {
    schema_version: "strength-workout-log-v0.1";
    artifact_id: string;
    athlete_id: string;
    session_id: string;
    session: {
        id: string;
        sport: string;
        started_at: string;
        ended_at: string | null;
        duration_sec: number | null;
    };
    timezone_name: string;
    proposal: StrengthLogProposal;
    revision: number;
    previous_hash: string | null;
    submitted_at: string;
    content_hash: string;
};
export type StrengthLogReceipt = {
    artifact: StrengthLogArtifact;
    durable_available_at: string;
};
export type StrengthLogContext = {
    schema_version: string;
    athlete_id: string;
    session_id: string;
    timezone_name: string;
    session: StrengthLogArtifact["session"];
    current: StrengthLogReceipt | null;
    catalog: Catalog;
    patterns: Registry["patterns"];
    locations: Location[];
};
export function proposal(raw: unknown): StrengthLogProposal {
    const p = object(raw);
    check(canonical(Object.keys(p).sort()) === canonical(["request_id", "expected_revision", "purpose", "exercises", "note", "confirmed_actual"].sort()));
    check(typeof p.request_id === "string" && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(p.request_id) && Number.isSafeInteger(p.expected_revision) && Number(p.expected_revision) >= 0 && ["training", "assessment"].includes(String(p.purpose)) && typeof p.note === "string" && p.note.length <= 2000 && p.confirmed_actual === true);
    check(Array.isArray(p.exercises) && p.exercises.length >= 1, "Adj hozzá legalább egy ténylegesen elvégzett gyakorlatot.");
    for (const [i, rawExercise] of (p.exercises as unknown[]).entries()) {
        const e = object(rawExercise);
        check(e.exercise_id && e.location_id && e.side !== "unknown", `${i + 1}. gyakorlat: válaszd ki a gyakorlatot, helyszínt és végrehajtási oldalt.`);
        check(Array.isArray(e.sets) && e.sets.length > 0, `${i + 1}. gyakorlat: adj hozzá elvégzett munkasorozatot.`);
        for (const [j, rawSet] of (e.sets as unknown[]).entries()) {
            const s = object(rawSet);
            check(s.repetitions !== null || s.hold_seconds !== null, `${i + 1}. gyakorlat, ${j + 1}. sorozat: add meg a tényleges ismétlést vagy tartásidőt.`);
            check(s.load_value === null || !["unknown", "bodyweight", "band"].includes(String(s.load_kind)), `${i + 1}. gyakorlat, ${j + 1}. sorozat: számszerű súlyhoz válassz külső súlyt, rásegítést vagy gépfokozatot.`);
        }
    }
    const exercises = readData({ timezone_name: "UTC", assessment_date: "2100-12-31", program_reference: null, goal_label: "", state_change: "unchanged", state_notes: "", experience: "unknown", strength_frequency: "unknown", last_strength_date: null, usual_strength_minutes: null, supervision: "unknown", default_location_id: null, sports: [], exercises: p.exercises, sport_references: [], references_reviewed: false, reviewed: false }).exercises;
    check(exercises.length >= 1 && exercises.length <= 16 && exercises.every(e => e.exercise_id && e.location_id && e.performed_on && e.side !== "unknown" && e.sets.length));
    check(exercises.every(e => e.sets.every(s => s.repetitions !== null || s.hold_seconds !== null)));
    return p as StrengthLogProposal;
}
export async function receipt(raw: unknown, owner: string): Promise<StrengthLogReceipt> {
    const r = object(raw), a = object(r.artifact), p = proposal(a.proposal), s = object(a.session);
    check(a.schema_version === "strength-workout-log-v0.1" && a.athlete_id === owner && s.id === a.session_id && s.sport === "STRENGTH" && typeof s.started_at === "string" && typeof s.ended_at === "string" && Date.parse(s.started_at) <= Date.parse(s.ended_at) && typeof a.submitted_at === "string" && Date.parse(s.ended_at) <= Date.parse(a.submitted_at) && typeof r.durable_available_at === "string" && Date.parse(a.submitted_at) <= Date.parse(r.durable_available_at));
    check(a.artifact_id === "pt-strength-workout:" + await sha({ athlete_id: owner, request_id: p.request_id }) && a.revision === p.expected_revision + 1 && (a.previous_hash === null || typeof a.previous_hash === "string" && /^[a-f0-9]{64}$/.test(a.previous_hash)));
    const { content_hash, ...body } = a;
    check(content_hash === await sha(body));
    const zone = String(a.timezone_name), day = new Intl.DateTimeFormat("sv-SE", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(s.started_at));
    check(p.exercises.every(e => e.performed_on === day));
    return r as unknown as StrengthLogReceipt;
}
const messages: Record<string, string> = { CALENDAR_STRENGTH_LOG_REVISION_CONFLICT: "Az edzésnapló közben változott. Töltsd újra, majd egyeztesd a módosításokat.", CALENDAR_STRENGTH_LOG_DAY_MISMATCH: "A gyakorlatok dátuma az edzés helyi napja legyen.", CALENDAR_STRENGTH_LOG_COMPLETED_REQUIRED: "Csak befejezett erősítő edzéshez menthető tényleges gyakorlatsor.", CALENDAR_STRENGTH_LOG_LOCATION_INVALID: "A helyszín nem található. Frissítsd a helyszínlistát.", CALENDAR_STRENGTH_LOG_EXERCISE_INVALID: "A gyakorlat nem illeszkedik a mozgásmintához.", CALENDAR_INPUT_INVALID: "Ellenőrizd a gyakorlatokat, ismétléseket és a terhelés jelentését." };
async function request(session: string, body?: string, signal?: AbortSignal) { const r = await fetch(`/api/calendar/sessions/${session}/strength-log`, { method: body ? "POST" : "GET", cache: "no-store", signal, headers: body ? { "Content-Type": "application/json" } : {}, body }); const v = await r.json(); if (!r.ok) {
    const code = object(object(v).detail).code;
    throw Error(messages[String(code)] ?? `Az edzésnapló nem menthető / tölthető (${String(code ?? r.status)}).`);
} return v; }
export async function loadLog(owner: string, session: string, signal?: AbortSignal): Promise<StrengthLogContext> { const v = object(await request(session, undefined, signal)); check(v.schema_version === "strength-workout-log-v0.1" && v.athlete_id === owner && v.session_id === session && object(v.session).id === session && Array.isArray(v.locations) && Array.isArray(v.patterns) && Array.isArray(object(v.catalog).exercises)); if (v.current) {
    const r = await receipt(v.current, owner);
    check(r.artifact.session_id === session);
} return v as unknown as StrengthLogContext; }
export async function saveLog(owner: string, session: string, body: string) { proposal(JSON.parse(body)); const v = object(await request(session, body)), r = await receipt({ artifact: v.artifact, durable_available_at: v.durable_available_at }, owner); check(v.committed === true && r.artifact.session_id === session && canonical(r.artifact.proposal) === canonical(JSON.parse(body))); return r; }
export const logKey = (owner: string, session: string) => `paddletrainer:strength-log:v1:${owner}:${session}`;
