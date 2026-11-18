"use client";
import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import { canonical } from '@/lib/planning-cycles/contracts';
import { blankNutritionData, civilDay, diets, eligibleRecipes, generatePlan, loadNutrition, NutritionHTTPError, pendingKey, projectNutrition, readPending, saveNutrition, shoppingText, slots, validPantryQuantity } from '@/lib/nutrition/contracts';
import { durationHMS } from '@/lib/duration';
import { JournalWorkspace, MealJournalControls, useNutritionJournal } from './journal-workspace';
import { mealTiming } from '@/lib/nutrition/timing';
import { applyFoodFeedback, plannedTime } from '@/lib/nutrition/journal';
import type { Context, Meal, NutritionData, Preferences, Projection } from '@/lib/nutrition/contracts';
import { draftKey, readDraft, sameReference } from '@/lib/nutrition/draft';
import { notifyNutrition } from '@/lib/nutrition/events';
import { SavedRequirements } from './requirements-panel';

const message = (e: unknown) => e instanceof Error ? e.message : 'A művelet nem sikerült.';
const pretty = (value: string) => value.replace('.', ',');

export default function MealWorkspace({ initialView = 'menu' }: { initialView?: 'menu' | 'shopping' }) {
  const [context, setContext] = useState<Context | null>(null), [data, setData] = useState<NutritionData>(blankNutritionData);
  const journal = useNutritionJournal(context);
  const [view, setView] = useState(initialView), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false), [pending, setPending] = useState<string | null>(null), [rejected, setRejected] = useState(false), [needsReload, setNeedsReload] = useState(false), [storageBlocked, setStorageBlocked] = useState(false);
  const [start, setStart] = useState(''), [count, setCount] = useState(7), [people, setPeople] = useState(1), [search, setSearch] = useState(''), [reload, setReload] = useState(0);
  const [allergenMode, setAllergenMode] = useState('unknown'), [pantryInputs, setPantryInputs] = useState<Record<string, string>>({});
  const [draftReady, setDraftReady] = useState(false);
  const exclusionPanel = useRef<HTMLDetailsElement>(null);
  const writing = useRef(false), alive = useRef(true);
  function install(c: Context, preserveDraft = false) {
    setContext(c); setNeedsReload(false);
    if (!preserveDraft) { const d = structuredClone(c.saved?.proposal.data ?? blankNutritionData()); setData(d); setPantryInputs({}); setAllergenMode(d.preferences.excluded_allergens.length ? 'specified' : d.preferences.allergens_reviewed ? 'none' : 'unknown'); setStart(d.plan?.start_date ?? c.local_today); setCount(d.plan?.day_count ?? 7); setPeople(d.plan?.people ?? 1); }
  }
  useEffect(() => {
    alive.current = true; const abort = new AbortController();
    void loadNutrition(abort.signal).then(c => {
      if (abort.signal.aborted) return;
      install(c);
      try { const raw = localStorage.getItem(pendingKey(c.athlete_id)); if (raw) { const restored = readPending(raw, c.catalog).data; setData(restored); setAllergenMode(restored.preferences.excluded_allergens.length ? 'specified' : restored.preferences.allergens_reviewed ? 'none' : 'unknown'); if (restored.plan) { setStart(restored.plan.start_date); setCount(restored.plan.day_count); setPeople(restored.plan.people); } setPending(raw); }
        else { const savedDraft=localStorage.getItem(draftKey(c.athlete_id)); if(savedDraft) { const d=readDraft(savedDraft,c.athlete_id,c.catalog);setData(d.data);setPantryInputs(d.pantry_inputs);setStart(d.start);setCount(d.count);setPeople(d.people);setAllergenMode(d.data.preferences.excluded_allergens.length?'specified':d.data.preferences.allergens_reviewed?'none':'unknown');if(!sameReference(d.base_reference,c.reference)&&canonical(d.data)!==canonical(c.saved?.proposal.data??blankNutritionData())){setNeedsReload(true);setNotice('A mentett étrend közben változott. A piszkozatod megmaradt; vedd át a friss állapotot.');}else setNotice('A korábbi piszkozatot visszaállítottuk.'); } } }
      catch { setStorageBlocked(true); setError('A korábbi étrendmentés nem olvasható. Őrizd meg a böngésző adatait; az eredményt ellenőrizni kell.'); }
      setDraftReady(true);
    }).catch(e => { if (!abort.signal.aborted) setError(message(e)); });
    return () => { alive.current = false; abort.abort(); };
  }, [reload]);
  const preview = useMemo(() => {
    if (!context) return { result: null, error: '' };
    try { return { result: projectNutrition(data, context.catalog), error: '' }; } catch (e) { return { result: null, error: message(e) }; }
  }, [context, data]);
  const dirty = !!context && canonical(data) !== canonical(context.saved?.proposal.data ?? blankNutritionData());
  const invalidPantry = Object.values(pantryInputs).some(value => !validPantryQuantity(value));
  const locked = busy || !!pending || needsReload || storageBlocked || !context;
  useEffect(()=>{
    if(!context||!draftReady||storageBlocked||needsReload)return;
    try { if(dirty||Object.keys(pantryInputs).length)localStorage.setItem(draftKey(context.athlete_id),JSON.stringify({schema_version:'nutrition-menu-draft-v0.1',owner:context.athlete_id,base_reference:context.reference,data,pantry_inputs:pantryInputs,start,count,people}));else localStorage.removeItem(draftKey(context.athlete_id)); }
    catch {queueMicrotask(()=>{if(alive.current)setError('A böngésző nem tudta megőrizni a piszkozatot. Mentsd el az étrendet az oldal elhagyása előtt.');});}
  },[context,draftReady,storageBlocked,needsReload,dirty,data,pantryInputs,start,count,people]);
  function preferences(change: Partial<Preferences>) { setData(old => ({ ...old, preferences: { ...old.preferences, ...change }, checked: [] })); setError(''); setNotice(''); }
  function editMeal(date: string, slot: Meal['slot'], change: Partial<Meal>) {
    setData(old => ({ ...old, checked: [], plan: old.plan ? { ...old.plan, meals: old.plan.meals.map(m => m.date === date && m.slot === slot ? { ...m, ...change } : m) } : null })); setNotice('');
  }
  function generate() {
    if (!context) return;
    if (invalidPantry) { setError('Előbb fejezd be az otthoni mennyiségek megadását a bevásárlólistán.'); return; }
    try { const result = generatePlan(context.catalog, data, start, count, people); setData(result); setError(''); setView('menu'); saveData(result); } catch (e) { setError(message(e)); }
  }
  async function transmit(body: string) {
    if (!context || writing.current || storageBlocked) return;
    writing.current = true; setBusy(true); setError(''); setNotice(''); setRejected(false);
    let committed = false;
    try {
      const key = pendingKey(context.athlete_id), stored = localStorage.getItem(key);
      if (stored && stored !== body) throw Error('Előbb ellenőrizd a korábbi étrendmentést.');
      localStorage.setItem(key, body); setPending(body);
      await saveNutrition(context.athlete_id, body, context.catalog); committed = true;
      notifyNutrition(context.athlete_id);
      if (localStorage.getItem(key) === body) localStorage.removeItem(key);
      if (!alive.current) return;
      setPending(null); setNeedsReload(true);
      install(await loadNutrition(undefined, context.athlete_id));
      setNotice('Az étrend és a bevásárlólista mentve. A naptárban és újranyitás után is elérhető.');
    } catch (e) {
      if (alive.current) { setError(committed ? 'A mentés sikerült, de a visszaolvasás megszakadt. Töltsd be a mentett változatot.' : message(e)); setRejected(!committed && e instanceof NutritionHTTPError && e.status >= 400 && e.status < 500); }
    } finally { writing.current = false; if (alive.current) setBusy(false); }
  }
  function saveData(next: NutritionData) {
    if (!context || locked || invalidPantry) return;
    projectNutrition(next,context.catalog);
    const body = JSON.stringify({ request_id: crypto.randomUUID(), previous_reference: context.reference, catalog_hash: context.catalog.content_hash, data:next });
    void transmit(body);
  }
  function save() {if(!preview.error)saveData(data);}
  async function readSaved(preserveDraft = false) {
    if (!context || writing.current || pending && !rejected) return;
    setBusy(true); setError('');
    try {
      const current = await loadNutrition(undefined, context.athlete_id);
      if (pending) { if (localStorage.getItem(pendingKey(context.athlete_id)) === pending) localStorage.removeItem(pendingKey(context.athlete_id)); setPending(null); setRejected(false); }
      install(current, preserveDraft); setNotice(preserveDraft ? 'A friss mentett állapotot átvettük, a piszkozatod megmaradt. Ellenőrizd, majd mentsd el.' : 'A mentett változat betöltve.');
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  async function copyList(result: Projection) {
    if (!context) return;
    try { await navigator.clipboard.writeText(shoppingText(result, context.catalog)); setNotice('A bevásárlólista a vágólapra került.'); } catch { setError('A böngésző nem engedte a másolást. A listát kijelölheted, vagy kinyomtathatod.'); }
  }
  return <div className="pt-meal-workspace">
    <header className="pt-meal-intro"><div><p className="pt-meal-eyebrow">Étrend és bevásárlás · <span data-app-release="C21.14">C21.14</span></p><h2>Tervezz előre néhány napra</h2><p>Egyszerű receptek, pontos alapanyaglista és együtt számolt adagok. A mennyiségek szerkeszthető kiinduló adagok.</p></div><Link href={initialView === 'shopping' ? '/nutrition' : '/shopping'} className="pt-button">{initialView === 'shopping' ? 'Táplálkozási oldal' : 'Bevásárlólista külön oldalon'}</Link></header>
    {error && <p className="pt-warning" role="alert">{error}</p>}{notice && <p className="pt-meal-notice" role="status">{notice}</p>}
    {!context && <p role="status">{error ? <button className="pt-button" onClick={() => { setError(''); setReload(v => v + 1); }}>Adatok újraolvasása</button> : 'Receptek és mentett étrend betöltése…'}</p>}
    {context && <>
      <div className="pt-meal-toolbar"><div className="pt-meal-tabs" role="group" aria-label="Táplálkozási nézet"><button className="pt-button" aria-pressed={view === 'menu'} onClick={() => setView('menu')}>Étrend</button><button className="pt-button" aria-pressed={view === 'shopping'} onClick={() => setView('shopping')}>Bevásárlólista</button></div><div className="pt-meal-actions"><span>{dirty ? 'Nem mentett változtatások' : context.saved ? 'Mentett állapot' : 'Még nincs mentett étrend'}</span><button className="pt-button pt-button-primary" disabled={locked || !dirty || !!preview.error || invalidPantry} onClick={save}>Módosítások mentése</button><button className="pt-button" disabled={busy || !!pending} onClick={() => void readSaved()}>Mentett változat betöltése</button></div></div>
      {pending && <section className="pt-panel pt-meal-pending" aria-label="Függő étrendmentés"><h3>{busy ? 'Mentés folyamatban…' : rejected ? 'A mentést a rendszer elutasította' : 'A mentés visszaigazolása szükséges'}</h3><p>A bevitt adatokat megőriztük. Az ellenőrzés ugyanazt a kérést használja.</p><button className="pt-button" disabled={busy || storageBlocked} onClick={() => void transmit(pending)}>Mentés eredményének ellenőrzése</button>{rejected && <button className="pt-button" disabled={busy} onClick={() => void readSaved(true)}>Friss adatok átvétele, piszkozat megtartása</button>}</section>}
      <fieldset disabled={locked} hidden={view === 'shopping' && !!data.plan} className="pt-meal-controls" id="preferences"><legend>Étrend beállításai</legend>
        <div className="pt-meal-grid"><label>Étrend típusa<select value={data.preferences.diet} onChange={e => preferences({ diet: e.target.value as Preferences['diet'] })}>{Object.entries(diets).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <label>Ételallergia és érzékenység<select value={allergenMode} onChange={e => { setAllergenMode(e.target.value); if (e.target.value === 'specified' && exclusionPanel.current) exclusionPanel.current.open = true; preferences({ allergens_reviewed: e.target.value === 'none' || e.target.value === 'specified' && data.preferences.excluded_allergens.length > 0, excluded_allergens: e.target.value === 'none' ? [] : data.preferences.excluded_allergens }); }}><option value="unknown">Még nem néztem át</option><option value="none">Nincs kizárandó allergén</option><option value="specified">Az alábbi listában választok</option></select></label>
          <label>Elkészítési idő ételenként<select value={data.preferences.max_prep_minutes} onChange={e => preferences({ max_prep_minutes: Number(e.target.value) })}>{[15, 30, 45, 60].map(n => <option key={n} value={n}>Legfeljebb {durationHMS(n * 60)}</option>)}</select></label>
          <label>Étkezések naponta<select value={data.preferences.meals_per_day} onChange={e => preferences({ meals_per_day: Number(e.target.value) })}><option value={3}>Reggeli, ebéd, vacsora</option><option value={4}>Három főétkezés és kisétkezés</option></select></label></div>
        <details ref={exclusionPanel} className="pt-meal-exclusions"><summary>Allergének és kerülendő alapanyagok {data.preferences.excluded_allergens.length + data.preferences.excluded_foods.length > 0 && `· ${data.preferences.excluded_allergens.length + data.preferences.excluded_foods.length} kizárás`}</summary><p>A kizárás az alapanyaglistát szűri. Csomagolt terméknél az összetevőket és a „nyomokban tartalmazhat” jelölést is ellenőrizd a címkén.</p><div className="pt-meal-checks">{Object.entries(context.catalog.allergens).map(([id, label]) => <label key={id}><input type="checkbox" checked={data.preferences.excluded_allergens.includes(id)} onChange={e => { const values = e.target.checked ? [...data.preferences.excluded_allergens, id] : data.preferences.excluded_allergens.filter(a => a !== id); setAllergenMode('specified'); preferences({ allergens_reviewed: values.length > 0, excluded_allergens: values }); }} />{label}</label>)}</div>
          <label>Alapanyag keresése<input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Például banán vagy csirke" /></label><div className="pt-meal-checks pt-meal-food-search">{context.catalog.foods.filter(f => f.name.toLocaleLowerCase('hu').includes(search.toLocaleLowerCase('hu'))).map(f => <label key={f.id}><input type="checkbox" checked={data.preferences.excluded_foods.includes(f.id)} onChange={e => preferences({ excluded_foods: e.target.checked ? [...data.preferences.excluded_foods, f.id] : data.preferences.excluded_foods.filter(a => a !== f.id) })} />{f.name}</label>)}</div></details>
        <div className="pt-meal-grid pt-meal-range"><label>Első nap<input type="date" value={start} min="1900-01-01" max="2100-12-31" onChange={e => setStart(e.target.value)} /></label><label>Napok száma<input type="number" min={1} max={14} value={count || ''} onChange={e => setCount(Number(e.target.value))} /></label><label>Hány főre?<input type="number" min={1} max={8} value={people || ''} onChange={e => setPeople(Number(e.target.value))} /></label><button type="button" className="pt-button pt-button-primary" onClick={generate}>Étrend tervezése és mentése a naptárba</button></div>
      </fieldset>
      <p className="pt-meal-note">Az étkezési időpontokat az app javasolja; a napi kézi beállításaid elsőbbséget kapnak. A mentés a kijelölt napok korábbi étrendjét felülírja. Más napok terve és a tényleges étkezési napló megmarad. Az edzések alapján automatikus energia- és tápanyagszámítás még nincs bekötve.</p>
      {needsReload && !pending && <p role="status">A piszkozatod megmaradt. <button className="pt-button" onClick={() => void readSaved(true)}>Friss adatok átvétele, piszkozat megtartása</button></p>}
      {preview.error && <p className="pt-warning" role="alert">{preview.error}</p>}{invalidPantry && <p className="pt-warning" role="alert">Az otthoni mennyiség félbehagyott vagy hibás. Legfeljebb három tizedesjegyet adj meg; az üres mező nulla készletet jelent.</p>}
      {view === 'menu' && <SavedRequirements owner={context.athlete_id} today={context.local_today} plan={context.saved?.proposal.data.plan} />}
      {preview.result && data.plan && <section id={view === 'menu' ? 'meal-plan' : 'shopping-options'} className="pt-meal-output"><div className="pt-meal-summary"><div><h2>{view === 'menu' ? 'A tervezett étkezések' : 'Közös bevásárlólista'}</h2><p>{data.plan.start_date} – {civilDay(data.plan.start_date, data.plan.day_count - 1)} · {data.plan.people} fő · {preview.result.meal_count} étkezés</p></div>{view === 'shopping' && <div className="pt-meal-actions"><button className="pt-button" disabled={invalidPantry || busy} onClick={() => void copyList(preview.result!)}>Lista másolása</button><button className="pt-button" disabled={invalidPantry || busy} onClick={() => window.print()}>Nyomtatás</button></div>}</div>
        {view === 'menu' ? <><button type="button" className="pt-button" disabled={locked || !journal.context?.saved?.proposal.data.entries.some(e => e.status === 'eaten' && e.recipe_id && e.satisfaction !== null && e.satisfaction !== 3)} onClick={() => { try { setData(applyFoodFeedback(data, context.catalog, journal.context!.saved!.proposal.data.entries)); setNotice('Az ételértékeléseid alapján új javaslat készült. Az adagok és a kizárások megmaradtak; nézd át, majd mentsd el.'); } catch (e) { setError(message(e)); } }}>Ételjavaslatok a visszajelzéseim alapján</button><p className="pt-meal-note">Az alapanyagok az összes személy teljes adagját mutatják. Az adagszorzó személyenként értendő; az ételcsere és az adagváltoztatás azonnal frissíti a bevásárlólistát.</p><div className="pt-meal-days">{preview.result.days.map(day => <section key={day.date} className="pt-meal-day"><h3>{new Intl.DateTimeFormat('hu-HU', { weekday: 'long', month: 'short', day: 'numeric', timeZone: 'UTC' }).format(new Date(day.date + 'T12:00:00Z'))}</h3><div className="pt-meal-cards">{day.meals.map(m => { const r = context.catalog.recipes.find(r => r.id === m.recipe_id)!; const pool = eligibleRecipes(context.catalog, data.preferences, m.slot);const hint=mealTiming(context,journal.data,m,day.meals.map(x=>x.slot)); return <article className="pt-meal-card" key={m.slot}><p className="pt-meal-eyebrow">{slots[m.slot]} · {journal.context ? (hint?hint.time:plannedTime(journal.data, day.date, m.slot)) ?? 'Időpont nincs megadva' : 'Időpont betöltése…'}</p><h4>{r.title}</h4><fieldset disabled={locked}><label>Másik étel · {slots[m.slot]} · {day.date}<select value={m.recipe_id} onChange={e => editMeal(day.date, m.slot, { recipe_id: e.target.value })}>{pool.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}</select></label><label>Adagszorzó · {slots[m.slot]} · {day.date}<select value={m.portion_factor} onChange={e => editMeal(day.date, m.slot, { portion_factor: e.target.value as Meal['portion_factor'] })}>{['0.5', '1', '1.5', '2'].map(n => <option key={n} value={n}>{pretty(n)} ×</option>)}</select></label></fieldset><MealJournalControls store={journal} meal={m} /><details><summary>Alapanyagok és elkészítés</summary><p>Elkészítési idő: {durationHMS(r.prep_minutes * 60)}</p><ul>{m.ingredients.map(i => { const f = context.catalog.foods.find(f => f.id === i.food_id)!; return <li key={i.food_id}>{f.name}: <strong>{pretty(i.quantity)} {f.unit}</strong></li>; })}</ul><ol>{r.steps.map(step => <li key={step}>{step}</li>)}</ol></details>{pool.length === 1 && <p className="pt-meal-note">Ehhez az étkezéshez egy recept illik a szűréshez; több napon ismétlődhet.</p>}</article>; })}</div></section>)}</div></> : <><p className="pt-meal-note">Az „Otthon van” mezőbe a most rendelkezésre álló mennyiséget írd. Ezt levonjuk az összesített szükségletből; darabos terméknél a vásárolandó mennyiséget egészre kerekítjük. A pipákat és a készletet a Módosítások mentése gomb őrzi meg.</p><div className="pt-meal-table-scroll"><table className="pt-meal-shopping"><thead><tr><th>Megvan</th><th>Alapanyag</th><th>Összesen kell</th><th>Otthon van</th><th>Vásárolandó</th></tr></thead><tbody>{Object.entries(context.catalog.categories).flatMap(([category, title]) => { const rows = preview.result!.shopping.filter(r => context.catalog.foods.find(f => f.id === r.food_id)!.category === category); return !rows.length ? [] : [<tr className="pt-meal-category" key={category}><th colSpan={5}>{title}</th></tr>, ...rows.map(r => { const f = context.catalog.foods.find(f => f.id === r.food_id)!; return <tr key={r.food_id} className={r.checked || r.to_buy === '0' ? 'pt-meal-supplied' : ''}><td><input type="checkbox" aria-label={`Beszerezve: ${f.name}`} disabled={locked || r.to_buy === '0'} checked={r.checked} onChange={e => { setNotice(''); setData(old => ({ ...old, checked: e.target.checked ? [...old.checked, r.food_id] : old.checked.filter(id => id !== r.food_id) })); }} /></td><th scope="row">{f.name}</th><td>{pretty(r.required)} {f.unit}</td><td><label><span className="pt-sr-only">Otthon van: {f.name} ({f.unit})</span><input disabled={locked} inputMode="decimal" aria-invalid={pantryInputs[f.id] !== undefined && !validPantryQuantity(pantryInputs[f.id]) || undefined} value={pantryInputs[f.id] ?? data.pantry[f.id] ?? ''} placeholder="0" onChange={e => { const value = e.target.value.trim().replace(',', '.'); setNotice(''); setPantryInputs(old => ({ ...old, [f.id]: value })); if (!validPantryQuantity(value)) return; setData(old => { const pantry = { ...old.pantry }; if (value === '') delete pantry[f.id]; else pantry[f.id] = value; return { ...old, pantry, checked: old.checked.filter(id => id !== f.id) }; }); }} /></label></td><td><strong>{pretty(r.to_buy)} {f.unit}</strong></td></tr>; })]; })}</tbody></table></div></>}
      </section>}
      {!data.plan && <section className="pt-panel pt-meal-empty"><h3>Néhány napra előre, egyetlen listával</h3><p>Nézd át az étrendi beállításokat, válaszd ki az időszakot és az adagok számát, majd kattints az Étrend tervezése és mentése a naptárba gombra.</p></section>}
      <div className="pt-meal-savebar"><span>{dirty ? 'Nem mentett étrendmódosítások' : context.saved ? 'Mentett étrend · a naptárban is elérhető' : 'Még nincs mentett étrend'}</span><button type="button" className="pt-button pt-button-primary" disabled={locked || !dirty || !!preview.error || invalidPantry} onClick={save}>{data.plan ? 'Mentés a naptárba' : 'Beállítások mentése'}</button><Link className="pt-button" href="/">Naptár és étkezési napló →</Link></div>
      {view === 'menu' && <JournalWorkspace store={journal} />}
      <details className="pt-meal-method"><summary>A receptek és az adagok háttere</summary><p>A receptkészlet változatos alapanyagokat használ. A megadott mennyiségek általános kiinduló adagok; az adagszorzóval alakíthatók. A napi számítás a mentett saját adagokat használja. Az ételeket és az adagokat az étrendkártyákon lehet módosítani.</p><p>A tárolás és a csomagoláson szereplő felhasználhatósági idő a többnapos vásárlásnál is számít. A receptek alapanyagaihoz a megadott állapotban (például szárazon vagy lecsöpögtetve) mérj.</p><ul>{context.catalog.sources.map(s => <li key={s.url}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></li>)}</ul></details>
    </>}
  </div>;
}
