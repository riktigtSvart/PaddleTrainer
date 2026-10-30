import type { PhaseResult } from "./phase-statistics";
/** Half-open windows prevent double assignment at a shared boundary. Unknown,
 * overlapping and unassigned windows never inherit the whole-session totals. */
export function currentPhase(
  results: PhaseResult[],
  cursor: number,
): PhaseResult | null {
  if (!Number.isFinite(cursor)) return null;
  const end = Math.max(
    0,
    ...results.flatMap((p) => (p.to_ms === null ? [] : [p.to_ms])),
  );
  const matching = results.filter(
    (p) =>
      p.from_ms !== null &&
      p.to_ms !== null &&
      p.to_ms > p.from_ms &&
      cursor >= p.from_ms &&
      (cursor < p.to_ms || (cursor === end && cursor === p.to_ms)),
  );
  return matching.length === 1 ? matching[0] : null;
}
