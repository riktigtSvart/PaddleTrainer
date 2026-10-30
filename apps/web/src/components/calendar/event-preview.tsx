"use client";
import Link from "next/link";
import { createPortal } from "react-dom";
import { useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { CalendarEvent, Feed } from "@/lib/calendar/contracts";
import { eventHref, previewLines } from "@/lib/calendar/event-preview";

type Preview = { event: CalendarEvent; left: number; top: number };
export default function EventPreview({
  feed,
  events,
  onEditGoal,
  onMove,
  editDisabled,
  children,
}: {
  feed: Feed;
  events: CalendarEvent[];
  children: ReactNode;
  onEditGoal: (event: CalendarEvent) => void;
  onMove: (event: CalendarEvent) => void;
  editDisabled: boolean;
}) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const box = useRef<HTMLDivElement>(null),
    timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const id = useId();
  const lastTrigger = useRef<HTMLElement | null>(null);
  function cancelHide() {
    if (timer.current) clearTimeout(timer.current);
  }
  function hideSoon() {
    cancelHide();
    timer.current = setTimeout(() => {
      if (!box.current?.contains(document.activeElement)) setPreview(null);
    }, 180);
  }
  function reveal(target: EventTarget) {
    if (!(target instanceof Element)) return;
    const trigger = target.closest<HTMLElement>("[data-calendar-event]");
    const event = events.find((e) => e.key === trigger?.dataset.calendarEvent);
    if (!trigger || !event || !eventHref(event)) return;
    cancelHide();
    lastTrigger.current = trigger;
    const rect = trigger.getBoundingClientRect();
    setPreview({
      event,
      left: Math.max(8, Math.min(rect.left, window.innerWidth - 304)),
      top: Math.max(8, Math.min(rect.bottom + 6, window.innerHeight - 320)),
    });
  }
  useEffect(() => {
    function close() {
      setPreview(null);
    }
    function key(event: KeyboardEvent) {
      if (event.key === "Escape") {
        if (box.current?.contains(document.activeElement))
          lastTrigger.current?.focus();
        close();
      }
    }
    window.addEventListener("keydown", key);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      if (timer.current) clearTimeout(timer.current);
      window.removeEventListener("keydown", key);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, []);
  // Dismiss obsolete information while the parent is fetching or replaces its events.
  const current = preview && events.find((e) => e.key === preview.event.key);
  return (
    <div
      className="pt-event-preview-root"
      onMouseOver={(e) => reveal(e.target)}
      onMouseLeave={hideSoon}
      onFocus={(e) => reveal(e.target)}
      onBlur={hideSoon}
      onKeyDown={(event) => {
        if (
          event.key === "ArrowDown" &&
          event.target instanceof Element &&
          event.target.closest("[data-calendar-event]")
        ) {
          event.preventDefault();
          reveal(event.target);
          requestAnimationFrame(() =>
            box.current?.querySelector<HTMLAnchorElement>("a")?.focus(),
          );
        }
      }}
      onPointerDown={() => setPreview(null)}
    >
      {children}
      {preview &&
        current &&
        createPortal(
          <div
            ref={box}
            id={id}
            role="dialog"
            aria-label="Edzés gyorsnézet"
            onPointerDown={(event) => event.stopPropagation()}
            className="pt-event-preview"
            style={{ left: preview.left, top: preview.top }}
            onMouseEnter={cancelHide}
            onMouseLeave={hideSoon}
            onFocus={cancelHide}
            onBlur={hideSoon}
          >
            <strong>{current.title}</strong>
            <ul>
              {previewLines(current, feed).map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
            <Link href={eventHref(current)!}>Edzés részletei →</Link>
            {!editDisabled && (
              <div className="pt-preview-actions">
                <button
                  type="button"
                  onClick={() => {
                    setPreview(null);
                    onEditGoal(current);
                  }}
                >
                  Fő cél módosítása
                </button>
                {current.kind === "planned" && (
                  <button
                    type="button"
                    onClick={() => {
                      setPreview(null);
                      onMove(current);
                    }}
                  >
                    Áthelyezés…
                  </button>
                )}
              </div>
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}
