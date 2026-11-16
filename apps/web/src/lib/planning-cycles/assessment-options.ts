import { canonical, object } from "./contracts";
import { readOptionsReceipt } from "@/lib/training-options/contracts";
import {physicalStrengthOptions} from "./assessment-source-changes";

// Match assessment_content(): observations belong to venues and equipment.
// The latest timetable and closures are enforced separately by the planner.
export function physicalOptions(raw: unknown) {
  const data = object(raw);
  return {timezone_name:data.timezone_name,locations:(data.locations as unknown[]).map(l => Object.fromEntries(Object.entries(object(l)).filter(([key]) => !["coordinates", "area", "kind", "pool_length_m", "daylight_overrides"].includes(key))))};
}

export async function verifyAssessmentOptions(inputs: Record<string, unknown>, body: Record<string, unknown>, context: Record<string, unknown>, owner: string) {
  if (canonical(body.options_reference) === canonical(inputs.training_options_reference ?? null)) return;
  const light = inputs.daylight_context ? object(inputs.daylight_context) : null;
  const saved = context.receipt ? object(object(context.receipt).artifact) : null;
  const sourceRaw = context.options_source_receipt ?? (saved ? object(saved.snapshot).options_receipt : null);
  const currentRaw = context.current_options_receipt ?? light?.options_receipt;
  const source = await readOptionsReceipt(sourceRaw, owner), current = await readOptionsReceipt(currentRaw, owner);
  const ref = (r: typeof source) => ({ artifact_id: r.artifact.artifact_id, content_hash: r.artifact.content_hash });
  const cutoff = Date.parse(String(inputs.captured_at));
  const ids=context.source_comparison?(object(context.source_comparison).location_ids as string[]):null;
  if (!Number.isFinite(cutoff) || canonical(ref(source)) !== canonical(body.options_reference) ||
      canonical(ref(current)) !== canonical(inputs.training_options_reference) ||
      source.artifact.revision > current.artifact.revision || Date.parse(source.artifact.created_at) > Date.parse(current.artifact.created_at) ||
      [source, current].some(r => Date.parse(r.durable_available_at) > cutoff) ||
      canonical(ids?physicalStrengthOptions(source.artifact.proposal.data,ids):physicalOptions(source.artifact.proposal.data)) !== canonical(ids?physicalStrengthOptions(current.artifact.proposal.data,ids):physicalOptions(current.artifact.proposal.data)))
    throw Error("A felmérés helyszíni forrása eltér az aktuális helyszíntől vagy felszereléstől.");
}
