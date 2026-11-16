"use client";
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { loadContext } from "@/lib/athlete-setup/client";
import { CycleHTTPError, loadCatalog, loadDetail, loadPage, preview, send } from "@/lib/planning-cycles/client";
import { canonical, draftIssues, normalizeProgram, PENDING_KEY, readPending } from "@/lib/planning-cycles/contracts";
import type { Catalog, Competition, Detail, Mode, Pending, Program, Receipt } from "@/lib/planning-cycles/contracts";
import { currentGoalPrograms, effectiveProgram, goalFrame, newSportGoal, replacementProgram, sportGoalModes } from "@/lib/planning-data/sport-goals";
import { withEventDemands } from "@/lib/planning-cycles/event-demands";
import { LOCAL_REFRESH_EVENT } from "@/lib/data-connections/preferences";
import { buttonClass, Field, secondaryClass, Select } from "@/components/planning-goals/fields";
import CompetitionEditor from "@/components/planning-cycles/competition-editor";
import GoalEditor, { newGoal } from "@/components/planning-cycles/goal-editor";
import StructureEditor from "@/components/planning-cycles/structure-editor";
import GoalWorkspace from "@/components/planning-goals/workspace";
import { BlockSaveFooter, BlockSaveProvider, SaveActionButton } from "./save-actions";

const message = (error: unknown) => error instanceof Error ? error.message : "A célkitűzés nem menthető.";
const endOf = (p: Program) => p.macrocycles.map((m) => m.end_date).sort().at(-1) ?? p.end_date ?? "";

function ProgramCard({ initial, source, catalog, locked, id, onSave, onDirty, onDiscard, onReload }: {
  initial: Program; source: Detail | null; catalog: Catalog; locked: boolean; id: string;
  onSave: (value: Program, source: Detail | null, id: string) => Promise<void>;
  onDirty: (id: string, value: boolean) => void; onDiscard?: () => void; onReload?: () => void;
}) {
  const [draft, setDraft] = useState(initial), [end, setEnd] = useState(endOf(initial)), [error, setError] = useState("");
  const [strategyOpen, setStrategyOpen] = useState(false), [strategyMacro, setStrategyMacro] = useState("");
  const formId = useId();
  const baseline = source ? effectiveProgram(source) : initial;
  const dirty = canonical(draft) !== canonical(baseline) || end !== endOf(baseline);
  useEffect(() => { onDirty(id, dirty); }, [id, dirty, onDirty]);
  const edit = (patch: Partial<Program>) => { setDraft((old) => ({ ...old, ...patch })); setError(""); };
  function events(competitions: Competition[]) {
    const keys = new Set(competitions.map((v) => v.key));
    edit({ competitions, goals: draft.goals.map((g) => g.details ? { ...g, details: { ...g.details, event_keys: g.details.event_keys.filter((v) => keys.has(v)) } } : g) });
  }
  const framed = draft;
  function timeline(next: Program, finish: string) {
    setEnd(finish); setError("");
    try { setDraft(goalFrame(next, finish)); } catch { setDraft({ ...next, end_date: next.mode === "recreation" ? null : finish }); }
  }
  async function submit() {
    try {
      const value = { ...draft, goals: draft.goals.filter((goal) => !["weight_loss", "weight_maintenance"].includes(goal.key)), end_date: draft.mode === "recreation" ? null : end }, issue = draftIssues(value, end, 3)[0];
      if (issue) throw Error(issue.message);
      await onSave(normalizeProgram(withEventDemands(value)), source, id);
    } catch (e) { setError(message(e)); }
  }
  const periods = source?.boundary_revisions.at(-1)?.artifact.periods ?? source?.program.artifact.periods ?? [];
  const macros = periods.filter((v) => v.period_type === "MACROCYCLE");
  const macroId = strategyMacro || macros.find((v) => v.end_date >= catalog.local_today)?.id || macros[0]?.id || "";
  return <BlockSaveProvider><div className="pt-goal-editor">
    {error && <p role="alert">{error}</p>}
    <form id={formId} onInvalidCapture={(event) => { let parent = (event.target as HTMLElement).closest("details"); while (parent) { parent.open = true; parent = parent.parentElement?.closest("details") ?? null; } }} onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <fieldset disabled={locked} className="space-y-5">
        <div className="pt-goal-dates grid gap-4 sm:grid-cols-2">
          <Field label={`${sportGoalModes[draft.mode]} kezdete`} name="program_start_date" type="date" required value={draft.start_date} onChange={(e) => timeline({ ...draft, start_date: e.target.value }, end)} />
          <Field label={draft.mode === "recreation" ? "Az aktuális rekreációs makrociklus vége" : `${sportGoalModes[draft.mode]} vége`} name="program_end_date" type="date" required value={end} onChange={(e) => timeline(draft, e.target.value)} />
        </div>
        {draft.mode === "recreation" && <p className="pt-options-meta">A rekreáció hosszú távon folytatható. A zárónap a most megtervezett makrociklust határolja.</p>}
        <details className="pt-goal-basics" open={!source ? true : undefined}><summary>Célkitűzés neve és sportága</summary><div className="grid gap-4 sm:grid-cols-2 mt-4">
          <Field label="Célkitűzés neve" required maxLength={200} value={draft.title} onChange={(e) => edit({ title: e.target.value })} />
          <Field label="A felkészülés fő sportága" required maxLength={200} value={draft.sport} onChange={(e) => edit({ sport: e.target.value })} />
          {draft.mode === "olympic" && <Select label="Olimpiai játékok" value={draft.olympic_key ?? ""} onChange={(e) => { const edition = catalog.olympics.find((v) => v.key === e.target.value); if (edition) timeline({ ...draft, olympic_key: edition.key }, edition.end_date); }}>{catalog.olympics.map((v) => <option key={v.key} value={v.key}>{v.title}</option>)}</Select>}
        </div></details>
        <section className="pt-goal-subsection"><h4>Versenycélok</h4>
          {!draft.competitions.length && <p className="pt-options-meta">Még nincs megadott verseny.</p>}
          <CompetitionEditor value={draft.competitions} change={events} sport={draft.sport} structured />
        </section>
        <section className="pt-goal-subsection"><h4>Edzéscélok</h4>{draft.goals.some((goal) => ["weight_loss", "weight_maintenance"].includes(goal.key)) && <p className="pt-options-meta">A korábbi testsúlycél a táplálkozási résznél átvehető. <Link className="underline" href="/nutrition#body-goals">Testsúlycél megnyitása</Link></p>}
          {draft.goals.filter((goal) => !["weight_loss", "weight_maintenance"].includes(goal.key)).map((goal) => <div key={goal.key} className="pt-training-goal-card"><h5>{catalog.goals[goal.key] ?? goal.key}</h5><GoalEditor value={goal} events={draft.competitions} onChange={(value) => edit({ goals: draft.goals.map((g) => g.key === goal.key ? value : g) })} /><button className={secondaryClass} type="button" onClick={() => edit({ goals: draft.goals.filter((g) => g.key !== goal.key) })}>Edzéscél törlése</button></div>)}
          <div className="pt-goal-add grid gap-3 sm:grid-cols-2"><Select label="Hozzáadható edzéscél" value="" onChange={(e) => { if (e.target.value) edit({ goals: [...draft.goals, newGoal(e.target.value)] }); }}><option value="">Válassz edzéscélt…</option>{Object.entries(catalog.goals).filter(([key]) => !["weight_loss", "weight_maintenance"].includes(key) && !draft.goals.some((g) => g.key === key)).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</Select></div>
        </section>
      </fieldset>
    </form>
    {source && <details className="pt-goal-strategy-details" onToggle={(event) => setStrategyOpen(event.currentTarget.open)}><summary>Ciklusonkénti fejlesztési célok</summary>
      {dirty ? <p className="pt-options-meta">Előbb mentsd a célkitűzés mostani változtatásait; a ciklusonkénti célokat a mentett időkerethez adhatod meg.</p> : strategyOpen && <BlockSaveProvider><div className="space-y-4">
        {macros.length > 1 && <Select label="Fejlesztési célok makrociklusa" value={macroId} onChange={(e) => setStrategyMacro(e.target.value)}>{macros.map((v) => <option key={v.id} value={v.id}>{v.title} · {v.start_date} – {v.end_date}</option>)}</Select>}
        <GoalWorkspace key={macroId} initialCycle={source.program.artifact.artifact_id} initialPeriod={macroId} strategyOnly />
        <BlockSaveFooter emptyHint="A fejlesztési célok szerkesztésének megnyitása után itt menthetsz." />
      </div></BlockSaveProvider>}
    </details>}
    <details className="pt-goal-mesocycles"><summary>Automatikusan létrehozott mezociklusok · {framed.macrocycles.reduce((n, v) => n + v.mesocycles.length, 0)} blokk</summary>
      <p className="pt-options-meta">A dátumok kezdeti felosztást jelentenek. Az időkeret átírásakor új felosztási javaslat készül.</p>
      <fieldset disabled={locked}><StructureEditor value={framed} change={setDraft} invalid={setError} /></fieldset>
    </details>
    {source && dirty && <p className="pt-options-meta">A módosítás mentése után a ciklusonkénti célokat újra át kell nézni. A már naplózott edzések megmaradnak.</p>}
    <SaveActionButton type="submit" form={formId} saveLabel="Célkitűzés mentése" saveHint={source ? dirty ? "A módosított célokat és időkeretet menti." : "A mentett célkitűzéshez képest még nincs változtatás." : "A célkitűzést, versenyeket és edzéscélokat együtt menti."} disabled={locked || (!!source && !dirty)} className={buttonClass}>Célkitűzés mentése</SaveActionButton>
    <BlockSaveFooter emptyHint="Célkitűzés betöltése…" />
    <div className="pt-data-actions">
      {onDiscard && <button className={secondaryClass} type="button" disabled={locked} onClick={onDiscard}>Új célkitűzés elvetése</button>}
      {source && dirty && <button className={secondaryClass} type="button" disabled={locked} onClick={() => { setDraft(baseline); setEnd(endOf(baseline)); setError(""); }}>Változtatások elvetése</button>}
      {onReload && <button className={secondaryClass} type="button" disabled={locked} onClick={onReload}>Mentett változat újraolvasása</button>}
    </div>
  </div></BlockSaveProvider>;
}

export default function SportGoalsWorkspace({ owner, sport, selected, onSelected, onDirtyChange }: {
  owner: string; sport: string; selected: Detail | null; onSelected: (detail: Detail) => void; onDirtyChange: (dirty: boolean) => void;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null), [rows, setRows] = useState<Receipt[]>([]), [hasMore, setHasMore] = useState(false), [offset, setOffset] = useState(0);
  const [details, setDetails] = useState<Record<string, Detail>>(() => selected ? { [selected.program.artifact.artifact_id]: selected } : {});
  const [detailEditions, setDetailEditions] = useState<Record<string, number>>({});
  const [expanded, setExpanded] = useState(selected?.program.artifact.artifact_id ?? ""), [newDrafts, setNewDrafts] = useState<Program[]>([]);
  const [recoveredSources, setRecoveredSources] = useState<Record<string, Detail>>({});
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [busy, setBusy] = useState(false), [paging, setPaging] = useState(false), [reload, setReload] = useState(0);
  const [pending, setPending] = useState<Pending | null>(null), [ready, setReady] = useState(false), [blocked, setBlocked] = useState(false), [rejected, setRejected] = useState(false), [dirtyIds, setDirtyIds] = useState<Set<string>>(new Set());
  const sending = useRef(false), preparing = useRef(false), selection = useRef(0);
  const dirty = useCallback((id: string, changed: boolean) => setDirtyIds((old) => { if (old.has(id) === changed) return old; const next = new Set(old); if (changed) next.add(id); else next.delete(id); return next; }), []);
  useEffect(() => { onDirtyChange(dirtyIds.size > 0 || newDrafts.length > 0 || !!pending || busy); }, [dirtyIds, newDrafts.length, pending, busy, onDirtyChange]);
  useEffect(() => {
    const abort = new AbortController();
    void Promise.all([loadCatalog(abort.signal), loadPage(0, abort.signal)]).then(([c, p]) => {
      if (p.items.some((v) => v.artifact.athlete_id !== owner)) throw Error("Másik sportoló célkitűzése érkezett.");
      if (!abort.signal.aborted) { setCatalog(c); setRows(p.items); setHasMore(p.has_more); setOffset(p.items.length); setError(""); }
    }).catch((e) => { if (!abort.signal.aborted) setError(message(e)); });
    return () => abort.abort();
  }, [owner, reload]);
  useEffect(() => {
    let active = true;
    queueMicrotask(() => { if (!active) return; try { const stored = sessionStorage.getItem(PENDING_KEY); if (stored) setPending(readPending(stored)); } catch { setBlocked(true); setError("A korábbi célmentés nem olvasható. A mentett célokat ellenőrizni kell."); } setReady(true); });
    return () => { active = false; };
  }, []);
  const locked = busy || !!pending || blocked || !ready;
  async function choose(row: Receipt, refresh = false) {
    const id = row.artifact.artifact_id, sequence = ++selection.current;
    if (refresh && dirtyIds.has(id) && !window.confirm("A célkitűzés el nem mentett változtatásait lecseréled a mentett adatokra?")) return;
    setExpanded(id);
    try {
      const detail = !refresh && details[id] ? details[id] : await loadDetail(id);
      if (sequence !== selection.current) return;
      if (detail.program.artifact.athlete_id !== owner) throw Error("Másik sportoló célkitűzése érkezett.");
      setDetails((v) => ({ ...v, [id]: detail })); if (refresh) { dirty(id, false); setDetailEditions((v) => ({ ...v, [id]: (v[id] ?? 0) + 1 })); } onSelected(detail); setError("");
    } catch (e) { if (sequence === selection.current) setError(message(e)); }
  }
  async function perform(request: Pending, sourceId?: string) {
    if (sending.current || blocked) return;
    sending.current = true; setBusy(true); setError(""); setRejected(false);
    let committed = false;
    try {
      sessionStorage.setItem(PENDING_KEY, JSON.stringify(request)); setPending(request);
      const receipt = await send(request);
      if (receipt.artifact.athlete_id !== owner) throw Error("A mentési visszaigazolás másik sportolóhoz tartozik.");
      sessionStorage.removeItem(PENDING_KEY); setPending(null); committed = true;
      const body = JSON.parse(request.body), id = request.operation === "programs" ? receipt.artifact.artifact_id : body.program_reference.artifact_id;
      if (request.operation === "programs") { setRows((v) => [receipt, ...v.filter((r) => r.artifact.artifact_id !== id)]); setNewDrafts((v) => v.filter((p) => p.program_id !== body.program_id && p.program_id !== sourceId)); }
      if (sourceId) dirty(sourceId, false);
      if (request.operation === "programs") { dirty(body.program_id, false); if (body.replacement) dirty(body.replacement.program_reference.artifact_id, false); }
      setExpanded(id); setNotice("A célkitűzés mentve.");
      const detail = await loadDetail(id); setDetails((v) => ({ ...v, [id]: detail })); onSelected(detail);
      window.dispatchEvent(new Event(LOCAL_REFRESH_EVENT));
    } catch (e) {
      setError(committed ? "A mentés sikerült, de a visszatöltés megszakadt. A mentett változat újraolvasható." : message(e));
      setRejected(!committed && e instanceof CycleHTTPError && [400, 403, 404, 405, 409, 413, 415, 422].includes(e.status));
    } finally { sending.current = false; setBusy(false); }
  }
  async function save(program: Program, source: Detail | null, id: string) {
    if (locked || sending.current || preparing.current) return;
    preparing.current = true;
    setBusy(true); setError(""); setNotice("");
    try {
      const context = await loadContext();
      if (context.athlete_id !== owner || !context.profile) throw Error("Előbb mentsd el a sportolói alapadatokat.");
      const profile = context.profile.artifact, availability = context.availability?.artifact;
      const proposal = replacementProgram(program, source, { profile_reference: { artifact_id: profile.artifact_id, content_hash: profile.content_hash }, availability_reference: availability ? { artifact_id: availability.artifact_id, content_hash: availability.content_hash } : null });
      await preview(proposal);
      setBusy(false); await perform({ schema_version: "cycle-pending-v0.1", operation: "programs", body: JSON.stringify(proposal) }, id);
    } catch (e) { setError(message(e)); setBusy(false); } finally { preparing.current = false; }
  }
  async function more() {
    if (paging) return;
    setPaging(true);
    try { const page = await loadPage(offset); if (page.items.some((v) => v.artifact.athlete_id !== owner)) throw Error("Másik sportoló célkitűzése érkezett."); setRows((v) => [...v, ...page.items.filter((r) => !v.some((p) => p.artifact.artifact_id === r.artifact.artifact_id))]); setHasMore(page.has_more); setOffset(offset + page.items.length); }
    catch (e) { setError(message(e)); } finally { setPaging(false); }
  }
  async function returnToEditing() {
    if (!pending || busy) return;
    setBusy(true);
    try {
      if (pending.operation === "programs") {
        const program = JSON.parse(pending.body) as Program;
        if (program.replacement) {
          const source = await loadDetail(program.replacement.program_reference.artifact_id);
          if (source.program.artifact.content_hash !== program.replacement.program_reference.content_hash || source.program.artifact.athlete_id !== owner) throw Error("A korábbi szerkesztés forrása eltér.");
          setRecoveredSources((v) => ({ ...v, [program.program_id]: source }));
        }
        setNewDrafts((v) => v.some((p) => p.program_id === program.program_id) ? v : [...v, program]);
      }
      sessionStorage.removeItem(PENDING_KEY); setPending(null); setRejected(false); setError("");
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  const programs = currentGoalPrograms(selected && !rows.some((v) => v.artifact.artifact_id === selected.program.artifact.artifact_id) ? [...rows, selected.program] : rows);
  return <div className="pt-sport-goals space-y-5">
    {error && <p role="alert">{error} {!catalog && <button type="button" className={secondaryClass} onClick={() => setReload((v) => v + 1)}>Betöltés újra</button>}</p>}
    {notice && <p role="status">{notice}</p>}
    {pending && <div className="pt-goal-pending"><p>A korábbi célmentés eredménye még ellenőrzésre vár.</p><button className={buttonClass} type="button" disabled={busy || blocked} onClick={() => void perform(pending)}>Mentés ellenőrzése és folytatása</button>{rejected && pending.operation === "programs" && <button className={secondaryClass} type="button" disabled={busy} onClick={() => void returnToEditing()}>Vissza a szerkesztéshez</button>}{pending.operation !== "programs" && <Link href="/planning-cycles">Korábbi verseny- vagy ciklusmódosítás megnyitása</Link>}</div>}
    <section className="pt-data-panel pt-new-sport-goal"><h3>Új cél kitűzése</h3><div className="pt-new-goal-buttons">{(Object.keys(sportGoalModes) as Mode[]).map((mode) => <button className={secondaryClass} key={mode} type="button" disabled={!catalog || locked} onClick={() => {
      if (!catalog) return;
      try { const { program } = newSportGoal(mode, catalog, sport); setNewDrafts((v) => [...v, program]); setExpanded(program.program_id);
        requestAnimationFrame(() => { const heading = document.getElementById(`goal-${program.program_id}`); heading?.scrollIntoView({ block: "start", behavior: "smooth" }); heading?.focus({ preventScroll: true }); });
      } catch (e) { setError(message(e)); }
    }}>{sportGoalModes[mode]}</button>)}</div></section>
    {!catalog && !error && <p role="status">Sportcélok betöltése…</p>}
    {catalog && programs.map((row) => {
      const p = row.artifact, id = p.artifact_id, detail = details[id], isOpen = expanded === id;
      return <section className="pt-sport-goal-card" key={id}><h3><button type="button" className="pt-goal-heading" aria-expanded={isOpen} aria-controls={`goal-content-${id}`} onClick={() => isOpen ? setExpanded("") : void choose(row)}>{p.proposal.title}<span>{sportGoalModes[p.proposal.mode]} · {p.proposal.start_date} – {endOf(p.proposal)}</span></button></h3>
        <div id={`goal-content-${id}`} hidden={!isOpen}>{detail ? <ProgramCard key={JSON.stringify([detail.program.artifact.content_hash, detail.competition_revisions.at(-1)?.artifact.content_hash, detail.boundary_revisions.at(-1)?.artifact.content_hash, detailEditions[id]])} initial={effectiveProgram(detail)} source={detail} catalog={catalog} locked={locked} id={id} onSave={save} onDirty={dirty} onReload={() => void choose(row, true)} /> : <p role="status">Célkitűzés betöltése…</p>}</div>
      </section>;
    })}
    {hasMore && <button type="button" className={secondaryClass} disabled={paging} onClick={() => void more()}>További célkitűzések betöltése</button>}
    {catalog && newDrafts.map((program) => <section className="pt-sport-goal-card is-new" key={program.program_id}><h3 id={`goal-${program.program_id}`} tabIndex={-1}>{recoveredSources[program.program_id] ? "Visszaállított szerkesztés" : "Új célkitűzés"} · {sportGoalModes[program.mode]}</h3><ProgramCard initial={program} source={recoveredSources[program.program_id] ?? null} catalog={catalog} locked={locked} id={program.program_id} onSave={save} onDirty={dirty} onDiscard={() => { setNewDrafts((v) => v.filter((p) => p.program_id !== program.program_id)); dirty(program.program_id, false); }} /></section>)}
  </div>;
}
