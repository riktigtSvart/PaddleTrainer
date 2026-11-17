"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Span } from "@/lib/calendar/contracts";
import { defaultVisibility, readVisibility, visibilityKey, writeVisibility } from "@/lib/calendar/visibility";
import type { Visibility, VisibilityLayer, WeekStart } from "@/lib/calendar/visibility";

type State = { key: string | null; value: Visibility; ready: boolean; notice: string };
export function useVisibility(owner: string | null, span: Span) {
  const key = visibilityKey(owner, span);
  const [state, setState] = useState<State>(() => ({ key: null, value: defaultVisibility(), ready: false, notice: "" }));
  const current = useRef(state);
  useEffect(() => {
    let active = true;
    const read = () => {
      if (!active || !key || !owner) return;
      let next: State;
      try { next = { key, value: readVisibility(localStorage.getItem(key), owner, span), ready: true, notice: "" }; }
      catch { next = { key, value: defaultVisibility(), ready: true, notice: "A nézet korábbi beállításait nem sikerült visszaolvasni. Most az alapbeállítások látszanak." }; }
      current.current = next; setState(next);
    };
    queueMicrotask(read);
    const storage = (event: StorageEvent) => { if (event.storageArea === localStorage && (event.key === key || event.key === null)) read(); };
    window.addEventListener("storage", storage);
    return () => { active = false; window.removeEventListener("storage", storage); };
  }, [key, owner, span]);
  const update = useCallback((change: (value: Visibility) => Visibility) => {
    const before = current.current;
    if (!key || !owner || before.key !== key || !before.ready) return;
    const value = change(before.value);
    let notice = "";
    try { localStorage.setItem(key, writeVisibility(owner, span, value)); }
    catch { notice = "A böngésző nem engedi a nézet beállításainak mentését. A választás ebben a megnyitásban használható."; }
    const next = { key, value, ready: true, notice }; current.current = next; setState(next);
  }, [key, owner, span]);
  const value = useMemo(() => state.key === key ? state.value : defaultVisibility(), [state, key]);
  const layers = useMemo(() => ({ ...value.layers, training: true }), [value]);
  return { layers, meals: value.meals ?? true, setMeals: (meals:boolean) => update(v=>({...v,meals})), fullDay: value.fullDay, cycleLoad: value.cycleLoad, weekStart:value.weekStart??"monday", ready: state.key === key && state.ready,
    notice: state.key === key ? state.notice : "",
    setLayer: (layer: VisibilityLayer, checked: boolean) => update(v => ({ ...v, layers: { ...v.layers, [layer]: checked } })),
    setFullDay: (fullDay: boolean) => update(v => ({ ...v, fullDay })),
    setCycleLoad: (cycleLoad: boolean) => update(v => ({ ...v, cycleLoad })),
    setWeekStart: (weekStart:WeekStart) => update(v=>({...v,weekStart})),
  };
}
