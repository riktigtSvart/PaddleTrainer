import { addDays, canonical } from "@/lib/planning-cycles/contracts";
import { readBody, readPending, readReceipt, requireValue } from "./contracts";
import type { Pending, Receipt } from "./contracts";

export type HistoryBackfill = {
  version: "polar-history-backfill-v0.1";
  owner: string;
  first_date: string;
  to_exclusive: string;
  cursor: string;
  checked_batches: number;
  imported: number;
  updated: number;
  pending: Pending | null;
};
export const historyKey = (owner: string) => "paddletrainer.polar-history.v1:" + owner;
function validDay(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value + "T00:00:00Z")) &&
    new Date(value + "T00:00:00Z").toISOString().slice(0, 10) === value;
}
export function newHistory(owner: string, first: string, last: string): HistoryBackfill {
  requireValue(validDay(first) && validDay(last) && first >= "1900-01-01" && first < last);
  // Reuse the closed date/request validator for the first bounded batch.
  const value: HistoryBackfill = { version: "polar-history-backfill-v0.1", owner,
    first_date: first, to_exclusive: last, cursor: last, checked_batches: 0,
    imported: 0, updated: 0, pending: null };
  historyPending(value, "00000000-0000-4000-8000-000000000001");
  return value;
}
export function historyPending(state: HistoryBackfill, requestId: string): Pending {
  requireValue(state.cursor > state.first_date);
  const first = [state.first_date, addDays(state.cursor, -90)].sort().at(-1)!;
  const body = readBody({ request_id: requestId, provider: "POLAR", datasets: ["sessions"],
    past_days: 35, future_days: 0, history_range: { from_date: first, to_exclusive: state.cursor } });
  return readPending(JSON.stringify({ version: "data-sync-pending-v0.1", owner: state.owner, body: canonical(body) }));
}
export function readHistory(raw: string, owner: string): HistoryBackfill {
  const value = JSON.parse(raw) as HistoryBackfill;
  requireValue(value.version === "polar-history-backfill-v0.1" && value.owner === owner &&
    [value.checked_batches, value.imported, value.updated].every(n => Number.isSafeInteger(n) && n >= 0) &&
    validDay(value.cursor) && value.first_date <= value.cursor && value.cursor <= value.to_exclusive);
  newHistory(owner, value.first_date, value.to_exclusive);
  if (value.pending) {
    const p = readPending(JSON.stringify(value.pending)), body = readBody(JSON.parse(p.body));
    requireValue(p.owner === owner && canonical(body) === canonical(JSON.parse(historyPending(value, body.request_id).body)));
  }
  return value;
}
export async function advanceHistory(state: HistoryBackfill, receipt: Receipt): Promise<HistoryBackfill> {
  requireValue(state.pending !== null);
  const checked = await readReceipt(receipt, state.pending);
  requireValue(checked.run.state === "succeeded" && checked.run.datasets.length === 1);
  const data = checked.run.datasets[0], body = readBody(JSON.parse(state.pending.body));
  requireValue(data.dataset === "sessions" && data.state === "succeeded" && data.skipped === 0 &&
    data.imported !== null && data.updated !== null && body.history_range?.to_exclusive === state.cursor);
  return { ...state, cursor: body.history_range!.from_date, checked_batches: state.checked_batches + 1,
    imported: state.imported + data.imported, updated: state.updated + data.updated, pending: null };
}
