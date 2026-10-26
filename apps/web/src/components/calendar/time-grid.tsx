"use client";
import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  allocateLanes,
  formatDay,
  formatDuration,
  goalFamily,
  goalLabels,
  localParts,
  MIN_ACTIVITY_HEIGHT,
  segments,
} from "@/lib/calendar/contracts";
import type { CalendarEvent, Feed, Segment } from "@/lib/calendar/contracts";
import Icon, { sportIcon } from "@/components/ui/icon";
import { constraintDescription } from "@/lib/calendar/constraint-forms";
import type { Opportunity } from "@/lib/calendar/constraints";
import { estimateLabel, estimateRange } from "@/lib/calendar/duration-estimate";
export function eventDuration(e: CalendarEvent) { return e.durationEstimate ? estimateLabel(e.durationEstimate) : formatDuration(e.duration); }

export function eventLabel(event: CalendarEvent, zone: string) {
  const when = event.start
    ? localParts(event.start, zone).clock +
      (event.end ? "–" + (event.durationEstimate ? "~" : "") + localParts(event.end, zone).clock : " · végidő nélkül")
    : "Időpont nélkül";
  const plan = event.pairedPlan;
  const plannedWhen = plan
    ? `${formatDay(plan.date)} ${plan.start ? localParts(plan.start, zone).clock : "időpont nélkül"}`
    : "";
  const status = event.kind === "constraint" || event.occurrence ? constraintDescription(event) : event.kind === "availability" ? "edzéslehetőség"
    : event.kind === "planned" ? "tervezett"
      : event.linkedPlanId ? "tervhez párosított teljesítés" : "teljesített";
  const parts = [event.title, when, status, eventDuration(event),
    ...(event.kind === "planned" || event.kind === "session" ? [event.goal ? goalLabels[event.goal] : "fő cél nincs megadva"] : [])];
  if (event.conflict) parts.push(event.conflict === "review" ? "időpont tisztázandó" : "időpont ütközik");
  if (event.durationEstimate) parts.push(`személyes időbecslés · ${estimateRange(event.durationEstimate)} · ${event.durationEstimate.sample_count} megfigyelés`);
  else if (event.endEstimated) parts.push("végidő az időtartamból becsülve");
  if (plan) parts.push(`Terv: ${plan.title}`, plannedWhen, eventDuration(plan));
  return parts.join(" · ");
}
function timeLabel(minute: number) {
  const n = Math.floor(minute);
  return `${Math.floor(n / 60)
    .toString()
    .padStart(2, "0")}:${(n % 60).toString().padStart(2, "0")}`;
}
function shortTitle(event: CalendarEvent) {
  return event.kind === "availability" && !event.occurrence ? "Edzéslehetőség" : event.title;
}
export default function TimeGrid({
  feed,
  events,
  days,
  fullDay,
  open,
  selectDay,
  expandHours,
  addSlot,
  opportunities,
}: {
  feed: Feed;
  events: CalendarEvent[];
  days: string[];
  fullDay: boolean;
  open: (event: CalendarEvent) => void;
  selectDay: (day: string) => void;
  expandHours: () => void;
  addSlot?: (day: string) => void;
  opportunities?: Opportunity[];
}) {
  const from = fullDay ? 0 : 6,
    to = fullDay ? 24 : 22;
  const body = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState({ hours: 0, hour: 24 });
  // The grid compresses with viewport height. Use the same measured scale for
  // minimum-height collision lanes; before measurement reserve conservatively.
  const hour = scale.hours === to - from ? scale.hour : 24;
  useEffect(() => {
    if (!body.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const height = entry.contentRect.height / (to - from);
      if (height > 0) setScale({ hours: to - from, hour: height });
    });
    observer.observe(body.current);
    return () => observer.disconnect();
  }, [from, to]);
  const all = segments(
    events,
    days[0],
    days[days.length - 1],
    feed.timezone_name,
  );
  const outside = new Set(
    all
      .filter(
        (s) =>
          s.point ? s.top < from * 60 || s.top >= to * 60
            : s.top < from * 60 || s.bottom > to * 60 ||
              s.top >= to * 60 || s.bottom <= from * 60,
      )
      .map((s) => s.event.key),
  );
  const hours = Array.from({ length: to - from + 1 }, (_, i) => from + i);
  function draw(s: Segment) {
    const top = Math.max(s.top, from * 60),
      bottom = Math.min(s.bottom, to * 60);
    if (s.point ? top >= to * 60 || s.top < from * 60 : bottom <= top)
      return null;
    const available = s.event.kind === "availability", busy = s.event.kind === "constraint", background = available || busy;
    const actualHeight = s.point ? 0 : ((bottom - top) / 60) * hour;
    const enlarged = !background && !s.point && actualHeight < MIN_ACTIVITY_HEIGHT;
    const style: CSSProperties = {
      top: `${((top / 60 - from) / (to - from)) * 100}%`,
      height: background
        ? `${((bottom - top) / 60 / (to - from)) * 100}%`
        : s.point ? MIN_ACTIVITY_HEIGHT
          : `max(${MIN_ACTIVITY_HEIGHT}px, ${((bottom - top) / 60 / (to - from)) * 100}%)`,
      zIndex: available ? 0 : busy ? 1 : 2,
    };
    if (!background) {
      style.left = `${(s.lane / s.lanes) * 100}%`;
      style.width = `calc(${100 / s.lanes}% - 6px)`;
    }
    const small = !background && Math.max(MIN_ACTIVITY_HEIGHT, actualHeight) < 44;
    const label =
      eventLabel(s.event, feed.timezone_name) +
      (s.clockChange ? " · óraátállítás érinti" : "") +
      (enlarged ? " · jelölés az olvashatóság miatt nagyítva" : "");
    return (
      <button
        type="button"
        key={s.event.key}
        className={`pt-event pt-goal-${goalFamily(s.event.goal)}${available ? " is-available" : ""}${busy ? " is-commitment" : ""}${s.event.occurrence?.details.firmness === "flexible" ? " is-flexible" : ""}${s.event.conflict ? " has-conflict" : ""}${s.event.kind === "session" ? " is-actual" : ""}${s.point ? " is-point" : ""}${small ? " is-short" : ""}${enlarged ? " is-enlarged" : ""}`}
        style={style}
        onClick={() => open(s.event)}
        aria-label={label}
        title={label}
      >
        {enlarged && (
          <span className="pt-event-true-end" style={{ top: `calc(var(--pt-hour) * ${(bottom - top) / 60} - 1px)` }} aria-hidden="true" />
        )}
        <span className="pt-event-label">
          {!background && <Icon name={sportIcon(s.event.sport)} />}
          {busy && <Icon name="calendar" />}
          {s.event.conflict && <Icon name="alert" />}
          <span>{shortTitle(s.event)}</span>
          {!background && (
            <span className="pt-event-duration">
              {eventDuration(s.event)}
            </span>
          )}
          {s.event.kind === "session" && (
            <span className="pt-event-status" aria-hidden="true">
              {s.event.linkedPlanId && <Icon name="calendar" />}
              <Icon name="check" />
            </span>
          )}
        </span>
        {!s.point && (
          <span className="pt-event-time">
            {background
              ? `${timeLabel(s.top)}–${timeLabel(s.bottom)}`
              : eventDuration(s.event)}
          </span>
        )}
      </button>
    );
  }
  return (
    <>
      {outside.size > 0 && !fullDay && (
        <p className="pt-notice">
          {outside.size} esemény érinti a látható óratartományon kívüli részt.{" "}
          <button type="button" className="pt-more" onClick={expandHours}>
            Teljes nap mutatása
          </button>
        </p>
      )}
      <div className="pt-grid-scroll">
        <div
          className={`pt-time-grid${days.length === 1 ? " is-day" : ""}`}
          style={
            {
              "--pt-days": days.length,
              "--pt-hours": to - from,
              "--pt-min-event-height": `${MIN_ACTIVITY_HEIGHT}px`,
            } as CSSProperties
          }
        >
          <div className="pt-grid-head">
            <div className="pt-grid-label">{feed.timezone_name}</div>
            {days.map((date) => {
              const a = feed.availability.days.find((d) => d.date === date);
              const declared = opportunities?.filter((w) => w.source_date === date || w.start_at && w.end_at &&
                localParts(w.start_at, feed.timezone_name).date <= date &&
                (localParts(w.end_at, feed.timezone_name).date > date || localParts(w.end_at, feed.timezone_name).date === date && localParts(w.end_at, feed.timezone_name).clock !== "00:00")).length;
              return (
                <div
                  className={`pt-grid-day-head${date === feed.local_today ? " is-today" : ""}`}
                  key={date}
                >
                  <button type="button" onClick={() => selectDay(date)}>
                    {formatDay(date, true)}
                  </button>
                  <small>
                    {a?.status === "unavailable" ? "Edzésre nem elérhető" : declared && (a?.max_total_minutes === null || a?.max_total_minutes === undefined)
                      ? `${declared} megadott idősáv`
                      : !a || a.status === "unknown"
                      ? "Keret nincs megadva"
                      : a.max_total_minutes === null
                          ? `${a.windows.length} megadott idősáv`
                          : `Napi keret: ${a.max_total_minutes} p`}
                  </small>
                  {addSlot && <button className="pt-add-slot" type="button" aria-label={`${formatDay(date)} · új idősáv`} onClick={() => addSlot(date)}>+</button>}
                </div>
              );
            })}
          </div>
          <div className="pt-grid-unscheduled">
            <div className="pt-grid-label">Időpont nélkül</div>
            {days.map((date) => (
              <div className="pt-unscheduled-day" key={date}>
                {events
                  .filter((e) => !e.start && e.date === date)
                  .map((e) => (
                    <button
                      type="button"
                      key={e.key}
                      title={eventLabel(e, feed.timezone_name)}
                      onClick={() => open(e)}
                    >
                      {e.title}
                      <br />
                      <small>{eventDuration(e)}</small>
                    </button>
                  ))}
              </div>
            ))}
          </div>
          <div className="pt-grid-body" ref={body}>
            <div className="pt-hour-axis">
              {hours.map((h) => (
                <span
                  key={h}
                  style={{ top: `${((h - from) / (to - from)) * 100}%` }}
                >
                  {String(h).padStart(2, "0")}:00
                </span>
              ))}
            </div>
            {days.map((date) => {
              const perDay = all.filter((s) => s.day === date);
              const available = perDay.filter(
                (s) => s.event.kind === "availability",
              );
              const busy = perDay.filter((s) => s.event.kind === "constraint");
              const activity = allocateLanes(
                perDay.filter((s) => s.event.kind !== "availability" && s.event.kind !== "constraint" &&
                  (s.point ? s.top >= from * 60 && s.top < to * 60
                    : s.bottom > from * 60 && s.top < to * 60)),
                MIN_ACTIVITY_HEIGHT / hour * 60,
                from * 60,
              );
              return (
                <div
                  key={date}
                  className={`pt-day-column${feed.availability.days.find((d) => d.date === date)?.status === "unavailable" ? " unavailable" : ""}`}
                >
                  {available.map(draw)}
                  {busy.map(draw)}
                  {activity.map(draw)}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </>
  );
}
