import { object } from "@/lib/planning-cycles/contracts";
import { readFeed, verifyGoalReceipt } from "./contracts";
const errors: Record<string, string> = {
  GOAL_CONFIGURED_OWNER_NOT_FOUND:
    "A sportolói fiók még nincs előkészítve az alkalmazásban.",
  CALENDAR_RANGE_TOO_DENSE:
    "Túl sok adat esik az időszakba. Válassz rövidebb időnézetet.",
  CALENDAR_REVISION_CONFLICT_RELOAD:
    "Közben megváltozott az edzés célja. Olvasd újra az adatokat, majd nézd át a választást.",
  CALENDAR_WORKOUT_NOT_FOUND: "Az edzés már nem érhető el ennél a sportolónál.",
  CALENDAR_SOURCE_UNAVAILABLE:
    "A naptár forrása most nem érhető el. Ellenőrizd az API-t, majd próbáld újra.",
  CALENDAR_GOAL_STORAGE_INVALID:
    "A céljelölés előzménye nem ellenőrizhető. A mentést ellenőrizni kell.",
};
export class CalendarHTTPError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(
      errors[code] ?? `A naptári művelet nem sikerült (${status}, ${code}).`,
    );
  }
}
async function json(response: Response) {
  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw new Error("A naptár nem értelmezhető választ kapott.");
  }
  if (!response.ok) {
    const detail = object(value).detail;
    const code =
      detail && typeof detail === "object"
        ? String(object(detail).code ?? "UNKNOWN")
        : "UNKNOWN";
    throw new CalendarHTTPError(response.status, code);
  }
  return value;
}
export async function loadFeed(
  range: { start: string; end: string } | null,
  signal?: AbortSignal,
) {
  const query = range
    ? "?" +
      new URLSearchParams({ start_date: range.start, end_date: range.end })
    : "";
  return readFeed(
    await json(
      await fetch("/api/calendar/feed" + query, { signal, cache: "no-store" }),
    ),
  );
}
export async function saveGoal(body: string, owner: string) {
  const value = await json(
    await fetch("/api/calendar/goals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      cache: "no-store",
    }),
  );
  return verifyGoalReceipt(value, body, owner);
}
