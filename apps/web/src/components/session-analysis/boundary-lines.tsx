import { clock } from "@/lib/session-analysis/chart-data";
import { positionedBoundaries } from "@/lib/session-analysis/plan-boundaries";
import type { Boundary } from "@/lib/session-analysis/plan-boundaries";

export function BoundaryLines({ boundaries, from, to, manual, distanceBased = false }: { boundaries: Boundary[]; from: number; to: number; manual: boolean; distanceBased?: boolean }) {
  const visible = positionedBoundaries(boundaries, from, to);
  return <g className={`pt-plan-boundaries${manual ? " is-manual" : ""}`} aria-label={manual ? "Kézzel megadott tervhatárok" : "Terv szerinti szakaszhatárok"}>
    {visible.map(({ boundary, x, showLabel }) => {
      return <g key={boundary.ms} data-boundary-ms={boundary.ms}>
        <line x1={x} x2={x} y1="24" y2="180"><title>{`${manual ? "Kézi tervjelölés" : distanceBased ? "Számított tervhatár · mért távsor" : "Terv szerinti határ"} · ${clock(boundary.ms)} · ${boundary.labels.join(" · ")}`}</title></line>
        {showLabel && <text x={x} y="17" textAnchor={x > 820 ? "end" : "start"}>{clock(boundary.ms)}</text>}
      </g>;
    })}
  </g>;
}
