"use client";
import { CalendarMealsDay, useNutritionLayerEnabled } from "@/components/nutrition/calendar-layer";
import { useEffect, useRef, useState } from "react";
import {
  formatDay,
  goalFamily,
  localParts,
  segments,
} from "@/lib/calendar/contracts";
import type { CalendarEvent, Feed } from "@/lib/calendar/contracts";
import Icon, { sportIcon } from "@/components/ui/icon";
import { eventLabel } from "./time-grid";
import AlternativeBadge from "./alternative-badge";
import { interactionHint } from "@/lib/calendar/interactions";
import type { CalendarTarget } from "@/lib/calendar/interactions";
import { calendarCycles, cycleBoundaries } from "@/lib/calendar/cycles";
import { CycleDayMarkers } from "./cycle-markers";
import {cycleLoad as loadBand} from "@/lib/calendar/cycle-context";
import type {CycleContext} from "@/lib/calendar/cycle-context";
import type {CalendarCycle} from "@/lib/calendar/cycles";
export default function PeriodGrid({
  feed,
  events,
  days,
  selected,
  overview,
  open,
  selectDay,
  addSlot,
  onContext,
  fitted = false,
  showCycles = false,
  showCycleLoad = false,
  cycleContext = null,
  onOpenCycle,
}: {
  feed: Feed;
  events: CalendarEvent[];
  days: string[];
  selected: string;
  overview: boolean;
  open: (event: CalendarEvent) => void;
  selectDay: (day: string) => void;
  addSlot?: (day: string) => void;
  onContext?: (target: CalendarTarget) => void;
  fitted?: boolean;
  showCycles?: boolean;
  showCycleLoad?: boolean;
  cycleContext?: CycleContext | null;
  onOpenCycle?: (cycle: CalendarCycle) => void;
}) {
  const mealsEnabled=useNutritionLayerEnabled();
  const cycles = showCycles ? calendarCycles(feed.periods) : [];
  const grid = useRef<HTMLDivElement>(null);
  const [capacity, setCapacity] = useState(3);
  useEffect(() => {
    if (!fitted || !grid.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const rows = Math.ceil(days.length / 7), rowHeight = (entry.contentRect.height - 20 - rows * 4) / rows;
      setCapacity(Math.max(1, Math.floor((rowHeight - (showCycles ? 62 : 32) - (mealsEnabled ? 24 : 0)) / 22)));
    });
    observer.observe(grid.current); return () => observer.disconnect();
  }, [fitted, days.length, showCycles, mealsEnabled]);
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
            (e) => e.kind === "planned" || e.kind === "session",
          );
          return (
            <button
              type="button"
              className={`pt-overview-day${d === selected ? " is-selected" : ""}`}
              data-cycle-load={showCycleLoad ? loadBand(cycleContext,feed,d)?.tone : undefined}
              key={d}
              title={`${formatDay(d, true)} · ${activities.length} edzés/terv · ${(byDay.get(d) ?? []).filter((e) => e.kind === "constraint").length} elfoglaltság`}
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
    <div ref={grid} className="pt-month-grid" style={{ gridTemplateRows: `20px repeat(${Math.ceil(days.length / 7)}, minmax(0, 1fr))` }}>
      {Array.from({length:7},(_,i)=>["V","H","K","Sze","Cs","P","Szo"][(new Date(days[0]+"T12:00:00Z").getUTCDay()+i)%7]).map((d) => (
        <div className="pt-month-heading" key={d}>
          {d}
        </div>
      ))}
      {days.map((d) => {
        const activities = (byDay.get(d) ?? []).filter(
            (e) => e.kind === "planned" || e.kind === "session",
          ),
          a = feed.availability.days.find((a) => a.date === d);
        const ordered = [...activities, ...(byDay.get(d) ?? []).filter((e) => e.kind === "constraint" || e.kind === "availability")];
        const shown = ordered.slice(0, ordered.length > capacity ? Math.max(0, capacity - 1) : capacity);
        return (
          <div
            className={`pt-month-cell${d === selected ? " is-selected" : ""}`}
            key={d}
            data-date={d}
            data-cycle-load={showCycleLoad ? loadBand(cycleContext,feed,d)?.tone : undefined}
            title={showCycleLoad ? loadBand(cycleContext,feed,d)?.label : undefined}
            data-cycle-start={cycleBoundaries(cycles, d).filter(b => b.edge === "start").map(b => b.cycle.kind).join(" ") || undefined}
            data-cycle-end={cycleBoundaries(cycles, d).filter(b => b.edge === "end").map(b => b.cycle.kind).join(" ") || undefined}
            tabIndex={onContext || addSlot ? 0 : undefined}
            role="group"
            aria-label={interactionHint(d)}
            onDoubleClick={(e) => { if (addSlot && !(e.target as Element).closest("button")) addSlot(d); }}
            onContextMenu={(e) => {
              if (!onContext) return;
              e.preventDefault(); const target = (e.target as Element).closest<HTMLElement>("[data-calendar-event]");
              const rect = e.currentTarget.getBoundingClientRect();
              onContext({ date: d, event: events.find((v) => v.key === target?.dataset.calendarEvent) ?? null, x: e.clientX || rect.left + 12, y: e.clientY || rect.top + 12 });
            }}
            onKeyDown={(e) => { if (onContext && e.target === e.currentTarget && ["Enter", " ", "ContextMenu"].includes(e.key)) { e.preventDefault(); const rect = e.currentTarget.getBoundingClientRect(); onContext({ date: d, event: null, x: rect.left + 12, y: rect.top + 12 }); } }}
          >
            <button
              className="pt-day-number"
              type="button"
              onClick={() => selectDay(d)}
              title={`${formatDay(d, true)} · ${(byDay.get(d) ?? []).length} esemény`}
              aria-label={`${formatDay(d, true)} napi nézet · ${(byDay.get(d) ?? []).length} esemény`}
            >
              {d.slice(8)}
              <small>{d.endsWith("-01") ? d.slice(5, 7) + "." : ""}</small>
            </button>
            <CycleDayMarkers cycles={cycles} date={d} onOpenCycle={onOpenCycle} />
            <CalendarMealsDay date={d} compact/>
            {fitted ? <>
              {shown.map((e) => <button type="button" key={e.key} data-calendar-event={e.key} className={e.kind === "planned" || e.kind === "session" ? `pt-month-event pt-goal-${goalFamily(e.goal)}` : "pt-month-commitment"} onClick={() => open(e)} aria-label={eventLabel(e, feed.timezone_name)} title={eventLabel(e, feed.timezone_name)}><Icon name={e.kind === "availability" ? "clock" : e.kind === "constraint" ? "calendar" : sportIcon(e.sport)} /><span>{e.start ? localParts(e.start, feed.timezone_name).clock + " " : ""}{e.kind === "availability" ? "Edzéslehetőség" : e.title}</span><AlternativeBadge event={e} />{e.kind === "session" && <Icon name="check" />}</button>)}
              {ordered.length > shown.length && <button type="button" className="pt-more" onClick={() => selectDay(d)}>+{ordered.length - shown.length} esemény</button>}
              {a?.status === "unavailable" && ordered.length === 0 && <small className="pt-notice">Nem elérhető</small>}
            </> : <>
            {activities.slice(0, 3).map((e) => (
              <button
                type="button"
                className={`pt-month-event pt-goal-${goalFamily(e.goal)}`}
                key={e.key}
                data-calendar-event={e.key}
                aria-label={eventLabel(e, feed.timezone_name)}
                title={eventLabel(e, feed.timezone_name)}
                onClick={() => open(e)}
              >
                <Icon name={sportIcon(e.sport)} />
                {e.conflict && <Icon name="alert" />}
                <span>
                  {e.start
                    ? localParts(e.start, feed.timezone_name).clock + " "
                    : ""}
                  {e.title}
                </span>
                <AlternativeBadge event={e} />
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
            {(byDay.get(d) ?? [])
              .filter((e) => e.kind === "constraint")
              .slice(0, 1)
              .map((e) => (
                <button
                  type="button"
                  key={e.key}
                  className="pt-month-commitment"
                  data-calendar-event={e.key}
                  onClick={() => open(e)}
                  title={eventLabel(e, feed.timezone_name)}
                >
                  <Icon name="calendar" />
                  {e.title}
                </button>
              ))}
            {(byDay.get(d) ?? []).filter((e) => e.kind === "constraint")
              .length > 1 && (
              <button
                type="button"
                className="pt-more"
                onClick={() => selectDay(d)}
              >
                +
                {(byDay.get(d) ?? []).filter((e) => e.kind === "constraint")
                  .length - 1}{" "}
                elfoglaltság
              </button>
            )}
            {(byDay.get(d) ?? [])
              .filter((e) => e.kind === "availability" && e.occurrence)
              .slice(0, 1)
              .map((e) => (
                <button
                  key={e.key}
                  type="button"
                  className="pt-more"
                  data-calendar-event={e.key}
                  onClick={() => open(e)}
                >
                  Edzéslehetőség
                </button>
              ))}
            {a?.status === "available" && (
              <small className="pt-notice">{a.windows.length} idősáv</small>
            )}
            {a?.status === "unavailable" && (
              <small className="pt-notice">Nem elérhető</small>
            )}            </>}

          </div>
        );
      })}
    </div>
  );
}
