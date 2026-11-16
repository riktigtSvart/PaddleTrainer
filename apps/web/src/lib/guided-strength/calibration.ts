import rawBank from "./calibration-protocols-v0_3_1.json";
import legacyBank from "./calibration-protocols-v0_3.json";
import { canonical, sha } from "@/lib/planning-cycles/contracts";
import { newSet, requireValue as check } from "@/lib/initial-assessment/contracts";
import type { Data, SetRecord } from "@/lib/initial-assessment/contracts";
import type { Command, Observation, Progress, Receipt } from "./contracts";

export const protocolVersion = "strength-calibration-v0.3";
export const calibrationSchema = "guided-strength-session-v0.2";
export const calibrationRules = "guided-strength-calibration-v0.3";
export type Protocol = (typeof rawBank.entries)[number];
type BankSource = Omit<typeof rawBank, "repeatability"> & {
  repeatability: typeof legacyBank.repeatability & { bodyweight_steps?: string[] };
};
export type ProtocolBank = BankSource & { content_hash: string };
export type SelectedProtocols = {
  schema_version: "selected-calibration-protocols-v0.1";
  protocol_version: typeof protocolVersion;
  protocol_hash: string;
  measurement_mode: "calibration" | "repeatability";
  entries: { entry_id: string; protocol: Protocol }[];
  content_hash: string;
};
export const dynamicFamilies = new Set([
  "weighted_repetitions", "bodyweight_repetitions", "assisted_repetitions", "band_repetitions",
]);
const banksPromise: Promise<ProtocolBank[]> = Promise.all([rawBank, legacyBank].map(async (bank) => ({ ...bank, content_hash: await sha(bank) })));
export async function readProtocolBank(value: unknown): Promise<ProtocolBank> {
  const known = await banksPromise;
  check(known.some((bank) => canonical(value) === canonical(bank)));
  return value as ProtocolBank;
}
export function protocolFor(id: string | null | undefined, bank: BankSource = rawBank): Protocol | undefined {
  return bank.entries.find((v) => v.exercise_id === id);
}
export function forMeasurementMode(protocol: Protocol, mode: Command["measurement_mode"] = "calibration", bank: BankSource = rawBank): Protocol {
  const repeated = bank.repeatability;
  const steps = protocol.family === "bodyweight_repetitions" ? repeated.bodyweight_steps ?? repeated.steps : repeated.steps;
  return mode === "repeatability" ? { ...protocol, steps,
    planned_measurement: { ...protocol.planned_measurement, ...repeated.planned_measurement } } as Protocol : protocol;
}
export function displayedProtocol(protocol: Protocol, mode: Command["measurement_mode"] = "calibration"): Protocol {
  // Correct misleading bodyweight wording even for an already-started occasion.
  // The original signed snapshot remains untouched and still verifies on read.
  if (protocol.family !== "bodyweight_repetitions") return protocol;
  const current = protocolFor(protocol.exercise_id);
  if (!current) return protocol;
  return { ...protocol, steps: forMeasurementMode(current, mode).steps };
}
export async function selectedProtocols(data: Data, ids: string[], mode: "calibration" | "repeatability" = "calibration", contentHash?: string): Promise<SelectedProtocols> {
  const known = await banksPromise;
  const bank = contentHash === undefined ? known[0] : known.find((v) => v.content_hash === contentHash);
  check(bank);
  const body = {
    schema_version: "selected-calibration-protocols-v0.1" as const,
    protocol_version: protocolVersion as typeof protocolVersion,
    protocol_hash: bank!.content_hash,
    measurement_mode: mode,
    entries: ids.map((entry_id) => ({ entry_id, protocol: forMeasurementMode(protocolFor(data.exercises.find((e) => e.id === entry_id)?.exercise_id, bank)!, mode, bank) })),
  };
  check(body.entries.every((v) => v.protocol));
  return { ...body, content_hash: await sha(body) };
}
export function isCalibration(p: Progress) { return p.protocol_version === protocolVersion; }
export function calibrationStopped(p: Progress) {
  return p.results.some((r) => r.observations.some((s) => s.performed_confirmed && (
    ["pain", "discomfort"].includes(s.symptoms) || s.technique === "breakdown" ||
    ["symptom", "technique_limit"].includes(s.stop_reason ?? ""))));
}
export const setFields = ["id", "repetitions", "hold_seconds", "load_kind", "load_value", "load_basis", "load_note", "rir", "technique", "symptoms"] as const;
export const measurementFields = ["purpose", "performed_on", "performed_confirmed", "trial_number", "side", "stop_reason", "actual_rest_seconds", "setup_note", "duration_seconds", "distance_m", "measured_height_m", "metric_name", "metric_unit", "metric_value", "plate_configuration", "left_plates_kg", "right_plates_kg", "shared_plates_kg", "bar_kg"] as const;
export const measurementDecimals = ["duration_seconds", "distance_m", "measured_height_m", "metric_value", "left_plates_kg", "right_plates_kg", "shared_plates_kg", "bar_kg"] as const;
export function actualSet(s: Observation): SetRecord {
  return Object.fromEntries(setFields.map((key) => [key, s[key]])) as SetRecord;
}
export const stopLabels = {
  unknown: "Még nincs megadva", planned_cap: "Elértem a tervezett darabszámot / időt / távot",
  reserve_target: "Elértem a választott tartalékot", effort_limit: "Az erőkifejtés miatt fejeztem be",
  technique_limit: "Romlott a kivitelezés", symptom: "Panasz jelentkezett",
  external_interruption: "Külső ok miatt szakítottam meg", measurement_error: "Mérési vagy számolási hiba",
};
export function newMeasurement(protocol: Protocol, today: string, trial = 1, mode: Command["measurement_mode"] = "calibration"): Observation {
  const load_kind: SetRecord["load_kind"] = protocol.load_kind.includes("bodyweight") || protocol.load_kind === "leverage_variant" ? "bodyweight" :
    protocol.load_kind === "band_setup" ? "band" : protocol.load_kind === "assistance_display" ? "assistance_kg" :
    protocol.load_kind === "machine_display" ? "machine_level" : "external_kg";
  const load_basis: SetRecord["load_basis"] = load_kind === "bodyweight" ? "not_applicable" : load_kind === "band" ? "not_applicable" :
    load_kind === "assistance_kg" ? "assistance" : load_kind === "machine_level" ? "machine_display" :
    protocol.load_kind === "dumbbell_per_hand_kg" ? "per_hand" : "total";
  return {
    ...newSet(), purpose: mode === "repeatability" ? "repeatability" : dynamicFamilies.has(protocol.family) || ["timed_hold", "carry"].includes(protocol.family) ? "calibration" : "quality",
    performed_on: today, performed_confirmed: false, trial_number: trial,
    side: protocol.side === "together" ? "both" : "unknown",
    stop_reason: "unknown", actual_rest_seconds: null, setup_note: "",
    duration_seconds: null, distance_m: null, measured_height_m: null,
    metric_name: "", metric_unit: "", metric_value: null,
    plate_configuration: protocol.load_kind === "machine_plate_components" ? "unknown" : "not_applicable",
    left_plates_kg: null, right_plates_kg: null, shared_plates_kg: null, bar_kg: null,
    load_kind, load_basis,
  };
}
export function validateMeasurement(s: Record<string, unknown>) {
  check(Object.keys(s).sort().join("|") === [...setFields, ...measurementFields].sort().join("|"));
  check(["calibration", "quality", "repeatability"].includes(String(s.purpose)) &&
    typeof s.performed_confirmed === "boolean" && Number.isInteger(s.trial_number) && Number(s.trial_number) >= 1 && Number(s.trial_number) <= 100 &&
    ["unknown", "both", "left", "right", "alternating"].includes(String(s.side)) &&
    Object.hasOwn(stopLabels, String(s.stop_reason)) &&
    (s.actual_rest_seconds === null || Number.isInteger(s.actual_rest_seconds) && Number(s.actual_rest_seconds) >= 0 && Number(s.actual_rest_seconds) <= 86400) &&
    typeof s.setup_note === "string" && s.setup_note.length <= 200 &&
    typeof s.metric_name === "string" && s.metric_name.length <= 200 && typeof s.metric_unit === "string" && s.metric_unit.length <= 200 &&
    ["not_applicable", "unknown", "shared", "paired"].includes(String(s.plate_configuration)));
  for (const key of measurementDecimals) check(s[key] === null || typeof s[key] === "string" && /^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?$/.test(s[key]));
  check(s.metric_value === null || String(s.metric_name).trim() && String(s.metric_unit).trim());
  check(s.plate_configuration !== "shared" || s.left_plates_kg === null && s.right_plates_kg === null);
  check(s.plate_configuration !== "paired" || s.shared_plates_kg === null);
}

// UUIDv5 is used only for stable row identities, never as a security hash.
export function groupIdentity(value: string): string {
  const ns = "6ba7b8119dad11d180b400c04fd430c8f";
  const prefix = Uint8Array.from(ns.match(/../g)!.map((v) => parseInt(v, 16)));
  const input = new TextEncoder().encode(value), bytes = new Uint8Array(prefix.length + input.length);
  bytes.set(prefix); bytes.set(input, prefix.length);
  const length = Math.ceil((bytes.length + 9) / 64) * 64, block = new Uint8Array(length);
  block.set(bytes); block[bytes.length] = 128;
  const view = new DataView(block.buffer); view.setUint32(length - 4, bytes.length * 8);
  const h = [0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0], w = new Int32Array(80);
  const rot = (v: number, n: number) => v << n | v >>> (32 - n);
  for (let offset = 0; offset < length; offset += 64) {
    for (let i = 0; i < 16; i++) w[i] = view.getInt32(offset + i * 4);
    for (let i = 16; i < 80; i++) w[i] = rot(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
    let [a, b, c, d, e] = h;
    for (let i = 0; i < 80; i++) {
      const f = i < 20 ? (b & c) | (~b & d) : i < 40 ? b ^ c ^ d : i < 60 ? b & c | b & d | c & d : b ^ c ^ d;
      const k = i < 20 ? 0x5a827999 : i < 40 ? 0x6ed9eba1 : i < 60 ? 0x8f1bbcdc : 0xca62c1d6;
      const next = rot(a, 5) + f + e + k + w[i] | 0;
      e = d; d = c; c = rot(b, 30); b = a; a = next;
    }
    [a, b, c, d, e].forEach((v, i) => { h[i] = h[i] + v | 0; });
  }
  const out = new Uint8Array(20), outView = new DataView(out.buffer);
  h.forEach((v, i) => outView.setInt32(i * 4, v)); out[6] = out[6] & 15 | 80; out[8] = out[8] & 63 | 128;
  const hex = [...out.slice(0, 16)].map((v) => v.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
export function projectCalibration(original: Data, p: Progress, today: string): Data {
  const data = structuredClone(original), dates: string[] = [];
  data.assessment_date = today;
  for (const row of p.results) {
    const source = data.exercises.find((v) => v.id === row.entry_id)!;
    const groups = new Map<string, { date: string; side: Observation["side"]; setup: string; sets: SetRecord[] }>();
    for (const v of row.observations) {
      if (!v.performed_confirmed) continue;
      dates.push(v.performed_on);
      if (["pain", "discomfort"].includes(v.symptoms)) source.comfort = "symptoms";
      if (!["calibration", "repeatability"].includes(v.purpose) || v.repetitions === null && v.hold_seconds === null) continue;
      const setup = v.setup_note || row.machine_note;
      const key = JSON.stringify([v.performed_on, v.side, setup]);
      if (!groups.has(key)) groups.set(key, { date: v.performed_on, side: v.side, setup, sets: [] });
      groups.get(key)!.sets.push(actualSet(v));
    }
    let index = 0;
    for (const group of groups.values()) {
      const target = index === 0 ? source : structuredClone(source);
      if (index++) {
        target.id = groupIdentity(`${row.entry_id}:${group.date}:${group.side}:${group.setup}`);
        const old = data.exercises.findIndex((v) => v.id === target.id);
        if (old < 0) data.exercises.push(target); else data.exercises[old] = target;
      }
      Object.assign(target, { performed_on: group.date, side: group.side, machine_note: group.setup, sets: group.sets });
    }
  }
  if (calibrationStopped(p)) data.state_change = "changed";
  if (dates.length) data.last_strength_date = dates.sort().at(-1)!;
  data.references_reviewed = data.reviewed = true;
  return data;
}
export type StarterTarget = {
  entry_id: string; source_entry_id: string; exercise_id: string | null; location_id: string | null;
  performed_on: string | null; side: Data["exercises"][number]["side"]; machine_note: string;
  actual_sets: SetRecord[]; sets: SetRecord[]; derivation: {
    rules_version: "calibration-starter-v0.1"; guided_reference: { artifact_id: string; content_hash: string };
    observation_id: string; source_repetitions: number; planned_repetitions: number; source_rir: SetRecord["rir"];
    load_kind: string; planned_minimum_rir: 3; personal_capacity_estimated: false; one_rm_estimated: false;
  };
};
const million = BigInt(1000000);
const decimalUnits = (v: string) => { const [whole, fraction = ""] = v.split("."); return BigInt(whole) * million + BigInt(fraction.padEnd(6, "0")); };
export function plateTotal(values: (string | null | undefined)[]): string | null {
  if (!values.length || values.some((v) => v == null || !/^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?$/.test(v))) return null;
  const n = values.reduce<bigint>((sum, v) => sum + decimalUnits(v!), BigInt(0));
  return `${n / million}.${String(n % million).padStart(6, "0")}`.replace(/\.?0+$/, "");
}
export function starterTargets(receipt: Receipt): StarterTarget[] {
  const a = receipt.artifact, base = receipt.base ?? a;
  if (a.state !== "finished" || !a.result?.assessment_reference || a.result.stop_required) return [];
  const projected = projectCalibration(a.application_context!.data!, a.proposal.progress, a.application_context!.local_today);
  const result: StarterTarget[] = [];
  for (const row of a.proposal.progress.results) {
    const protocol = base.measurement_protocols!.entries.find((v) => v.entry_id === row.entry_id)!.protocol;
    if (!dynamicFamilies.has(protocol.family) || ["landmine_components", "variant_dependent_load"].includes(protocol.load_kind)) continue;
    const source = base.intake_context!.data!.exercises.find((v) => v.id === row.entry_id)!;
    for (const entry of projected.exercises) {
      if (entry.exercise_id !== source.exercise_id || entry.location_id !== source.location_id) continue;
      const measured = row.observations.filter((v) => v.performed_confirmed && entry.sets.some((s) => s.id === v.id) && v.repetitions !== null && v.repetitions >= 4 &&
        ["2", "3", "4", "5_plus"].includes(v.rir) && v.technique === "stable" && v.symptoms === "none" && v.side !== "unknown" &&
        (["each_side", "alternating_sides"].includes(protocol.side) ? ["left", "right"].includes(v.side ?? "") : v.side === "both") &&
        ["planned_cap", "reserve_target", "effort_limit"].includes(v.stop_reason ?? "")).at(-1);
      if (!measured) continue;
      const load = measured.load_kind === "bodyweight" || measured.load_kind === "band" && !!measured.load_note.trim() || measured.load_value !== null && measured.load_basis !== "unknown";
      if (!load || ["machine_display", "machine_plate_components", "assistance_display"].includes(protocol.load_kind) && !entry.machine_note.trim()) continue;
      if (protocol.load_kind === "machine_plate_components") {
        const parts = measured.plate_configuration === "shared" ? [measured.shared_plates_kg] : measured.plate_configuration === "paired" ? [measured.left_plates_kg, measured.right_plates_kg] : [];
        const total = plateTotal(parts);
        if (total === null || measured.load_value === null || decimalUnits(total) !== decimalUnits(measured.load_value)) continue;
      }
      const planned = { ...actualSet(measured), repetitions: Math.min(8, measured.repetitions! - 2), rir: "unknown" as const };
      result.push({ entry_id: entry.id, source_entry_id: row.entry_id, exercise_id: entry.exercise_id, location_id: entry.location_id,
        performed_on: entry.performed_on, side: entry.side, machine_note: entry.machine_note,
        actual_sets: entry.sets, sets: [planned], derivation: {
          rules_version: "calibration-starter-v0.1", guided_reference: { artifact_id: a.artifact_id, content_hash: a.content_hash },
          observation_id: measured.id, source_repetitions: measured.repetitions!, planned_repetitions: planned.repetitions,
          source_rir: measured.rir, load_kind: protocol.load_kind, planned_minimum_rir: 3, personal_capacity_estimated: false, one_rm_estimated: false,
        } });
    }
  }
  return result;
}
