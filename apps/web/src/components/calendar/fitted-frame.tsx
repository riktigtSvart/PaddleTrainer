"use client";
import { useLayoutEffect, useRef } from "react";
import type { ReactNode } from "react";
import { frameHeight } from "@/lib/calendar/interactions";
export default function FittedFrame({ children, active = true }: { children: ReactNode; active?: boolean }) {
  const frame = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const node = frame.current;
    if (!node || !active) return;
    let scheduled = 0;
    const measure = () => {
      const scroller = node.closest<HTMLElement>(".pt-page-content");
      const top = node.getBoundingClientRect().top + (scroller?.scrollTop ?? 0);
      const height = frameHeight(window.visualViewport?.height ?? window.innerHeight, top);
      if (node.style.getPropertyValue("--pt-calendar-frame-height") !== `${height}px`) node.style.setProperty("--pt-calendar-frame-height", `${height}px`);
    };
    const schedule = () => { cancelAnimationFrame(scheduled); scheduled = requestAnimationFrame(measure); };
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(schedule) : null;
    const calendar = node.closest(".pt-calendar");
    if (calendar) observer?.observe(calendar);
    if (node.parentElement) observer?.observe(node.parentElement);
    window.addEventListener("resize", schedule); window.visualViewport?.addEventListener("resize", schedule);
    measure();
    return () => { observer?.disconnect(); cancelAnimationFrame(scheduled); window.removeEventListener("resize", schedule); window.visualViewport?.removeEventListener("resize", schedule); };
  }, [active]);
  return <div ref={frame} className={`pt-calendar-grid-frame${active ? " is-fitted" : ""}`}>{children}</div>;
}
