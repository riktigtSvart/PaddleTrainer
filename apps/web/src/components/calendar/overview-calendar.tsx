"use client";
import { useLayoutEffect, useRef, useState, useEffect } from "react";
import { loadFeed } from "@/lib/calendar/client";
import { loadConstraints } from "@/lib/calendar/constraint-client";
import {
  calendarEntries,
  dayList,
  eventsFrom,
  formatDay,
} from "@/lib/calendar/contracts";
import type { CalendarEvent, Feed } from "@/lib/calendar/contracts";
import { constraintEvents } from "@/lib/calendar/constraint-forms";
import { conflictKind } from "@/lib/calendar/constraints";
import type { ScheduleContext } from "@/lib/calendar/constraints";
import {
  adjacentOverview,
  initialOverview,
  retainOverview,
} from "@/lib/calendar/overview";
import type { OverviewRange } from "@/lib/calendar/overview";
import PeriodGrid from "./period-grid";
import EventPreview from "./event-preview";
import { eventHref } from "@/lib/calendar/event-preview";

type Chunk = OverviewRange & { feed: Feed; context: ScheduleContext | null };
export default function OverviewCalendar({
  feed,
  context,
  layers,
  selectDay,
}: {
  feed: Feed;
  context: ScheduleContext | null;
  layers: { availability: boolean; commitments: boolean; training: boolean };
  selectDay: (date: string) => void;
}) {
  const [chunks, setChunks] = useState<Chunk[]>(() =>
    initialOverview(feed.start_date).map((range) => ({
      ...range,
      feed,
      context,
    })),
  );
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const viewport = useRef<HTMLDivElement>(null),
    request = useRef<AbortController | null>(null);
  const previousTop = useRef(0),
    restoration = useRef<{ start: string; offset: number } | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  useLayoutEffect(() => {
    const saved = restoration.current,
      node = viewport.current;
    if (!saved || !node) return;
    const anchor = node.querySelector<HTMLElement>(
      `[data-overview-start="${saved.start}"]`,
    );
    if (anchor)
      node.scrollTop +=
        anchor.getBoundingClientRect().top -
        node.getBoundingClientRect().top -
        saved.offset;
    previousTop.current = node.scrollTop;
    restoration.current = null;
  }, [chunks]);
  async function extend(direction: -1 | 1) {
    if (request.current) return;
    const abort = new AbortController();
    request.current = abort;
    setBusy(true);
    setError("");
    try {
      const range = adjacentOverview(chunks, direction);
      const [next, schedule] = await Promise.all([
        loadFeed(range, abort.signal),
        loadConstraints(range, abort.signal),
      ]);
      if (abort.signal.aborted) return;
      if (
        next.athlete_id !== feed.athlete_id ||
        next.timezone_name !== feed.timezone_name ||
        next.start_date !== range.start ||
        next.end_date !== range.end ||
        schedule.athlete_id !== feed.athlete_id ||
        schedule.timezone_name !== feed.timezone_name ||
        schedule.start_date !== range.start ||
        schedule.end_date !== range.end ||
        (next.availability.reference?.artifact_id ?? null) !==
          (schedule.availability?.artifact.artifact_id ?? null) ||
        (next.availability.reference?.content_hash ?? null) !==
          (schedule.availability?.artifact.content_hash ?? null)
      )
        throw new Error(
          "A naptári részlet forrásai nem egyeznek. Próbáld újra.",
        );
      const node = viewport.current;
      if (node) {
        const top = node.getBoundingClientRect().top;
        const visible = [
          ...node.querySelectorAll<HTMLElement>("[data-overview-start]"),
        ].find((e) => e.getBoundingClientRect().bottom > top + 2);
        if (visible)
          restoration.current = {
            start: visible.dataset.overviewStart!,
            offset: visible.getBoundingClientRect().top - top,
          };
      }
      setChunks((old) =>
        retainOverview(
          old,
          { ...range, feed: next, context: schedule },
          direction,
        ),
      );
    } catch (e) {
      if (!abort.signal.aborted)
        setError(
          e instanceof Error ? e.message : "A további hetek nem tölthetők be.",
        );
    } finally {
      if (!abort.signal.aborted) {
        request.current = null;
        setBusy(false);
      }
    }
  }
  function open(event: CalendarEvent) {
    const href = eventHref(event);
    if (href) window.location.assign(href);
    else selectDay(event.date);
  }
  return (
    <section aria-label="Görgethető naptári áttekintés">
      <div
        ref={viewport}
        className="pt-overview-scroll"
        tabIndex={0}
        aria-label="Naptár · további hetek görgetéssel"
        onScroll={() => {
          const node = viewport.current!;
          const delta = node.scrollTop - previousTop.current;
          previousTop.current = node.scrollTop;
          if (busy || error || Math.abs(delta) < 1) return;
          if (delta < 0 && node.scrollTop < 120) void extend(-1);
          else if (
            delta > 0 &&
            node.scrollHeight - node.scrollTop - node.clientHeight < 180
          )
            void extend(1);
        }}
      >
        <button
          type="button"
          className="pt-overview-more pt-button"
          disabled={busy}
          onClick={() => void extend(-1)}
        >
          Korábbi 4 hét
        </button>
        {chunks.map((chunk) => {
          const schedule = chunk.feed === feed ? context : chunk.context;
          const training = eventsFrom(chunk.feed).map(
            (event): CalendarEvent => {
              if (event.kind !== "planned" || !schedule) return event;
              const impacts = schedule.conflicts.filter(
                (c) =>
                  c.plan_id === event.entityId && conflictKind(c) !== "unknown",
              );
              const conflict = impacts.some((c) => c.severity === "fixed")
                ? "fixed"
                : impacts.some((c) => c.severity === "flexible")
                  ? "flexible"
                  : impacts.length
                    ? "review"
                    : undefined;
              return { ...event, conflict };
            },
          );
          const events = calendarEntries([
            ...training,
            ...(schedule ? constraintEvents(schedule) : []),
          ]).filter((event) =>
            event.kind === "availability"
              ? layers.availability
              : event.kind === "constraint"
                ? layers.commitments
                : layers.training,
          );
          return (
            <section
              key={chunk.start}
              data-overview-start={chunk.start}
              className="pt-overview-chunk"
            >
              <h2>
                {formatDay(chunk.start)} – {formatDay(chunk.end)}{" "}
                <small>
                  {chunk.start.slice(0, 4)}
                  {chunk.start.slice(0, 4) !== chunk.end.slice(0, 4)
                    ? `–${chunk.end.slice(0, 4)}`
                    : ""}
                </small>
              </h2>
              <EventPreview
                feed={chunk.feed}
                events={events}
                editDisabled
                onEditGoal={(event) => selectDay(event.date)}
                onMove={(event) => selectDay(event.date)}
              >
                <PeriodGrid
                  feed={chunk.feed}
                  events={events}
                  days={dayList(chunk.start, chunk.end)}
                  selected={feed.local_today}
                  overview={false}
                  open={open}
                  selectDay={selectDay}
                />
              </EventPreview>
            </section>
          );
        })}
        <button
          type="button"
          className="pt-overview-more pt-button"
          disabled={busy}
          onClick={() => void extend(1)}
        >
          Következő 4 hét
        </button>
      </div>
      {busy && (
        <p className="pt-notice" role="status">
          További 4 hét betöltése…
        </p>
      )}
      {error && (
        <p className="pt-message is-error" role="alert">
          {error} A Korábbi / Következő 4 hét gombbal újrapróbálható.
        </p>
      )}
    </section>
  );
}
