import type { PhaseGap } from "@/lib/session-analysis/plan-boundaries";
import { clock } from "@/lib/session-analysis/chart-data";

export function PhaseWindows({ gaps, selected, from, to }: { gaps: PhaseGap[]; selected: { from: number; to: number; proposal?: boolean } | null; from: number; to: number }) {
  const x = (ms: number) => 76 + (ms - from) / Math.max(1, to - from) * 794;
  return <g className="pt-phase-windows">
    {gaps.filter(g => g.to_ms > from && g.from_ms < to).map(g => <rect key={g.id} data-gap-kind={g.kind} className={`is-${g.kind}`} x={x(Math.max(from, g.from_ms))} y="24" width={Math.max(0, x(Math.min(to, g.to_ms)) - x(Math.max(from, g.from_ms)))} height="156">
      <title>{`${g.kind === "wait" ? "Várakozás / szakaszok között · kézi referencia" : "Tervszakaszhoz nem rendelt idő"} · ${clock(g.from_ms)}–${clock(g.to_ms)}`}</title>
    </rect>)}
    {selected && selected.to > from && selected.from < to && <rect className={selected.proposal ? "is-proposal" : "is-selected"} data-proposal-window={selected.proposal ? true : undefined} x={x(Math.max(from, selected.from))} y="24" width={Math.max(0, x(Math.min(to, selected.to)) - x(Math.max(from, selected.from)))} height="156"><title>{selected.proposal ? "Becsült kezdés ellenőrzési ablaka · nem igazolt szakaszhatár" : "Kijelölt időablak"}</title></rect>}
  </g>;
}
