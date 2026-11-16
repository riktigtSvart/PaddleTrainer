import { canonical } from "@/lib/planning-cycles/contracts";
import type { OptionsContext, OptionsData, OptionsReceipt } from "./contracts";

export function scheduleContent(data: Pick<OptionsData, "schedule_start_date" | "schedule_end_date" | "weekly_slots" | "exceptions">) {
  return { schedule_start_date: data.schedule_start_date, schedule_end_date: data.schedule_end_date,
    weekly_slots: data.weekly_slots, exceptions: data.exceptions };
}
export type OptionsHead = { owner: string; revision: number; reference: OptionsContext["reference"] };
export function optionsHead(value: OptionsContext): OptionsHead {
  return { owner: value.athlete_id, revision: value.saved?.artifact.revision ?? 0, reference: value.reference };
}
export function receiptHead(value: OptionsReceipt): OptionsHead {
  return { owner: value.artifact.athlete_id, revision: value.artifact.revision,
    reference: { artifact_id: value.artifact.artifact_id, content_hash: value.artifact.content_hash } };
}
export function requireFreshOptions(next: OptionsHead, known: OptionsHead | null) {
  if (known?.owner === next.owner && (next.revision < known.revision ||
      next.revision === known.revision && canonical(next.reference) !== canonical(known.reference)))
    throw Error("A szerver korábbi beállításváltozatot adott vissza. A frissebb mentést nem töltjük vissza régebbi adatokkal; olvasd újra a mentett állapotot.");
}
