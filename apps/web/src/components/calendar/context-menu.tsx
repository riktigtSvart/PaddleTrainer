"use client";
import { createPortal } from "react-dom";
import { useEffect, useRef } from "react";
import type { CalendarTarget } from "@/lib/calendar/interactions";
export default function CalendarContextMenu({ target, disabled, onAdd, onEdit, onRemove, onClose, onAddWorkout }: {
  target: CalendarTarget; disabled: boolean; onAdd: () => void; onEdit: () => void; onRemove: () => void; onClose: () => void; onAddWorkout?: () => void;
}) {
  const menu = useRef<HTMLDivElement>(null);
  const slot = target.event?.kind === "availability" || target.event?.kind === "constraint";
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    (menu.current?.querySelector<HTMLButtonElement>("button:not(:disabled)") ?? menu.current)?.focus();
    const close = (e: PointerEvent) => { if (!menu.current?.contains(e.target as Node)) onClose(); };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); }
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
        e.preventDefault(); const buttons = [...menu.current!.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
        const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
        buttons[e.key === "Home" ? 0 : e.key === "End" ? buttons.length - 1 : (current + (e.key === "ArrowUp" ? -1 : 1) + buttons.length) % buttons.length]?.focus();
      }
    };
    document.addEventListener("pointerdown", close); document.addEventListener("keydown", key); window.addEventListener("resize", onClose);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", key); window.removeEventListener("resize", onClose); previous?.focus(); };
  }, [onClose]);
  return createPortal(<div ref={menu} tabIndex={-1} className="pt-calendar-context-menu" role="menu" aria-label="Naptári műveletek" style={{ left: Math.max(8, Math.min(target.x, window.innerWidth - 244)), top: Math.max(8, Math.min(target.y, window.innerHeight - (onAddWorkout ? 210 : 170))) }}>
    {onAddWorkout && <button type="button" role="menuitem" onClick={onAddWorkout}>Új saját edzés…</button>}
    <button type="button" role="menuitem" disabled={disabled} onClick={onAdd}>Új idősáv…</button>
    {target.event && <button type="button" role="menuitem" disabled={slot && disabled} onClick={onEdit}>{slot ? "Idősáv szerkesztése…" : "Edzés részletei…"}</button>}
    {slot && <button type="button" role="menuitem" disabled={disabled} onClick={onRemove}>Idősáv elhagyása…</button>}
  </div>, document.body);
}
