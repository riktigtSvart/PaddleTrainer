import {
  formatDay,
  goalFamily,
  localParts,
  segments,
} from "@/lib/calendar/contracts";
import type { CalendarEvent, Feed } from "@/lib/calendar/contracts";
import Icon, { sportIcon } from "@/components/ui/icon";
import { eventLabel } from "./time-grid";
export default function PeriodGrid({
  feed,
  events,
  days,
  selected,
  overview,
  open,
  selectDay,
}: {
  feed: Feed;
  events: CalendarEvent[];
  days: string[];
  selected: string;
  overview: boolean;
  open: (event: CalendarEvent) => void;
  selectDay: (day: string) => void;
}) {
  const all = segments(
    events,
    days[0],
    days[days.length - 1],
    feed.timezone_name,
  );
  const byDay = new Map(
    days.map((d) => [d, events.filter((e) => !e.start && e.date === d)]),
  );
  for (const segment of all) {
    const row = byDay.get(segment.day);
    if (row && !row.some((e) => e.key === segment.event.key))
      row.push(segment.event);
  }
  if (overview)
    return (
      <div className="pt-overview-grid">
        {days.map((d) => {
          const activities = (byDay.get(d) ?? []).filter(
            (e) => e.kind !== "availability",
          );
          return (
            <button
              type="button"
              className={`pt-overview-day${d === selected ? " is-selected" : ""}`}
              key={d}
              title={`${formatDay(d, true)} · ${activities.length} edzés/terv`}
              aria-label={`${formatDay(d, true)} napi nézet · ${activities.length} edzés/terv`}
              onClick={() => selectDay(d)}
            >
              <span>
                {d.slice(8)}
                {d.endsWith("-01") && <small>/{d.slice(5, 7)}</small>}
              </span>
              {activities.slice(0, 3).map((e) => (
                <b key={e.key} className={`pt-goal-${goalFamily(e.goal)}`} />
              ))}
              {activities.length > 3 && <small>+{activities.length - 3}</small>}
            </button>
          );
        })}
      </div>
    );
  return (
    <div className="pt-month-grid">
      {["H", "K", "Sze", "Cs", "P", "Szo", "V"].map((d) => (
        <div className="pt-month-heading" key={d}>
          {d}
        </div>
      ))}
      {days.map((d) => {
        const activities = (byDay.get(d) ?? []).filter(
            (e) => e.kind !== "availability",
          ),
          a = feed.availability.days.find((a) => a.date === d);
        return (
          <div
            className={`pt-month-cell${d === selected ? " is-selected" : ""}`}
            key={d}
          >
            <button
              className="pt-day-number"
              type="button"
              onClick={() => selectDay(d)}
              title={formatDay(d, true)}
            >
              {d.slice(8)}
              <small>{d.endsWith("-01") ? d.slice(5, 7) + "." : ""}</small>
            </button>
            {activities.slice(0, 3).map((e) => (
              <button
                type="button"
                className={`pt-month-event pt-goal-${goalFamily(e.goal)}`}
                key={e.key}
                aria-label={eventLabel(e, feed.timezone_name)}
                title={eventLabel(e, feed.timezone_name)}
                onClick={() => open(e)}
              >
                <Icon name={sportIcon(e.sport)} />
                <span>
                  {e.start
                    ? localParts(e.start, feed.timezone_name).clock + " "
                    : ""}
                  {e.title}
                </span>
                {e.kind === "session" && (
                  <span className="pt-event-status" aria-hidden="true">
                    {e.linkedPlanId && <Icon name="calendar" />}
                    <Icon name="check" />
                  </span>
                )}
              </button>
            ))}
            {activities.length > 3 && (
              <button
                className="pt-more"
                type="button"
                onClick={() => selectDay(d)}
              >
                +{activities.length - 3} további
              </button>
            )}
            {a?.status === "available" && (
              <small className="pt-notice">{a.windows.length} idősáv</small>
            )}
            {a?.status === "unavailable" && (
              <small className="pt-notice">Nem elérhető</small>
            )}
          </div>
        );
      })}
    </div>
  );
}
