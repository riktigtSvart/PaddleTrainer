import { addDays, viewRange } from "./contracts";
export const OVERVIEW_CHUNK_DAYS = 28;
export const OVERVIEW_INITIAL_CHUNKS = 6;
export const OVERVIEW_MAX_CHUNKS = 8;
export type OverviewRange = { start: string; end: string };
export function overviewRange(start: string): OverviewRange {
  const end = addDays(start, OVERVIEW_CHUNK_DAYS - 1);
  if (start < "1900-01-01" || end > "2100-12-31")
    throw new Error("Elérted a támogatott naptári időszak szélét.");
  return { start, end };
}
export function initialOverview(anchor: string): OverviewRange[] {
  const { start } = viewRange(anchor, 168);
  return Array.from({ length: OVERVIEW_INITIAL_CHUNKS }, (_, i) =>
    overviewRange(addDays(start, i * OVERVIEW_CHUNK_DAYS)),
  );
}
export function adjacentOverview(
  ranges: OverviewRange[],
  direction: -1 | 1,
): OverviewRange {
  const edge = direction === -1 ? ranges[0] : ranges[ranges.length - 1];
  return overviewRange(addDays(edge.start, direction * OVERVIEW_CHUNK_DAYS));
}
/** Return the retained window; discard only from the opposite edge. */
export function retainOverview<T extends OverviewRange>(
  chunks: T[],
  next: T,
  direction: -1 | 1,
): T[] {
  if (chunks.some((c) => c.start === next.start)) return chunks;
  const expected = adjacentOverview(chunks, direction);
  if (next.start !== expected.start || next.end !== expected.end)
    throw new Error("Nem folytonos naptári részlet.");
  return direction === -1
    ? [next, ...chunks].slice(0, OVERVIEW_MAX_CHUNKS)
    : [...chunks, next].slice(-OVERVIEW_MAX_CHUNKS);
}
