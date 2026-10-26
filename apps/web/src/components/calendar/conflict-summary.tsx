import Icon from "@/components/ui/icon";
import { formatDay } from "@/lib/calendar/contracts";
import { conflictKind, conflictLabels } from "@/lib/calendar/constraints";
import type { Conflict } from "@/lib/calendar/constraints";
import { estimateLabel, estimateRange } from "@/lib/calendar/duration-estimate";
import type { DurationEstimate } from "@/lib/calendar/duration-estimate";
export default function ConflictSummary({ conflicts, estimates = {}, openPlan, preview = false }: {
  conflicts: Conflict[]; estimates?: Record<string, DurationEstimate>; openPlan?: (id: string) => void; preview?: boolean;
}) {
  return <>{(["conflict", "estimate", "unknown"] as const).map((kind) => {
    const items = conflicts.filter((c) => conflictKind(c) === kind);
    if (!items.length) return null;
    const count = new Set(items.map((c) => c.plan_id)).size;
    const title = kind === "conflict" ? `${count} edzésterv időpontja egyeztetendő`
      : kind === "estimate" ? `${count} edzéstervnél becslés alapján átfedés lehetséges` : `Hiányzó időadat · ${count} edzésterv`;
    return <details key={kind} className={`pt-conflicts${kind === "unknown" ? " is-data-gap" : ""}`} open={preview && kind !== "unknown" ? true : undefined}>
      <summary><Icon name={kind === "unknown" ? "info" : "alert"} />{title}</summary>
      {kind === "unknown" && <p className="pt-notice">Az adathiány alapján az időbeli átfedés nem dönthető el.</p>}
      <ul>{items.map((c, i) => <li key={i}>
        {openPlan ? <button type="button" className="pt-more" onClick={() => openPlan(c.plan_id)}>{c.plan_title}</button> : <strong>{c.plan_title}</strong>}
        {" · "}{formatDay(c.date)} · {c.constraint_title}: {conflictLabels[c.code] ?? c.code}{c.severity === "flexible" ? " Rugalmas elfoglaltság." : ""}
        {estimates[c.plan_id] && <small className="pt-estimate-source">Naptári időbecslés: {estimateLabel(estimates[c.plan_id])} · tartomány: {estimateRange(estimates[c.plan_id])}.</small>}
      </li>)}</ul>
    </details>;
  })}</>;
}
