"use client";
import { SaveActionButton } from "@/components/planning-data/save-actions";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  Field,
  buttonClass,
  secondaryClass,
} from "@/components/planning-goals/fields";
import { Choice } from "@/components/initial-assessment/fields";
import { newSet } from "@/lib/initial-assessment/contracts";
import {
  GuidedError,
  loadGuided,
  sendGuided,
  loadGuidedRevision,
} from "@/lib/guided-strength/client";
import {
  initialProgress,
  normalizeCommand,
  key,
  readCommand,
  readDraft,
  readPending,
  readReceipt,
  stopped,
} from "@/lib/guided-strength/contracts";
import type {
  Command,
  Context,
  Pending,
  Receipt,
  ExerciseResult,
} from "@/lib/guided-strength/contracts";
import { ref, same } from "@/lib/guided-strength/activity";
import SetFields from "./set-fields";
import GuidedPreparation from "./preparation";
import AssessmentWorkspace from "@/components/initial-assessment/workspace";
import { preserveLocalRecovery } from "@/lib/initial-assessment/recovery-backup";
import { ExerciseInstructions } from "./protocol-preview";
import CalibrationMovement, { MeasurementSummary } from "./calibration-movement";
import { protocolVersion, starterTargets } from "@/lib/guided-strength/calibration";
import {
  preparationLocation,
  retainedChoices,
  startIssues,
} from "@/lib/guided-strength/preparation";
function fromReceipt(r: Receipt): Command {
  return {
    ...structuredClone(r.artifact.proposal),
    action: "checkpoint",
    previous_reference: ref(r.artifact),
    reviewed: false,
  };
}
export function clockInput(iso: string, zone: string) {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("sv-SE", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date(iso))
      .map((v) => [v.type, v.value]),
  );
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}
export function clockInstant(value: string, zone: string) {
  const stamp = Date.parse(value + "Z");
  const matches: string[] = [];
  if (Number.isFinite(stamp))
    for (let m = -14 * 60; m <= 14 * 60; m += 15) {
      const iso = new Date(stamp + m * 60000).toISOString();
      if (clockInput(iso, zone) === value) matches.push(iso);
    }
  if (matches.length !== 1)
    throw Error(
      "Ez a helyi idő nem egyértelmű vagy nem létezik. Ellenőrizd a dátumot és az időt.",
    );
  return matches[0];
}
function Rest() {
  const [until, setUntil] = useState<number | null>(null),
    [now, setNow] = useState(0);
  useEffect(() => {
    if (until === null) return;
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, [until]);
  const remaining =
    until === null ? null : Math.max(0, Math.ceil((until - now) / 1000));
  return (
    <aside className="pt-guided-rest">
      <p>
        {remaining === null
          ? "A sorozatok között tarts legalább 2 perc nyugodt pihenőt."
          : remaining > 0
            ? `Pihenő · ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}`
            : "Letelt a 2 perc. Ha még szükséges, pihenj tovább."}
      </p>
      <button
        type="button"
        className={secondaryClass}
        onClick={() => {
          const n = Date.now();
          setNow(n);
          setUntil(n + 120000);
        }}
      >
        2 perces pihenő indítása
      </button>
    </aside>
  );
}
export type GuidedSelection = { place: string; ids: string[]; mode: "device" | "manual" };
export default function GuidedWorkspace({ embedded = false, onCompleted, onEditIntake, selection }: { embedded?: boolean; onCompleted?: () => void; onEditIntake?: (selection: GuidedSelection) => void; selection?: GuidedSelection } = {}) {
  const [context, setContext] = useState<Context | null>(null),
    [latest, setLatest] = useState<Receipt | null>(null),
    [draft, setDraft] = useState<Command | null>(null),
    [pending, setPending] = useState<Pending | null>(null);
  const [place, setPlace] = useState(""),
    [ids, setIds] = useState<string[]>([]),
    [mode, setMode] = useState<"device" | "manual">(selection?.mode ?? "device"),
    [precheck, setPrecheck] = useState(false),
    [editingIntake, setEditingIntake] = useState(false);
  const [measurementMode, setMeasurementMode] = useState<"calibration" | "repeatability">("calibration"),
    [historyReceipt, setHistoryReceipt] = useState<Receipt | null>(null);
  const [busy, setBusy] = useState(false),
    [failure, setFailure] = useState(""),
    [message, setMessage] = useState(""),
    [storageFailure, setStorageFailure] = useState(""),
    [blocked, setBlocked] = useState(false),
    [rejected, setRejected] = useState(false);
  const initialized = useRef(""),
    writing = useRef(false);
  useEffect(() => {
    const abort = new AbortController();
    void loadGuided(abort.signal)
      .then((c) => {
        if (abort.signal.aborted) return;
        setContext(c);
        if (initialized.current === c.athlete_id) return;
        initialized.current = c.athlete_id;
        setLatest(c.latest);
        const location = preparationLocation(c, selection?.place);
        setPlace(location);
        if (selection) setIds(retainedChoices(c.preparation.locations.find(p => p.location_id === location)?.entries ?? [], selection.ids));
        let d =
          c.latest?.artifact.state === "active" ? fromReceipt(c.latest) : null;
        try {
          const raw = localStorage.getItem(key(c.athlete_id, "pending"));
          if (raw) {
            const p = readPending(raw, c.athlete_id);
            setPending(p);
            d = readCommand(JSON.parse(p.body));
            setMessage(
              "Korábbi kérés eredménye még tisztázandó. Nem küldtünk automatikusan újra.",
            );
          } else if (c.latest?.artifact.state === "active") {
            const raw = localStorage.getItem(key(c.athlete_id, "draft"));
            if (raw) d = readDraft(raw, c.athlete_id, ref(c.latest.artifact));
          }
        } catch (e) {
          setBlocked(true);
          setFailure(
            e instanceof Error ? e.message : "A helyi állapot nem olvasható.",
          );
        }
        setDraft(d);
      })
      .catch((e) => {
        if (!abort.signal.aborted)
          setFailure(
            e instanceof Error ? e.message : "A felmérés nem tölthető be.",
          );
      });
    return () => abort.abort();
  }, [selection]);
  useEffect(() => {
    if (!context || !draft || blocked || latest?.artifact.state !== "active")
      return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try {
        localStorage.setItem(
          key(context.athlete_id, "draft"),
          JSON.stringify({
            version: "guided-strength-draft-v0.1",
            owner: context.athlete_id,
            parent: ref(latest.artifact),
            command: draft,
          }),
        );
        setStorageFailure("");
      } catch {
        setStorageFailure(
          "A helyi piszkozat nem menthető. A szervermentéshez engedélyezett helyi tárolás szükséges.",
        );
      }
    });
    return () => {
      active = false;
    };
  }, [context, draft, latest, blocked]);
  async function accept(r: Receipt) {
    if (!context) return;
    setLatest(r);
    localStorage.removeItem(key(context.athlete_id, "pending"));
    localStorage.removeItem(key(context.athlete_id, "draft"));
    setPending(null);
    setRejected(false);
    setDraft(r.artifact.state === "active" ? fromReceipt(r) : null);
    setMessage(
      r.artifact.state === "finished"
        ? "Az alkalom és az eredmények tartósan mentve."
        : r.artifact.state === "abandoned"
          ? "Az el nem kezdett alkalom lezárva."
          : "A felmérés állapota mentve; innen folytathatod.",
    );
    if (r.artifact.state === "finished" || r.artifact.state === "abandoned") {
      setPrecheck(false);
      try {
        const fresh = await loadGuided();
        if (fresh.athlete_id !== context.athlete_id) throw Error("Másik sportoló adatai érkeztek.");
        if (fresh.latest && same(ref(fresh.latest.artifact), ref(r.artifact))) setContext(fresh);
        if (r.artifact.state === "finished") onCompleted?.();
      } catch {
        setFailure("Az eredmények tartósan mentve. A friss kiindulóadatokat a Szerverállapot frissítése gombbal töltheted be.");
      }
    }
  }
  async function refresh(adopt = false) {
    setFailure("");
    setBusy(true);
    try {
      const c = await loadGuided();
      if (context && c.athlete_id !== context.athlete_id)
        throw Error("Másik sportoló adatai érkeztek. Töltsd újra az oldalt.");
      setContext(c);
      const nextPlace = preparationLocation(c, place);
      setPlace(nextPlace);
      setIds((selected) =>
        retainedChoices(
          c.preparation.locations.find((p) => p.location_id === nextPlace)
            ?.entries ?? [],
          selected,
        ),
      );
      if (
        pending &&
        c.latest &&
        same(c.latest.artifact.proposal, JSON.parse(pending.body))
      ) {
        await accept(await readReceipt(c.latest, c.athlete_id, pending.body));
      } else if (adopt) {
        if (pending && !rejected)
          throw Error(
            "Előbb tisztázd a függő kérés eredményét az azonos kérés újraküldésével.",
          );
        await preserveLocalRecovery(localStorage, c.athlete_id, {
          draft: localStorage.getItem(key(c.athlete_id, "draft")),
          pending: localStorage.getItem(key(c.athlete_id, "pending")),
        }, "guided-strength");
        localStorage.removeItem(key(c.athlete_id, "pending"));
        localStorage.removeItem(key(c.athlete_id, "draft"));
        setPending(null);
        setRejected(false);
        setBlocked(false);
        setLatest(c.latest);
        setDraft(
          c.latest?.artifact.state === "active" ? fromReceipt(c.latest) : null,
        );
        setMessage("A szerveren mentett állapotot töltöttük be.");
      }
    } catch (e) {
      setFailure(e instanceof Error ? e.message : "A frissítés nem sikerült.");
    } finally {
      setBusy(false);
    }
  }
  async function intakeCommitted() {
    setBusy(true);
    setFailure("");
    try {
      const c = await loadGuided();
      if (!context || c.athlete_id !== context.athlete_id)
        throw Error("Másik sportoló adatai érkeztek. Töltsd újra az oldalt.");
      setContext(c);
      const nextPlace = preparationLocation(c, place);
      setPlace(nextPlace);
      setIds((selected) =>
        retainedChoices(
          c.preparation.locations.find((p) => p.location_id === nextPlace)
            ?.entries ?? [],
          selected,
        ),
      );
      if (!startIssues(c).length) {
        setEditingIntake(false);
        setMessage(
          "A kezdeti válaszok mentve, az indítás előfeltételei rendezve. Ellenőrizd a kiválasztott gyakorlatokat és az aktuális állapotról szóló nyilatkozatot, majd indítsd a felmérőalkalmat.",
        );
      } else {
        setMessage(
          "A kezdeti válaszok mentve. Az indításhoz még hiányzó feltételek fent láthatók; a válaszokat itt tovább szerkesztheted.",
        );
      }
    } catch (e) {
      setFailure(
        "A kezdeti felmérés tartósan mentve, de az indíthatóság frissítése nem sikerült. Használd a Szerverállapot frissítése gombot." +
          (e instanceof Error ? " " + e.message : ""),
      );
    } finally {
      setBusy(false);
    }
  }
  async function closeIntake() {
    if (busy || writing.current) return;
    setEditingIntake(false);
    await refresh();
  }
  async function submit(action: Command["action"], supplied?: Command) {
    if (!context || writing.current || blocked) return;
    writing.current = true;
    setBusy(true);
    setFailure("");
    setMessage("");
    try {
      let p = pending;
      if (!p) {
        let command = supplied ?? draft;
        if (!command) throw Error("Nincs menthető állapot.");
        command = { ...command, request_id: crypto.randomUUID(), action };
        if (action === "apply")
          command = {
            ...command,
            assessment_reference: context.intake.reference!,
            source_hash: context.intake.sources.source_hash,
            reviewed: true,
          };
        const body = JSON.stringify(normalizeCommand(command));
        p = {
          version: "guided-strength-pending-v0.1",
          owner: context.athlete_id,
          body,
        };
        localStorage.setItem(
          key(context.athlete_id, "pending"),
          JSON.stringify(p),
        );
        setPending(p);
        setRejected(false);
      }
      await accept(await sendGuided(p));
    } catch (e) {
      setRejected(e instanceof GuidedError && [409, 422].includes(e.status));
      setFailure(
        e instanceof Error ? e.message : "A mentés eredménye még nem ismert.",
      );
    } finally {
      writing.current = false;
      setBusy(false);
    }
  }
  const locked = busy || !!pending || blocked,
    active = latest?.artifact.state === "active";
  const base = latest?.base ?? latest?.artifact;
  const label = (id: string) =>
    base?.preparation?.locations
      .flatMap((p) => p.entries)
      .find((e) => e.entry_id === id)?.label ?? id;
  const patch = (v: Partial<Command>) =>
    setDraft((d) => (d ? { ...d, ...v } : d));
  const progress = (v: Partial<Command["progress"]>) =>
    draft && patch({ progress: { ...draft.progress, ...v } });
  const edit = (v: Partial<ExerciseResult>) =>
    draft &&
    progress({
      results: draft.progress.results.map((r, i) =>
        i === draft.progress.current_index ? { ...r, ...v } : r,
      ),
    });
  function begin() {
    if (!context?.intake.data || !context.intake.reference) return;
    const c: Command = {
      request_id: crypto.randomUUID(),
      action: "start",
      previous_reference: null,
      assessment_reference: context.intake.reference,
      source_hash: context.intake.sources.source_hash,
      location_id: place,
      selected_entry_ids: ids,
      recording_mode: mode,
      precheck_confirmed: precheck,
      progress: initialProgress(context.intake.data, ids),
      actual_start_at: null,
      actual_end_at: null,
      workout_session_id: null,
      no_other_recording_confirmed: false,
      reviewed: false,
    };
    if (context.calibration_protocols) {
      c.protocol_version = protocolVersion;
      c.protocol_hash = context.calibration_protocols.content_hash;
      c.measurement_mode = measurementMode;
      c.progress.protocol_version = protocolVersion;
    }
    void submit("start", c);
  }
  function review() {
    if (!draft || !base || !context) return;
    patch({
      progress: { ...draft.progress, phase: "review" },
      actual_start_at: draft.actual_start_at ?? base.created_at,
      actual_end_at: draft.actual_end_at ?? new Date().toISOString(),
    });
  }
  const row = draft?.progress.results[draft.progress.current_index];
  return (
    <section className="pt-guided" aria-label="Vezetett kezdő erőfelmérés">
      {failure && (
        <p role="alert" className="pt-options-warning">
          {failure}
        </p>
      )}
      {storageFailure && <p role="alert">{storageFailure}</p>}
      {message && <p role="status">{message}</p>}
      {!context ? (
        <p>Kiindulóadatok betöltése…</p>
      ) : (
        <>
          {!embedded && <div className="pt-guided-links">
            <Link href="/initial-assessment">
              Kezdeti felmérés és jártasság
            </Link>
            <Link href="/training-options/locations">
              Helyszínek és felszerelések
            </Link>
          </div>}
          {blocked && <aside className="pt-options-warning" role="alert">
            <strong>A korábbi helyi felmérőalkalom állapota nem olvasható.</strong>
            <p>A folytatás külön másolatban megőrzi az eredeti helyi adatokat, majd a szerveren mentett alkalmat nyitja meg. Ha még nincs aktív mentett alkalom, új felmérést készíthetsz elő.</p>
            <button type="button" className={buttonClass} disabled={busy} onClick={() => void refresh(true)}>Adatok megőrzése és mentett állapot megnyitása</button>
          </aside>}
          {pending && (
            <aside className="pt-panel">
              <h2>Függő mentés</h2>
              <p>
                Az eredeti kérés megmaradt. Az újrapróbálás ugyanazokat az
                adatokat küldi, így nem keletkezik újabb alkalom.
              </p>
              <button
                type="button"
                disabled={busy || blocked}
                className={buttonClass}
                onClick={() =>
                  void submit(
                    pending
                      ? readCommand(JSON.parse(pending.body)).action
                      : "checkpoint",
                  )
                }
              >
                Azonos mentés újrapróbálása
              </button>
            </aside>
          )}
          {!active && !latest?.artifact.result?.application_pending && (
            <GuidedPreparation
              context={context}
              locked={locked}
              place={place}
              ids={ids}
              mode={mode}
              precheck={precheck}
              onPlace={(v) => {
                setPlace(v);
                setIds([]);
              }}
              onIds={setIds}
              onMode={setMode}
              onPrecheck={setPrecheck}
              onBegin={begin}
              onResolveIntake={() => onEditIntake ? onEditIntake({ place, ids, mode }) : setEditingIntake(true)}
              onCloseIntake={() => void closeIntake()}
              measurementMode={measurementMode}
              onMeasurementMode={setMeasurementMode}
              intakeEditor={
                editingIntake ? (
                  <section
                    className="pt-panel"
                    aria-label="Kezdeti válaszok rendezése"
                  >
                    <h3>Kezdeti válaszok ellenőrzése és mentése</h3>
                    <p>
                      Ha a források megváltoztak, először vedd át őket. Nézd át
                      a megmaradt válaszokat, jelöld az átnézést a 6. lépésben,
                      majd mentsd a felmérést. A hiányzó referenciasorozatok nem
                      akadályozzák ezt a mentést.
                    </p>
                    <AssessmentWorkspace
                      embedded
                      initialStep={5}
                      onCommitted={intakeCommitted}
                    />
                    <button
                      type="button"
                      className={secondaryClass}
                      disabled={busy}
                      onClick={() => void closeIntake()}
                    >
                      Vissza a gyakorlatválasztáshoz
                    </button>
                  </section>
                ) : null
              }
            />
          )}
          {active && draft && (
            <fieldset
              className="pt-panel pt-assessment-fields"
              disabled={locked}
            >
              {base &&
                clockInput(base.created_at, context.timezone_name).slice(
                  0,
                  10,
                ) !== context.local_today && (
                  <p className="pt-options-warning">
                    Ez egy korábbi napon megkezdett alkalom. A valós befejezési
                    idővel zárd le; több külön edzés eredményeit ne fűzd egy
                    alkalomba.
                  </p>
                )}
              <p className="pt-guided-step">
                {draft.progress.phase === "warmup"
                  ? "1. Bemelegítés"
                  : draft.progress.phase === "review"
                    ? "3. Eredmények és lezárás"
                    : `2. Gyakorlatok · ${draft.progress.current_index + 1} / ${draft.progress.results.length}`}
              </p>
              {draft.progress.phase === "warmup" ? (
                <>
                  <h2>Nyugodt bemelegítés</h2>
                  <p>
                    5–10 perc ismert, könnyű általános bemelegítés. Ezután az
                    első gyakorlatból néhány könnyű, kontrollált ismétlés
                    következik. A mai cél a kiindulópont rögzítése.
                  </p>
                  <p>
                    A kiválasztott gyakorlat felmérési menete és az eredménymezők a következő lépésben együtt jelennek meg. Saját testsúlyos gyakorlatnál a terhelés adott; a tényleges szabályos ismétléseket rögzíted.
                  </p>
                  <label className="pt-guided-check">
                    <input
                      type="checkbox"
                      checked={draft.progress.warmup_completed}
                      onChange={(e) =>
                        progress({ warmup_completed: e.target.checked })
                      }
                    />
                    Elvégeztem a bemelegítést, panaszmentesen folytathatom.
                  </label>
                  <button
                    type="button"
                    className={buttonClass}
                    disabled={!draft.progress.warmup_completed}
                    onClick={() => progress({ phase: "movements" })}
                  >
                    Tovább az első gyakorlathoz
                  </button>
                </>
              ) : draft.progress.phase === "movements" && row ? (
                <>
                  <h2>{label(row.entry_id)}</h2>
                  {draft.protocol_version && base?.measurement_protocols ? (
                    <CalibrationMovement
                      row={row}
                      protocol={base.measurement_protocols.entries.find((v) => v.entry_id === row.entry_id)!.protocol}
                      today={context.local_today}
                      mode={draft.measurement_mode}
                      onChange={(value) => edit(value)}
                      onSave={(value) => {
                        const command = { ...draft, progress: { ...draft.progress, results: draft.progress.results.map((r) => r.entry_id === value.entry_id ? value : r) } };
                        setDraft(command);
                        void submit("checkpoint", command);
                      }}
                    />
                  ) : <>
                  {base?.intake_context && (
                    <ExerciseInstructions
                      catalog={base.intake_context.sources.catalog}
                      exerciseId={
                        base.preparation?.locations
                          .flatMap((p) => p.entries)
                          .find((e) => e.entry_id === row.entry_id)
                          ?.exercise_id ?? null
                      }
                    />
                  )}
                  <p>
                    Először opcionálisan 3–5 könnyű próba-ismétlés, majd pihenő
                    után egy könnyű referenciasorozat: 5–8 kontrollált ismétlés,
                    vagy már ismert tartásból 10–20 másodperc. Ezek induló
                    támpontok; a ténylegesen elvégzett mennyiséget rögzítsd.
                  </p>
                  <p className="pt-options-meta">
                    A súlyt te választod meg. Bizonytalan gyakorlatot ne próbálj
                    ki egyedül a felmérés kedvéért.
                  </p>
                  <Choice
                    label="Oldal / végrehajtás"
                    value={row.side}
                    options={{
                      unknown: "Még nem tisztázott",
                      both: "Kétoldali",
                      left: "Bal oldal",
                      right: "Jobb oldal",
                      alternating: "Váltott",
                    }}
                    onChange={(v) =>
                      edit({ side: v as ExerciseResult["side"] })
                    }
                  />
                  <Field
                    label="Konkrét gép, fogantyú és beállítás · ha használsz gépet"
                    maxLength={200}
                    value={row.machine_note}
                    onChange={(e) => edit({ machine_note: e.target.value })}
                  />
                  {(["practice", "reference"] as const).map((purpose) => {
                    const s = row.observations.find(
                      (s) => s.purpose === purpose,
                    );
                    return (
                      <article key={purpose} className="pt-guided-observation">
                        <h3>
                          {purpose === "practice"
                            ? "Könnyű próbasorozat · választható"
                            : "Referenciasorozat · tényleges eredmény"}
                        </h3>
                        {s ? (
                          <>
                            <SetFields
                              value={s}
                              today={context.local_today}
                              onChange={(v) =>
                                edit({
                                  state: "recorded",
                                  observations: row.observations.map((o) =>
                                    o.id === v.id ? v : o,
                                  ),
                                })
                              }
                            />
                            <button
                              type="button"
                              className={secondaryClass}
                              onClick={() =>
                                edit({
                                  observations: row.observations.filter(
                                    (o) => o.id !== s.id,
                                  ),
                                })
                              }
                            >
                              Sorozatadat törlése
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            className={secondaryClass}
                            onClick={() =>
                              edit({
                                state: "recorded",
                                observations: [
                                  ...row.observations,
                                  {
                                    ...newSet(),
                                    purpose,
                                    performed_on: context.local_today,
                                  },
                                ],
                              })
                            }
                          >
                            {purpose === "practice"
                              ? "Próbasorozat rögzítése"
                              : "Elvégzett referenciasorozat rögzítése"}
                          </button>
                        )}
                      </article>
                    );
                  })}
                  <Rest />
                  </>}
                  {stopped(draft.progress) && (
                    <p role="alert" className="pt-options-warning">
                      Megállást jelző eredményt rögzítettél. Fejezd be a
                      felmérést; őrizd meg a valós adatokat az áttekintésnél.
                    </p>
                  )}
                  <Field
                    label="Megjegyzés ehhez a gyakorlathoz"
                    value={row.note}
                    maxLength={2000}
                    onChange={(e) => edit({ note: e.target.value })}
                  />
                  <div className="pt-guided-actions">
                    <button
                      type="button"
                      className={secondaryClass}
                      onClick={() => {
                        edit({ state: "skipped" });
                      }}
                    >
                      Gyakorlat kihagyása
                    </button>
                    {row.state === "skipped" && (
                      <span>
                        Kihagyva · a már felvett sorozatok megmaradnak.
                      </span>
                    )}
                    {draft.progress.current_index > 0 && (
                      <button
                        type="button"
                        className={secondaryClass}
                        onClick={() =>
                          progress({
                            current_index: draft.progress.current_index - 1,
                          })
                        }
                      >
                        Előző gyakorlat
                      </button>
                    )}
                    {draft.progress.current_index <
                      draft.progress.results.length - 1 &&
                    !stopped(draft.progress) ? (
                      <button
                        type="button"
                        className={buttonClass}
                        onClick={() =>
                          progress({
                            current_index: draft.progress.current_index + 1,
                          })
                        }
                      >
                        Következő gyakorlat
                      </button>
                    ) : (
                      <button
                        type="button"
                        className={buttonClass}
                        onClick={review}
                      >
                        Eredmények áttekintése
                      </button>
                    )}
                  </div>
                </>
              ) : (
                <>
                  <h2>Az alkalom áttekintése</h2>
                  {draft.protocol_version && draft.progress.results.some((r) => r.observations.some((s) => !s.performed_confirmed)) && <p role="alert">Van még elvégzettként nem rögzített próbaadat. Térj vissza a gyakorlathoz, és rögzítsd vagy vesd el a piszkozatpróbát. A már mentett eredmények megmaradnak.</p>}
                  <ul>
                    {draft.progress.results.map((r) => (
                      <li key={r.entry_id}>
                        <strong>{label(r.entry_id)}</strong> ·{" "}
                        {r.state === "skipped"
                          ? "kihagyva"
                          : r.state === "stopped"
                            ? "megszakítva"
                            : r.observations.length
                              ? `${r.observations.length} rögzített sorozat`
                              : "nincs rögzített sorozat"}
                        {r.observations.map((s) => draft.protocol_version ? <MeasurementSummary key={s.id} value={s} /> : (
                          <p key={s.id}>
                            {s.purpose === "practice" ? "Próba" : "Referencia"}{" "}
                            ·{" "}
                            {s.repetitions === null
                              ? s.hold_seconds === null
                                ? "ismeretlen mennyiség"
                                : `${s.hold_seconds} mp`
                              : `${s.repetitions} ismétlés`}{" "}
                            ·{" "}
                            {s.load_kind === "bodyweight"
                              ? "saját testsúly"
                              : s.load_value === null
                                ? "nincs számszerű terhelés"
                                : `${s.load_value} ${s.load_kind === "machine_level" ? "fokozat" : "kg"}`}{" "}
                            · tartalék:{" "}
                            {s.rir === "unknown"
                              ? "ismeretlen"
                              : s.rir === "5_plus"
                                ? "legalább 5"
                                : s.rir}
                          </p>
                        ))}
                      </li>
                    ))}
                  </ul>
                  {stopped(draft.progress) && (
                    <p role="alert">
                      Megállást jelző eredmény szerepel az alkalomban. Ezeket is
                      megőrizzük; panaszt jelző gyakorlatból nem lesz
                      felhasználható referencia.
                    </p>
                  )}
                  {draft.recording_mode === "device" ? (
                    <>
                      <p>
                        Ha órával rögzítettél, állítsd le és szinkronizáld a
                        felvételt, majd frissítsd a listát. Addig a „Mentés és
                        szünet” gombbal őrizheted meg az eredményeidet.
                      </p>
                      <Choice
                        label="Ehhez az alkalomhoz tartozó saját edzésnapló-bejegyzés"
                        value={draft.workout_session_id ?? ""}
                        options={{
                          "": "Válassz már rögzített erőedzést",
                          ...Object.fromEntries(
                            context.recordings
                              .filter(
                                (w) =>
                                  w.ended_at &&
                                  w.provider !== "PADDLETRAINER_GUIDED" &&
                                  Date.parse(w.ended_at) >=
                                    Date.parse(base!.created_at),
                              )
                              .map((w) => [
                                w.id,
                                `${w.name ?? "Erőedzés"} · ${new Date(w.started_at).toLocaleString("hu-HU", { timeZone: context.timezone_name })} · ${w.duration_sec === null ? "ismeretlen idő" : `${Math.round(w.duration_sec / 60)} perc`}`,
                              ]),
                          ),
                        }}
                        onChange={(v) =>
                          patch({ workout_session_id: v || null })
                        }
                      />
                      <button
                        type="button"
                        className={secondaryClass}
                        onClick={() => void refresh()}
                      >
                        Rögzített edzések frissítése
                      </button>
                    </>
                  ) : (
                    <>
                      <p>
                        A valós időszak a bemelegítést és a pihenőket is
                        tartalmazza. Ellenőrizd az időket ·{" "}
                        {context.timezone_name}.
                      </p>
                      {(["actual_start_at", "actual_end_at"] as const).map(
                        (k) => (
                          <Field
                            key={k}
                            type="datetime-local"
                            step={1}
                            label={
                              k === "actual_start_at"
                                ? "Tényleges kezdés"
                                : "Tényleges befejezés"
                            }
                            value={
                              draft[k]
                                ? clockInput(draft[k]!, context.timezone_name)
                                : ""
                            }
                            onChange={(e) => {
                              try {
                                patch({
                                  [k]: clockInstant(
                                    e.target.value,
                                    context.timezone_name,
                                  ),
                                });
                                setFailure("");
                              } catch (e) {
                                setFailure(
                                  e instanceof Error ? e.message : "Hibás idő.",
                                );
                              }
                            }}
                          />
                        ),
                      )}
                      <button
                        type="button"
                        className={secondaryClass}
                        onClick={() =>
                          patch({ actual_end_at: new Date().toISOString() })
                        }
                      >
                        Befejezés most
                      </button>
                      <label className="pt-guided-check">
                        <input
                          type="checkbox"
                          checked={draft.no_other_recording_confirmed}
                          onChange={(e) =>
                            patch({
                              no_other_recording_confirmed: e.target.checked,
                            })
                          }
                        />
                        Erről az alkalomról nincs másik órás vagy kézi
                        edzésfelvétel. Egy új, kézzel rögzített alkalom kerül az
                        edzésnaplóba.
                      </label>
                    </>
                  )}
                  <label className="pt-guided-check">
                    <input
                      type="checkbox"
                      checked={draft.reviewed}
                      onChange={(e) => patch({ reviewed: e.target.checked })}
                    />
                    Átnéztem a tényleges eredményeket és az alkalom rögzítését.
                    Az ismeretlen válaszokat üresen hagytam.
                  </label>
                  <div className="pt-guided-actions">
                    <button
                      type="button"
                      className={secondaryClass}
                      onClick={() => progress({ phase: "movements" })}
                    >
                      Vissza a gyakorlatokhoz
                    </button>
                    <button
                      type="button"
                      className={buttonClass}
                      disabled={
                        !draft.reviewed ||
                        !!(draft.protocol_version && draft.progress.results.some((r) => r.observations.some((s) => !s.performed_confirmed))) ||
                        (draft.recording_mode === "device"
                          ? !draft.workout_session_id
                          : !draft.no_other_recording_confirmed)
                      }
                      onClick={() => void submit("finish")}
                    >
                      Alkalom lezárása és eredmények mentése
                    </button>
                  </div>
                </>
              )}
              <div className="pt-guided-actions">
                <SaveActionButton saveLabel="Felmérőalkalom eredményeinek mentése" disabled={locked} saveHint="Az eddigi eredményeket menti a szerverre, az alkalom később folytatható."
                  type="button"
                  className={secondaryClass}
                  onClick={() => void submit("checkpoint")}
                >
                  Mentés és szünet
                </SaveActionButton>
                {draft.progress.phase !== "review" &&
                  (draft.progress.warmup_completed ||
                    stopped(draft.progress)) && (
                    <button
                      type="button"
                      className={secondaryClass}
                      onClick={review}
                    >
                      Felmérés befejezése részleges eredménnyel
                    </button>
                  )}
                {!draft.progress.warmup_completed &&
                  !draft.progress.results.some(
                    (r) => r.observations.length,
                  ) && (
                    <button
                      type="button"
                      className={secondaryClass}
                      onClick={() => void submit("abandon")}
                    >
                      El nem kezdett alkalom lezárása
                    </button>
                  )}
              </div>
              <p className="pt-options-meta">
                A „Mentés és szünet” szerverre ment; a sorozatmezők helyben
                piszkozatként is megmaradnak. Másik eszközön az utolsó
                szervermentést tudod folytatni.
              </p>
            </fieldset>
          )}
          {latest?.artifact.state === "finished" && (
            <section className="pt-panel">
              <h2>A felmérőalkalom mentve</h2>
              <p>
                Az alkalom egyszer szerepel az edzésnaplóban; a
                sorozateredmények önbevallott adatokként maradnak meg.
              </p>
              {latest.artifact.proposal.protocol_version && <>
                <p><strong>{latest.artifact.proposal.progress.results.reduce((n, r) => n + r.observations.filter((s) => s.performed_confirmed).length, 0)} elvégzett próba eredménye tartósan mentve.</strong> A nyers eredmények és a belőlük készíthető kezdő edzésadag külön szerepelnek.</p>
                {latest.artifact.proposal.progress.results.map((r) => <article key={r.entry_id} className="pt-guided-observation"><h3>{(latest.base ?? latest.artifact).measurement_protocols?.entries.find((v) => v.entry_id === r.entry_id)?.protocol.label}</h3>{r.observations.filter((s) => s.performed_confirmed).map((s) => <MeasurementSummary key={s.id} value={s} />)}</article>)}
                {!latest.artifact.result?.application_pending && <p>{starterTargets(latest).length} gyakorlat-/oldalreferencia alkalmas a visszafogott kezdő ismétléscél megállapítására. Az ismeretlen vagy hiányos eredmények is megmaradnak.</p>}
              </>}
              {latest.artifact.result?.application_pending ? (
                <>
                  <p>
                    A kiindulóadatok közben változtak. Az eredmények megvannak,
                    de még nem írtuk felül velük a kezdeti felmérést. Nézd át a
                    jelenlegi kezdeti felmérést, majd frissítsd ezt az oldalt.
                  </p>
                  <button
                    type="button"
                    className={buttonClass}
                    disabled={locked || context.intake.sources_changed}
                    onClick={() => {
                      const c = {
                        ...latest.artifact.proposal,
                        previous_reference: ref(latest.artifact),
                        reviewed: true,
                      };
                      void submit("apply", c);
                    }}
                  >
                    Eredmények átvétele az áttekintett felmérésbe
                  </button>
                </>
              ) : (
                <>
                  <p>
                    <strong>
                      {latest.assessment_receipt?.artifact.summary
                        .recorded_reference_count ?? 0}{" "}
                      gyakorlatnál van rögzített kiinduló referencia.
                    </strong>{" "}
                    A tervező ebből csak a megfelelő, ismert, panaszmentes
                    sorozatokat használhatja.
                  </p>
                  <Link className={buttonClass} href="/planning-cycles">
                    Tovább az edzésterv felülvizsgálatához
                  </Link>
                </>
              )}
            </section>
          )}
          {!!context.history.length && <section className="pt-panel" aria-label="Mentett felmérési eredmények">
            <h2>Korábbi felmérési eredmények</h2>
            <fieldset disabled={busy}>
            <Choice label="Mentett alkalom megnyitása" value={historyReceipt?.artifact.artifact_id ?? ""} options={{ "": "Válassz korábbi alkalmat", ...Object.fromEntries(context.history.map((h) => [h.reference.artifact_id, `${new Date(h.created_at).toLocaleString("hu-HU", { timeZone: context.timezone_name })} · ${h.state === "finished" ? "lezárva" : h.state === "active" ? "folyamatban" : "el sem kezdett"}`])) }} onChange={(id) => {
              if (!id) { setHistoryReceipt(null); return; }
              setBusy(true); setFailure("");
              void loadGuidedRevision(id, context.athlete_id).then(setHistoryReceipt).catch((e) => setFailure(e instanceof Error ? e.message : "Az eredmény nem tölthető be.")).finally(() => setBusy(false));
            }} />
            </fieldset>
            {historyReceipt?.artifact.proposal.progress.results.map((r) => <article key={r.entry_id}><h3>{(historyReceipt.base ?? historyReceipt.artifact).preparation?.locations.flatMap((p) => p.entries).find((e) => e.entry_id === r.entry_id)?.label ?? r.entry_id}</h3>{r.observations.map((s) => historyReceipt.artifact.proposal.protocol_version ? <MeasurementSummary key={s.id} value={s} /> : <p key={s.id}>{s.repetitions !== null ? `${s.repetitions} ismétlés` : s.hold_seconds !== null ? `${s.hold_seconds} másodperc` : "Ismeretlen mennyiség"} · {s.load_value ?? "nincs számszerű terhelés"}</p>)}</article>)}
          </section>}
          <div className="pt-guided-actions">
            <button
              type="button"
              className={secondaryClass}
              disabled={busy}
              onClick={() => void refresh()}
            >
              Szerverállapot frissítése
            </button>
            {rejected && !blocked && (
              <button
                type="button"
                className={secondaryClass}
                disabled={busy}
                onClick={() => void refresh(true)}
              >
                Mentett állapot betöltése a piszkozat helyére
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
