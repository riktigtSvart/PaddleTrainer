"use client";
import Link from 'next/link';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { expandedRange, loadCalendar, sourceContext } from '@/lib/nutrition/calendar';
import type { CalendarMeal, NutritionCalendar } from '@/lib/nutrition/calendar';
import type { Context } from '@/lib/nutrition/contracts';
import { slots } from '@/lib/nutrition/contracts';
import type { Entry } from '@/lib/nutrition/journal';
import { NUTRITION_CHANGED, nutritionChangeKey } from '@/lib/nutrition/events';
import { LOCAL_REFRESH_EVENT } from '@/lib/data-connections/preferences';
import { IntakeForm, MealJournalControls, useNutritionJournal } from './journal-workspace';
import { durationHMS } from '@/lib/duration';
import { mealTiming, timingLabel } from '@/lib/nutrition/timing';

type Selection = { calendar: NutritionCalendar; date: string; meal?: CalendarMeal };
type Layer = { enabled: boolean; error: string; loading: boolean; packets: NutritionCalendar[]; ensureRange: (start: string, end: string) => void; select: (s: Selection) => void; retry: () => void };
const ContextLayer = createContext<Layer | null>(null);
export function useNutritionLayerEnabled() { return useContext(ContextLayer)?.enabled ?? false; }
export function NutritionCalendarProvider({ owner, zone, start, end, enabled, children }: { owner: string | null; zone?: string; start: string; end: string; enabled: boolean; children: ReactNode }) {
  const [packets, setPackets] = useState<NutritionCalendar[]>([]), [error, setError] = useState(''), [busy, setBusy] = useState(0), [generation, setGeneration] = useState(0), [selection, setSelection] = useState<Selection | null>(null);
  const cache = useRef<NutritionCalendar[]>([]), counter=useRef(0), pending = useRef(new Map<number, { start: string; end: string; abort: AbortController }>());
  const invalidate = useCallback(() => { pending.current.forEach(p => p.abort.abort()); pending.current.clear(); cache.current = []; setPackets([]); setGeneration(n => n+1); }, []);
  const ensureRange = useCallback((from: string, to: string) => {
    if (!owner || !enabled || !from || !to) return;
    if (cache.current.some(p => p.athlete_id === owner && p.timezone===zone && p.start_date <= from && p.end_date >= to)) return;
    if ([...pending.current.values()].some(p => p.start <= from && p.end >= to)) return;
    let range;try{range=expandedRange(from,to);}catch{setError('Ehhez az időszakhoz az étkezések nem tölthetők be.');return;}
    const key=generation*1000000+(++counter.current),abort=new AbortController();
    pending.current.set(key, { ...range, abort }); setBusy(n => n+1); setError('');
    void loadCalendar(owner, range, abort.signal).then(p => { if (zone && p.timezone !== zone) throw Error('Az étkezések és az edzésnaptár időzónája eltér. Frissítsd az adatokat.'); if (!abort.signal.aborted) { cache.current = [...cache.current, p].slice(-12); setPackets(cache.current); } }).catch(e => { if (!abort.signal.aborted) setError(e instanceof Error ? e.message : 'Az étkezések nem tölthetők be.'); }).finally(() => { pending.current.delete(key); setBusy(n => Math.max(0,n-1)); });
  }, [owner, zone, enabled, generation]);
  useEffect(() => { let active=true;queueMicrotask(()=>{if(active)ensureRange(start,end);});return()=>{active=false;}; }, [start, end, ensureRange]);
  useEffect(() => { const requests=pending.current;return () => { requests.forEach(p => p.abort.abort()); requests.clear(); }; }, [owner, zone, enabled]);
  useEffect(() => {
    const changed = (e: Event) => { if ((e as CustomEvent).detail?.owner === owner) invalidate(); };
    const stored = (e: StorageEvent) => { if (owner && e.key === nutritionChangeKey(owner)) invalidate(); };
    window.addEventListener(NUTRITION_CHANGED, changed); window.addEventListener('storage', stored); window.addEventListener(LOCAL_REFRESH_EVENT, invalidate);
    return () => { window.removeEventListener(NUTRITION_CHANGED, changed); window.removeEventListener('storage', stored); window.removeEventListener(LOCAL_REFRESH_EVENT, invalidate); };
  }, [owner, invalidate]);
  return <ContextLayer.Provider value={{ enabled, packets: packets.filter(p => p.athlete_id === owner && p.timezone===zone), error, loading: busy > 0, ensureRange, select: setSelection, retry: invalidate }}>{children}{selection && selection.calendar.athlete_id === owner && selection.calendar.timezone===zone && <MealCalendarDialog key={`${selection.date}/${selection.meal?.slot ?? 'day'}`} selection={selection} close={() => setSelection(null)} />}</ContextLayer.Provider>;
}
export function NutritionRangeLoader({ start, end }: { start: string; end: string }) {
  const layer = useContext(ContextLayer), ensureRange = layer?.ensureRange;
  useEffect(() => { ensureRange?.(start, end); }, [start, end, ensureRange]);
  return null;
}
export function NutritionCalendarNotice() {
  const layer = useContext(ContextLayer);if (!layer?.enabled) return null;
  return <>{layer.error && <p className="pt-message is-error" role="alert">{layer.error} <button className="pt-button" onClick={layer.retry}>Étkezések újraolvasása</button></p>}{layer.loading && <p className="pt-notice" role="status">Étkezések betöltése…</p>}</>;
}
export function CalendarMealsDay({ date, compact = false }: { date: string; compact?: boolean }) {
  const layer = useContext(ContextLayer); if (!layer?.enabled) return null;
  const calendar = [...layer.packets].reverse().find(p => p.start_date <= date && p.end_date >= date); if (!calendar) return null;
  const meals = calendar.result.days.find(d => d.date === date)?.meals ?? [], actual = calendar.result.actual_entries.filter(e => e.date === date && e.status === 'eaten');
  if (compact) return <div className="pt-calendar-meals is-compact" onDoubleClick={e => e.stopPropagation()} onContextMenu={e => e.stopPropagation()}><button type="button" onClick={e => { e.stopPropagation(); layer.select({ calendar, date }); }} aria-label={`Étkezések · ${date} · ${meals.length} tervezett · ${actual.length} naplózott`}>Étkezések · {meals.length} terv · {actual.length} napló</button></div>;
  return <div className="pt-calendar-meals" onDoubleClick={e => e.stopPropagation()} onContextMenu={e => e.stopPropagation()}>{meals.map(m => <button key={m.slot} type="button" data-nutrition-meal={`${date}/${m.slot}`} className={m.status === 'eaten' ? 'is-eaten' : ''} title={m.title+(m.timing?' · '+timingLabel(m.timing):'')} aria-label={`${date} · ${m.planned_time ?? 'Időpont nélkül'} · ${slots[m.slot]} · ${m.title}`} onClick={e => { e.stopPropagation(); layer.select({ calendar, date, meal: m }); }}>{m.planned_time?.slice(0,5) ?? '–:–'} · {slots[m.slot]}{m.status === 'eaten' ? ' ✓' : m.status === 'skipped' ? ' · kihagyva' : m.different_report ? ' · más étel naplózva' : ''}</button>)}<button type="button" onClick={e => { e.stopPropagation(); layer.select({ calendar, date }); }}>Étkezési napló{actual.length ? ` · ${actual.length}` : ''} / hozzáadás</button></div>;
}
function MealCalendarDialog({ selection, close }: { selection: Selection; close: () => void }) {
  const { calendar, date } = selection, [chosen, setChosen] = useState(selection.meal), [editing, setEditing] = useState<Entry>(), [newEntry,setNewEntry]=useState<Entry>();
  const menu = useMemo<Context>(() => chosen ? sourceContext(calendar, chosen) : { schema_version: 'nutrition-workspace-v0.1', athlete_id: calendar.athlete_id, local_today: calendar.journal.local_today, catalog: calendar.catalog, saved: null, reference: null, content_hash: calendar.content_hash, timing_context:calendar.timing_context }, [calendar, chosen]);
  const store = useNutritionJournal(menu, calendar.journal), dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { const node = dialog.current, before = document.activeElement as HTMLElement | null; node?.showModal(); return () => { node?.close(); before?.focus(); }; }, []);
  const meals = calendar.result.days.find(d => d.date === date)?.meals ?? [], actual = store.data.entries.filter(e => e.date === date);
  const recipe = chosen ? calendar.catalog.recipes.find(r => r.id === chosen.recipe_id) : null;
  const hint=chosen?mealTiming(menu,store.data,chosen):null;
  return <dialog ref={dialog} className="pt-meal-calendar-dialog" aria-label="Étkezés a naptárban" onCancel={e => { e.preventDefault(); close(); }} onClick={e => { if (e.target === e.currentTarget) { const r=e.currentTarget.getBoundingClientRect(); if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)close(); } }}><header><div><p>{date} · Étkezés és napló</p><h2>{recipe?.title ?? 'Napi étkezések'}</h2></div><button type="button" className="pt-button" onClick={close}>Bezárás ×</button></header>
    {store.error && <p role="alert" className="pt-warning">{store.error}</p>}{store.notice && <p role="status">{store.notice}</p>}{store.pending && <button type="button" className="pt-button" onClick={() => void store.transmit(store.pending!)}>Mentés eredményének ellenőrzése</button>}
    {chosen && recipe ? <><p>{(hint?hint.time:chosen.planned_time) ?? 'Tervezett időpont nincs megadva'} · Saját tervezett adag: {chosen.portion_factor} × receptadag</p><MealJournalControls store={store} meal={chosen} />{store.dirty && <button type="button" className="pt-button" disabled={store.locked} onClick={() => void store.save()}>Időpontváltoztatás mentése</button>}<details><summary>Alapanyagok és elkészítés</summary><p>Elkészítési idő: {durationHMS(recipe.prep_minutes*60)}. Az alábbi alapanyagok egy receptadaghoz tartoznak.</p><ul>{recipe.ingredients.map(i => <li key={i.food_id}>{calendar.catalog.foods.find(f => f.id === i.food_id)!.name}: {i.quantity} {calendar.catalog.foods.find(f => f.id === i.food_id)!.unit}</li>)}</ul><ol>{recipe.steps.map(s => <li key={s}>{s}</li>)}</ol></details><button type="button" className="pt-button" onClick={() => setChosen(undefined)}>Az összes napi étkezés</button></> : <>{meals.map(m => <button type="button" key={m.slot} className="pt-meal-calendar-choice" onClick={() => { setChosen(m); setNewEntry(undefined);setEditing(undefined); }}><strong>{m.planned_time ?? 'Időpont nélkül'} · {slots[m.slot]}</strong><span>{m.title}</span></button>)}<h3>Tényleges étkezések</h3>{actual.length === 0 && <p>Ehhez a naphoz még nincs visszajelzés. Ez nem nulla bevitel.</p>}{actual.map(e => <article key={e.id}><strong>{e.title}</strong><p>{e.time ?? 'Kihagyva'} · {e.amount} {e.unit === 'portion' ? 'saját adag' : e.unit}</p><button className="pt-button" disabled={store.locked} onClick={() => { setEditing({ ...e, status: 'eaten', amount: e.amount === '0' ? '1' : e.amount });setNewEntry(undefined); }}>Javítás</button></article>)}<button type="button" className="pt-button" disabled={store.locked || date > calendar.journal.local_today} onClick={() => { setNewEntry(newEntry?undefined:{ id: crypto.randomUUID(), date, time: null, timezone: calendar.timezone, fold: null, status: 'eaten', title: '', amount: '1', unit: 'portion', recipe_id: null, source: null, note: '', satisfaction: null }); setEditing(undefined); }}>Étkezés hozzáadása erre a napra</button></>}
    {(newEntry || editing) && <IntakeForm key={editing?.id ?? newEntry!.id} store={store} initial={editing ?? newEntry} onDone={() => {setNewEntry(undefined);setEditing(undefined);}} />}
    <p><Link href="/nutrition#intake-journal">Teljes étkezési napló és étrendtervező →</Link></p>
  </dialog>;
}
