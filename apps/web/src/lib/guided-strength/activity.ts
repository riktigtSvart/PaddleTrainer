import { canonical, object, sha } from "@/lib/planning-cycles/contracts";
import { requireValue as check } from "@/lib/initial-assessment/contracts";
import type { Ref } from "@/lib/initial-assessment/contracts";
export type ActivityReceipt = {
  artifact: {
    schema_version: "guided-strength-activity-v0.1" | "guided-strength-activity-v0.2";
    measurement_protocol_version?: "strength-calibration-v0.3";
    artifact_id: string;
    athlete_id: string;
    session_id: string;
    request_id: string;
    created_at: string;
    state: "active" | "finished" | "abandoned";
    guided_reference: Ref;
    previous_reference: Ref | null;
    workout_session_id: string | null;
    assessment_reference: Ref | null;
    stop_required: boolean;
    planning_authorized: false;
    clinical_clearance: false;
    content_hash: string;
  };
  committed: true;
  durable_available_at: string;
};
export const uuid = (v: unknown): v is string =>
  typeof v === "string" &&
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(v);
export const instant = (v: unknown): v is string =>
  typeof v === "string" &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(
    v,
  ) &&
  Number.isFinite(Date.parse(v));
export function elapsedWholeSeconds(first: string, last: string): number {
  const microseconds = (value: string) => {
    const fraction = /\.(\d{1,6})(?=Z|[+-]\d{2}:\d{2}$)/.exec(value)?.[1] ?? "";
    const whole = value.replace(/\.\d{1,6}(?=Z|[+-]\d{2}:\d{2}$)/, "");
    return BigInt(Date.parse(whole)) * BigInt(1000) + BigInt(fraction.padEnd(6, "0"));
  };
  return Number((microseconds(last) - microseconds(first)) / BigInt(1000000));
}
export const ref = (a: { artifact_id: string; content_hash: string }): Ref => ({
  artifact_id: a.artifact_id,
  content_hash: a.content_hash,
});
export const same = (a: unknown, b: unknown) => canonical(a) === canonical(b);
export function reference(v: unknown, prefix?: string): v is Ref {
  if (!v || typeof v !== "object" || Array.isArray(v)) return false;
  const r = object(v);
  return (
    Object.keys(r).length === 2 &&
    typeof r.artifact_id === "string" &&
    (!prefix || r.artifact_id.startsWith(prefix)) &&
    typeof r.content_hash === "string" &&
    /^[a-f0-9]{64}$/.test(r.content_hash)
  );
}
export async function readActivity(
  value: unknown,
  owner: string,
  cutoff?: string,
): Promise<ActivityReceipt> {
  const r = object(value),
    a = object(r.artifact),
    { content_hash, ...body } = a;
  const suffix = uuid(a.request_id) ? a.request_id.replaceAll("-", "") : "";
  check(
    r.committed === true &&
      instant(r.durable_available_at) &&
      a.schema_version === (a.measurement_protocol_version === undefined ? "guided-strength-activity-v0.1" : "guided-strength-activity-v0.2") &&
      (a.measurement_protocol_version === undefined || a.measurement_protocol_version === "strength-calibration-v0.3") &&
      a.athlete_id === owner &&
      uuid(a.session_id) &&
      suffix &&
      a.artifact_id ===
        `pt-guided-activity:${owner.replaceAll("-", "")}:${suffix}` &&
      instant(a.created_at) &&
      ["active", "finished", "abandoned"].includes(String(a.state)) &&
      reference(
        a.guided_reference,
        `pt-guided-strength:${owner.replaceAll("-", "")}:`,
      ) &&
      (a.previous_reference === null ||
        reference(
          a.previous_reference,
          `pt-guided-activity:${owner.replaceAll("-", "")}:`,
        )) &&
      (a.workout_session_id === null || uuid(a.workout_session_id)) &&
      (a.assessment_reference === null ||
        reference(
          a.assessment_reference,
          `pt-initial-assessment:${owner.replaceAll("-", "")}:`,
        )) &&
      (a.state === "finished"
        ? a.workout_session_id !== null
        : a.workout_session_id === null && a.assessment_reference === null) &&
      typeof a.stop_required === "boolean" &&
      a.planning_authorized === false &&
      a.clinical_clearance === false &&
      (await sha(body)) === content_hash,
  );
  if (cutoff)
    check(
      Date.parse(String(a.created_at)) <= Date.parse(cutoff) &&
        Date.parse(String(r.durable_available_at)) <= Date.parse(cutoff),
    );
  return r as unknown as ActivityReceipt;
}
