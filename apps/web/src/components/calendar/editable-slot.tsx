"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties, PointerEvent, ReactNode } from "react";
import { dateDistance, formatDay, localParts } from "@/lib/calendar/contracts";
import type { CalendarEvent, Segment } from "@/lib/calendar/contracts";
import {
  minuteDelta,
  transformSlot,
  moveTraining,
} from "@/lib/calendar/slot-transform";
import type { DragMode, SlotChange } from "@/lib/calendar/slot-transform";

type Gesture = {
  id: number;
  x: number;
  y: number;
  mode: DragMode;
  active: boolean;
  height: number;
  snapshot: string;
};
type Ghost = {
  change: SlotChange;
  left: number;
  top: number;
  width: number;
  height: number;
};
export default function EditableSlot({
  event,
  segment,
  zone,
  hours,
  style,
  disabled,
  onTransform,
  open,
  className,
  label,
  children,
}: {
  event: CalendarEvent;
  segment: Segment;
  zone: string;
  hours: number;
  style: CSSProperties;
  disabled: boolean;
  onTransform: (event: CalendarEvent, change: SlotChange) => void;
  open: () => void;
  className: string;
  label: string;
  children: ReactNode;
}) {
  const shell = useRef<HTMLDivElement>(null),
    gesture = useRef<Gesture | null>(null),
    skipClickUntil = useRef(0);
  const [ghost, setGhost] = useState<Ghost | null>(null),
    [message, setMessage] = useState("");
  const snapshot = JSON.stringify([
    event.key,
    event.start,
    event.end,
    event.occurrence,
    event.window,
    event.reschedule,
    event.duration,
  ]);
  const cancel = useCallback((text = "Húzás elvetve.") => {
    gesture.current = null;
    setGhost(null);
    setMessage(text);
  }, []);
  useEffect(() => {
    if (!message || ghost) return;
    const timer = setTimeout(() => setMessage(""), 5000);
    return () => clearTimeout(timer);
  }, [message, ghost]);
  useEffect(() => {
    function key(e: KeyboardEvent) {
      if (e.key === "Escape" && gesture.current) {
        e.preventDefault();
        cancel();
      }
    }
    function blur() {
      if (gesture.current) cancel();
    }
    window.addEventListener("keydown", key);
    window.addEventListener("blur", blur);
    window.addEventListener("resize", blur);
    window.addEventListener("scroll", blur, true);
    return () => {
      gesture.current = null;
      window.removeEventListener("keydown", key);
      window.removeEventListener("blur", blur);
      window.removeEventListener("resize", blur);
      window.removeEventListener("scroll", blur, true);
    };
  }, [cancel]);
  function down(e: PointerEvent<HTMLButtonElement>, mode: DragMode) {
    if (
      disabled ||
      e.button !== 0 ||
      e.isPrimary === false ||
      e.pointerType === "touch" ||
      gesture.current
    )
      return;
    const column = shell.current?.closest<HTMLElement>(".pt-day-column");
    if (!column) return;
    const height = column.getBoundingClientRect().height;
    if (!(height > 0)) return;
    gesture.current = {
      id: e.pointerId,
      x: e.clientX,
      y: e.clientY,
      mode,
      active: false,
      height,
      snapshot,
    };
    e.currentTarget.focus();
    e.currentTarget.setPointerCapture(e.pointerId);
    setMessage("");
  }
  function locate(e: PointerEvent<HTMLButtonElement>, g: Gesture): Ghost {
    const columns = [
      ...shell
        .current!.closest(".pt-grid-body")!
        .querySelectorAll<HTMLElement>(".pt-day-column[data-date]"),
    ];
    const column =
      g.mode === "move"
        ? columns.find((c) => {
            const r = c.getBoundingClientRect();
            return e.clientX >= r.left && e.clientX < r.right;
          })
        : shell.current!.closest<HTMLElement>(".pt-day-column");
    if (!column)
      throw new Error(
        "Engedd el egy látható napon belül, vagy az Escape-pel vesd el.",
      );
    const rect = column.getBoundingClientRect();
    if (e.clientY < rect.top || e.clientY > rect.bottom)
      throw new Error(
        "A húzás a látható óratartományon kívülre került. Válaszd a teljes napot, vagy szerkeszd az időpontot kattintással.",
      );
    const delta = minuteDelta(e.clientY, g.y, g.height, hours),
      days = dateDistance(segment.day, column.dataset.date!);
    const change =
      event.kind === "planned"
        ? moveTraining(event, delta, days, zone)
        : transformSlot(event, delta, days, g.mode);
    const start =
      Number(change.start_time.slice(0, 2)) * 60 +
      Number(change.start_time.slice(3));
    const end =
      Number(change.end_time.slice(0, 2)) * 60 +
      Number(change.end_time.slice(3)) +
      (change.ends_next_day ? 1440 : 0);
    const from = hours === 24 ? 0 : 360;
    const sourceShift = dateDistance(change.date, column.dataset.date!) * 1440;
    const top = start - sourceShift;
    return {
      change,
      left: rect.left + 3,
      top: rect.top + ((top - from) / (hours * 60)) * rect.height,
      width: rect.width - 6,
      height: ((end - start) / (hours * 60)) * rect.height,
    };
  }
  function move(e: PointerEvent<HTMLButtonElement>) {
    const g = gesture.current;
    if (!g || g.id !== e.pointerId) return;
    if (disabled || g.snapshot !== snapshot) {
      cancel("A naptár megváltozott; kezdd újra a friss idősávon.");
      return;
    }
    if (!g.active && Math.hypot(e.clientX - g.x, e.clientY - g.y) < 4) return;
    g.active = true;
    e.preventDefault();
    try {
      const value = locate(e, g);
      setGhost(value);
      setMessage(
        `${formatDay(value.change.date)} · ${value.change.start_time}–${value.change.end_time}${value.change.ends_next_day ? " (másnap)" : ""}. Elengedés után áttekinthető.`,
      );
    } catch (error) {
      setGhost(null);
      setMessage(
        error instanceof Error ? error.message : "Érvénytelen időpont.",
      );
    }
  }
  function up(e: PointerEvent<HTMLButtonElement>) {
    const g = gesture.current;
    if (!g || g.id !== e.pointerId) return;
    gesture.current = null;
    setGhost(null);
    if (!g.active) return;
    skipClickUntil.current = Date.now() + 400;
    if (disabled || g.snapshot !== snapshot) {
      setMessage("A naptár megváltozott; kezdd újra a friss idősávon.");
      return;
    }
    try {
      const { change } = locate(e, g);
      if (event.kind === "planned") {
        const old = localParts(event.start!, zone);
        if (change.date !== old.date || change.start_time !== old.clock)
          onTransform(event, change);
        return;
      }
      const original = event.occurrence?.details ?? event.window!;
      setMessage("");
      if (
        change.date !== (event.occurrence?.source_date ?? event.date) ||
        change.start_time !== original.start_time ||
        change.end_time !== original.end_time ||
        change.ends_next_day !== original.ends_next_day
      )
        onTransform(event, change);
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Érvénytelen időpont.",
      );
    }
  }
  function click() {
    if (Date.now() < skipClickUntil.current) {
      skipClickUntil.current = 0;
      return;
    }
    open();
  }
  function lostCapture() {
    if (gesture.current?.active) cancel();
    else gesture.current = null;
  }
  const start = localParts(event.start!, zone),
    end = localParts(event.end!, zone);
  const firstEdge =
    segment.day === start.date &&
    segment.top === start.minute &&
    start.minute >= (hours === 24 ? 0 : 360);
  const lastEdge =
    ((segment.day === end.date && segment.bottom === end.minute) ||
      (segment.bottom === 1440 && end.minute === 0)) &&
    segment.bottom <= (hours === 24 ? 1440 : 1320);
  return (
    <div
      ref={shell}
      className={`pt-slot-shell${ghost ? " is-dragging" : ""}`}
      style={event.kind === "planned" ? style : { ...style, left: 3, right: 3 }}
    >
      <button
        type="button"
        className={className}
        data-calendar-event={event.key}
        aria-label={label}
        title={
          event.kind === "planned" || event.kind === "session"
            ? undefined
            : label
        }
        aria-disabled={disabled}
        onPointerDown={(e) => down(e, "move")}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={() => cancel()}
        onLostPointerCapture={lostCapture}
        onClick={click}
        style={{
          ...style,
          top: 0,
          height: "100%",
          left: 0,
          right: 0,
          marginLeft: 0,
          width: "100%",
        }}
      >
        {children}
      </button>
      {event.kind !== "planned" && !disabled && firstEdge && (
        <button
          type="button"
          className="pt-slot-handle is-start"
          aria-label={`Kezdés szerkesztése: ${event.title}`}
          title="Kezdés húzása · kattintással pontos szerkesztés"
          onPointerDown={(e) => down(e, "start")}
          onPointerMove={move}
          onPointerUp={up}
          onPointerCancel={() => cancel()}
          onLostPointerCapture={lostCapture}
          onClick={click}
        >
          <span />
        </button>
      )}
      {event.kind !== "planned" && !disabled && lastEdge && (
        <button
          type="button"
          className="pt-slot-handle is-end"
          aria-label={`Befejezés szerkesztése: ${event.title}`}
          title="Befejezés húzása · kattintással pontos szerkesztés"
          onPointerDown={(e) => down(e, "end")}
          onPointerMove={move}
          onPointerUp={up}
          onPointerCancel={() => cancel()}
          onLostPointerCapture={lostCapture}
          onClick={click}
        >
          <span />
        </button>
      )}
      {ghost && (
        <div
          className="pt-drag-ghost"
          style={{
            left: ghost.left,
            top: ghost.top,
            width: ghost.width,
            height: Math.max(20, ghost.height),
          }}
          aria-hidden="true"
        >
          <strong>{event.title}</strong>
          <span>
            {ghost.change.start_time}–{ghost.change.end_time}
            {ghost.change.ends_next_day ? " +1 nap" : ""}
          </span>
        </div>
      )}
      {message && (
        <span
          className={ghost ? "pt-sr-only" : "pt-drag-feedback"}
          role="status"
        >
          {message}
        </span>
      )}
    </div>
  );
}
