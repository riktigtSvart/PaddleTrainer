"use client";
import { useEffect, useRef, useState } from "react";
import type { SetStateAction } from "react";
import { canonical } from "@/lib/planning-cycles/contracts";
import { scheduleContent } from "@/lib/training-options/synchronization";
import { initialScheduleDraft, readScheduleDraft, reconcileScheduleDraft, scheduleDraftDirty, scheduleDraftKey, writeScheduleDraft } from "@/lib/training-options/schedule-draft";
import type { ScheduleDraft } from "@/lib/training-options/schedule-draft";
import type { OptionsData, WeeklySlot } from "@/lib/training-options/contracts";

type View = { key: string | null; value: ScheduleDraft; ready: boolean; blocked: boolean; notice: string };

/** Tab-scoped input recovery. Reads and restores never submit a server write. */
export function useScheduleDraft(data: OptionsData, today: string, owner?: string) {
  const zone = data.timezone_name, key = scheduleDraftKey(owner, zone);
  const [view, setView] = useState<View>(() => ({ key, value: initialScheduleDraft(data, today), ready: !key, blocked: false, notice: "" }));
  const current = useRef(view), inputs = useRef({ data, today });
  useEffect(() => { inputs.current = { data, today }; }, [data, today]);
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active || !key || !owner) return;
      const { data, today } = inputs.current;
      let value = initialScheduleDraft(data, today), blocked = false, notice = "";
      try {
        const raw = sessionStorage.getItem(key);
        if (raw !== null) {
          value = reconcileScheduleDraft(readScheduleDraft(raw, owner, zone), data, today);
          if (scheduleDraftDirty(value) || value.editing)
            notice = "A korábbi helyi piszkozat visszatöltve, a nyitott időablakkal együtt. Ez még nem szervermentés.";
          else sessionStorage.removeItem(key);
        }
      } catch {
        blocked = true;
        notice = "A helyi órarend-piszkozat nem olvasható. A szerver mentett adatai látszanak; a korábbi helyi bejegyzést nem írtuk felül.";
      }
      const next = { key, value, ready: true, blocked, notice };
      current.current = next; setView(next);
    });
    return () => { active = false; };
  }, [key, owner, zone]);

  function persist(value: ScheduleDraft) {
    if (!key || !owner) return "";
    try {
      if (scheduleDraftDirty(value) || value.editing) sessionStorage.setItem(key, writeScheduleDraft(value, owner, zone));
      else sessionStorage.removeItem(key);
      return "";
    } catch {
      return "A böngésző nem tudja megőrizni a helyi piszkozatot. Frissítés előtt mentsd az érvényes órarendet a szerverre.";
    }
  }
  function commit(value: ScheduleDraft, notice = "") {
    const warning = persist(value);
    const next = { key, value, ready: true, blocked: false, notice: warning || notice };
    current.current = next; setView(next);
  }
  useEffect(() => {
    const before = current.current;
    if (before.key !== key || !before.ready || before.blocked) return;
    const value = reconcileScheduleDraft(before.value, data, today);
    if (value === before.value || canonical(value) === canonical(before.value)) return;
    // A fresh verified source may retire already saved input, or refresh a
    // clean form. A dirty conflicting form is retained by reconciliation.
    let notice = before.notice;
    try {
      if (key && owner) {
        if (scheduleDraftDirty(value) || value.editing) sessionStorage.setItem(key, writeScheduleDraft(value, owner, zone));
        else { sessionStorage.removeItem(key); notice = ""; }
      }
    } catch { notice = "A helyi piszkozat frissítése nem sikerült; az órarend továbbra is szerkeszthető."; }
    const next = { ...before, value, notice };
    current.current = next; setView(next);
  }, [data, today, key, owner, zone, view.value, view.ready, view.blocked]);

  const state = view.value;
  const ready = view.key === key && view.ready && !view.blocked;
  const dirty = scheduleDraftDirty(state);
  function setDraft(change: SetStateAction<OptionsData>) {
    const before = current.current;
    if (before.key !== key || !before.ready || before.blocked) return;
    const full = { ...data, ...before.value.draft };
    const next = typeof change === "function" ? change(full) : change;
    commit({ ...before.value, draft: scheduleContent(next) });
  }
  function setEditing(change: SetStateAction<WeeklySlot | null>) {
    const before = current.current;
    if (before.key !== key || !before.ready || before.blocked) return;
    commit({ ...before.value, editing: typeof change === "function" ? change(before.value.editing) : change });
  }
  function saved(submitted: OptionsData) {
    const before = current.current;
    // Never erase edits made after the submitted snapshot.
    if (before.value.editing || canonical(before.value.draft) !== canonical(scheduleContent(submitted))) return;
    commit(initialScheduleDraft(submitted, today));
  }
  return {
    draft: { ...data, ...state.draft }, editing: state.editing, setDraft, setEditing, dirty, ready, loaded: view.key === key && view.ready,
    conflict: canonical(scheduleContent(data)) !== canonical(state.source) && (dirty || !!state.editing),
    notice: view.notice, blocked: view.blocked,
    discard: () => commit(initialScheduleDraft(data, today)), saved,
  };
}
