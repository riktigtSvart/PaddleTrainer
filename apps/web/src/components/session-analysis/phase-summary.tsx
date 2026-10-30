"use client";
import type { PhaseResult } from "@/lib/session-analysis/phase-statistics";
import type { SpeedUnit } from "@/lib/session-analysis/presentation";
import { speedValue } from "@/lib/session-analysis/presentation";
import { clock } from "@/lib/session-analysis/chart-data";
import { currentPhase } from "@/lib/session-analysis/phase-summary";
const number = (value: number | null, unit: string) =>
  value === null
    ? "Nincs adat"
    : new Intl.NumberFormat("hu-HU", { maximumFractionDigits: 2 }).format(
        value,
      ) +
      " " +
      unit;
export function PhaseSummary({
  results,
  cursor,
  speedUnit,
  sourceLabel,
}: {
  results: PhaseResult[];
  cursor: number;
  speedUnit: SpeedUnit;
  sourceLabel: string;
}) {
  const phase = currentPhase(results, cursor);
  const fields = [
    [
      "Szakasz távja",
      number(phase?.distance_m == null ? null : phase.distance_m / 1000, "km"),
    ],
    [
      "Szakasz időtartama",
      phase?.observed_ms == null ? "Nincs adat" : clock(phase.observed_ms),
    ],
    ["Szakasz energiája", "Nincs adat"],
    ["Átlagpulzus", number(phase?.heart_rate.value ?? null, "bpm")],
    [
      "Átlagsebesség",
      number(
        phase?.speed.value == null
          ? null
          : speedValue(phase.speed.value, speedUnit),
        speedUnit,
      ),
    ],
    ["Átlagteljesítmény", number(phase?.power.value ?? null, "W")],
  ];
  return (
    <section
      className="pt-current-phase-summary"
      aria-label="Aktuális szakasz összesítői"
    >
      <p
        className="pt-summary-caption pt-summary-name"
        title={`${phase ? phase.label : "Itt nincs egyértelműen illesztett szakasz"}${phase ? ` · ${sourceLabel}` : ""}`}
      >
        {phase ? phase.label : "Itt nincs egyértelműen illesztett szakasz"}
        {phase ? ` · ${sourceLabel}` : ""}
      </p>
      <div className="pt-analysis-metrics">
        {fields.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <details className="pt-summary-explanation">
        <summary
          aria-label="A szakaszátlagok számítása és adathiányai"
          title="A szakaszátlagok számítása és adathiányai"
        >
          ⓘ
        </summary>
        <p>
          A szakaszátlagok az ismert mintákból készülnek; az adathiányt nem
          töltjük ki. Szakaszenergia nincs mérve.
          {phase?.partial ? " A szakasz csak részben megfigyelt." : ""}
        </p>
      </details>
    </section>
  );
}
