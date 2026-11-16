"use client";
import { SaveActionButton } from "@/components/planning-data/save-actions";
import type { SaveFeedback } from "@/components/planning-data/save-actions";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { canonical } from "@/lib/planning-cycles/contracts";
import {
  AssessmentError,
  loadAssessment,
  loadAssessmentRevision,
  sendAssessment,
} from "@/lib/initial-assessment/client";
import {
  emptyData,
  key,
  readPending,
  summarize,
} from "@/lib/initial-assessment/contracts";
import type {
  AssessmentReceipt,
  Context,
  Data,
  Pending,
  Ref,
} from "@/lib/initial-assessment/contracts";
import {
  buttonClass,
  secondaryClass,
} from "@/components/planning-goals/fields";
import AssessmentEditor from "./editor";
import { requestedStep } from "@/lib/guided-strength/preparation";
import { LOCAL_REFRESH_EVENT } from "@/lib/data-connections/preferences";
import { mergeAssessmentAnswers } from "@/lib/initial-assessment/draft-sync";
import { recoverAssessment } from "@/lib/initial-assessment/recovery";
import { preserveAssessmentRecovery } from "@/lib/initial-assessment/recovery-backup";
import type { RecoveryBackup, RecoveryInputs } from "@/lib/initial-assessment/recovery-backup";
import { assessmentSaveData, AssessmentSaveInputError } from "@/lib/initial-assessment/save-validation";

export type AssessmentEditState = { dirty: boolean; sourcesChanged: boolean; pending: boolean; saving: boolean; missingSteps: number[] };

export default function AssessmentWorkspace({
  onSaved,
  onCommitted,
  embedded = false,
  initialStep = 0,
  onStateChange,
  navigationRequest,
}: {
  onSaved?: (complete: boolean) => void;
  onCommitted?: (receipt: AssessmentReceipt) => void | Promise<void>;
  embedded?: boolean;
  initialStep?: number;
  onStateChange?: (state: AssessmentEditState) => void;
  navigationRequest?: { serial: number; step: number };
}) {
  const [context, setContext] = useState<Context | null>(null),
    [data, setData] = useState<Data | null>(null),
    [sourceHash, setSourceHash] = useState(""),
    [parent, setParent] = useState<Ref | null>(null),
    [open, setOpen] = useState(0);
  const [pending, setPending] = useState<Pending | null>(null),
    [verified, setVerified] = useState<AssessmentReceipt | null>(null),
    [busy, setBusy] = useState(false),
    [blocked, setBlocked] = useState(false),
    [rejected, setRejected] = useState(false),
    [failure, setFailure] = useState(""),
    [message, setMessage] = useState(""),
    [storageFailure, setStorageFailure] = useState("");
  const initialized = useRef<string | null>(null),
    writing = useRef(false);
  const [saveNotice, setSaveNotice] = useState<SaveFeedback>();
  const [recoveryBackup, setRecoveryBackup] = useState<RecoveryBackup | null>(null);
  const [persistencePaused, setPersistencePaused] = useState(false);
  const recoveryInputs = useRef<RecoveryInputs | null>(null);
  const draftPendingId = useRef<string | null>(null);
  const current = useRef({ context, data, pending });
  const draftBase = useRef<Data | null>(null);
  useEffect(() => { current.current = { context, data, pending }; }, [context, data, pending]);
  useEffect(() => {
    if (!navigationRequest) return;
    let active = true;
    queueMicrotask(() => { if (active) { setOpen(navigationRequest.step); document.querySelector(".pt-initial-assessment")?.scrollIntoView({ block: "start" }); } });
    return () => { active = false; };
  }, [navigationRequest]);
  useEffect(() => {
    const abort = new AbortController();
    void loadAssessment(abort.signal)
      .then(async (c) => {
        if (abort.signal.aborted) return;
        setContext(c);
        if (initialized.current === c.athlete_id) return;
        let initial = c.data ?? emptyData(c),
          source = c.data
            ? c.saved!.artifact.proposal.source_hash
            : c.sources.source_hash,
          previous = c.reference,
          step = 0,
          recovered = false;
        try {
          const inputs = { draft: localStorage.getItem(key(c.athlete_id, "draft")), pending: localStorage.getItem(key(c.athlete_id, "pending")) };
          recoveryInputs.current = inputs;
          const result = await recoverAssessment(c,
            inputs.draft, inputs.pending,
            token => loadAssessmentRevision(c.athlete_id, token, abort.signal));
          if (abort.signal.aborted) return;
          initial = result.data; source = result.sourceHash; previous = result.parent; step = result.step;
          recovered = result.recovered;
          draftPendingId.current = result.draftPendingId;
          draftBase.current = result.base;
          setPending(result.pending);
          let preserved = true;
          if (result.recovered || result.recoveryRequired) {
            try {
              const backup = await preserveAssessmentRecovery(localStorage, c.athlete_id, inputs);
              if (abort.signal.aborted) return;
              setRecoveryBackup(backup);
            } catch {
              if (abort.signal.aborted) return;
              preserved = false; setPersistencePaused(true);
              setFailure("Az eredeti helyi adatok külön másolatát nem sikerült eltárolni. A mezőket szerkesztheted; az eredeti piszkozatot nem írjuk felül. Az adatokat a helyreállítási panelből le is töltheted.");
            }
          }
          setBlocked(result.recoveryRequired || !preserved);
          if (result.committed) {
            if (preserved) localStorage.removeItem(key(c.athlete_id, "pending"));
            setVerified(result.committed);
          }
          if (result.message) {
            setMessage(result.message);
            setSaveNotice({ tone: "info", text: result.message });
          }
        } catch (e) {
          if (abort.signal.aborted) return;
          setBlocked(true);
          setPersistencePaused(true);
          setFailure(
            e instanceof Error
              ? e.message
              : "A helyi piszkozat vagy függő kérés nem ellenőrizhető. Új mentést nem indítunk.",
          );
        }
        initialized.current = c.athlete_id;
        setData(initial);
        setSourceHash(source);
        setParent(previous);
        setOpen(
          recovered ? 5 : embedded
            ? initialStep
            : (requestedStep(window.location.search) ?? step),
        );
      })
      .catch((e) => {
        if (!abort.signal.aborted)
          setFailure(
            e instanceof Error ? e.message : "A felmérés nem tölthető be.",
          );
      });
    return () => abort.abort();
  }, [embedded, initialStep]);
  useEffect(() => {
    if (!embedded) return;
    let active = true;
    queueMicrotask(() => { if (active) setOpen(initialStep); });
    return () => { active = false; };
  }, [embedded, initialStep]);
  useEffect(() => {
    const abort = new AbortController();
    const update = () => {
      if (writing.current || !initialized.current) return;
      void loadAssessment(abort.signal).then((c) => {
        if (abort.signal.aborted || writing.current) return;
        const old = current.current;
        if (c.athlete_id !== initialized.current) throw Error("Másik sportoló adatai érkeztek. Töltsd újra az oldalt.");
        // Bring new saved sets into an open editor as well as a reopened one.
        // Merge against its verified base so unrelated unfinished answers survive.
        if (!old.pending && old.data && c.data &&
          canonical(c.reference) !== canonical(old.context?.reference ?? null)) {
          const merged = mergeAssessmentAnswers(draftBase.current, old.data, c.data);
          setData(canonical(merged) === canonical(c.data) ? merged : { ...merged, reviewed: false });
          setParent(c.reference); setSourceHash(c.saved!.artifact.proposal.source_hash);
          draftBase.current = c.data;
          setMessage("Az újonnan mentett felmérési eredmények betöltődtek. A tervezéshez szükséges állapot frissült.");
        }
        setContext(c);
      }).catch((e) => { if (!abort.signal.aborted) setFailure(e instanceof Error ? e.message : "A felmérés frissítése nem sikerült."); });
    };
    window.addEventListener(LOCAL_REFRESH_EVENT, update); window.addEventListener("focus", update);
    return () => { abort.abort(); window.removeEventListener(LOCAL_REFRESH_EVENT, update); window.removeEventListener("focus", update); };
  }, []);
  useEffect(() => {
    if (!context || !data || persistencePaused) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try {
        localStorage.setItem(
          key(context.athlete_id, "draft"),
          JSON.stringify({
            version: "initial-assessment-draft-v0.1",
            owner: context.athlete_id,
            source_hash: sourceHash,
            previous_reference: parent,
            data,
            open,
            pending_request_id: pending ? JSON.parse(pending.body).request_id : draftPendingId.current,
          }),
        );
        setStorageFailure("");
      } catch {
        setStorageFailure(
          "A helyi piszkozatot nem sikerült eltárolni. A szervermentés csak a kérés helyi megőrzése után indulhat el.",
        );
      }
    });
    return () => {
      active = false;
    };
  }, [context, data, sourceHash, parent, open, persistencePaused, pending]);
  const latest =
    verified &&
    (!context?.saved ||
      verified.artifact.revision > context.saved.artifact.revision)
      ? verified
      : context?.saved;
  useEffect(() => {
    onSaved?.(
      !!latest?.artifact.summary.form_complete &&
        latest.artifact.proposal.source_hash === context?.sources.source_hash && !pending && !blocked &&
        !!data && canonical(data) === canonical(latest.artifact.proposal.data),
    );
  }, [latest, context?.sources.source_hash, data, pending, blocked, onSaved]);
  useEffect(() => {
    if (!context || !data) return;
    const summary = summarize(data, context.sources, context.local_today);
    onStateChange?.({ dirty: !latest || canonical(data) !== canonical(latest.artifact.proposal.data),
      sourcesChanged: sourceHash !== context.sources.source_hash || canonical(parent) !== canonical(context.reference),
      pending: !!pending || blocked, saving: busy,
      missingSteps: summary.steps.flatMap((done, i) => done ? [] : [i]) });
  }, [context, data, latest, sourceHash, parent, pending, busy, blocked, onStateChange]);
  async function refresh() {
    try {
      const c = await loadAssessment();
      if (initialized.current !== c.athlete_id)
        throw Error("Másik sportoló adatai érkeztek. Töltsd újra az oldalt.");
      const old = current.current;
      if (!old.pending && old.data && c.data &&
        canonical(c.reference) !== canonical(old.context?.reference ?? null)) {
        const merged = mergeAssessmentAnswers(draftBase.current, old.data, c.data);
        setData(canonical(merged) === canonical(c.data) ? merged : { ...merged, reviewed: false });
        setParent(c.reference); setSourceHash(c.saved!.artifact.proposal.source_hash);
        draftBase.current = c.data;
      }
      setContext(c);
      setFailure("");
      return c;
    } catch (e) {
      setFailure(e instanceof Error ? e.message : "A frissítés nem sikerült.");
      return null;
    }
  }
  function downloadRecovery() {
    if (!context || !data) return;
    const originals = recoveryBackup ? JSON.parse(recoveryBackup.payload) : {
      version: "initial-assessment-recovery-v0.1", owner: context.athlete_id,
      ...recoveryInputs.current,
    };
    const content = JSON.stringify({ ...originals, working_data: data, latest_saved_reference: context.reference }, null, 2);
    const url = URL.createObjectURL(new Blob([content], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url; link.download = `PaddleTrainer_felmeres_helyreallitas_${context.local_today}.json`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function prepareRecovery() {
    if (!context || !data || writing.current) return;
    writing.current = true; setBusy(true);
    try {
      const owner = context.athlete_id;
      const inputs = recoveryInputs.current ?? {
        draft: localStorage.getItem(key(owner, "draft")), pending: localStorage.getItem(key(owner, "pending")),
      };
      setRecoveryBackup(await preserveAssessmentRecovery(localStorage, owner, inputs));
      const c = await loadAssessment();
      if (c.athlete_id !== owner) throw Error("Másik sportoló adatai érkeztek. Töltsd újra az oldalt.");
      const raw = localStorage.getItem(key(owner, "pending"));
      let retained: Pending | null = null;
      if (raw) {
        try { retained = readPending(raw, owner); }
        catch {
          // The unreadable request is never repaired in place or silently retried.
          // The user's recovery action keeps its exact original in a separate copy.
          await preserveAssessmentRecovery(localStorage, owner, { draft: localStorage.getItem(key(owner, "draft")), pending: raw });
          localStorage.removeItem(key(owner, "pending"));
        }
      }
      const advanced = canonical(c.reference) !== canonical(context.reference);
      const next = advanced && c.data ? mergeAssessmentAnswers(draftBase.current, data, c.data) : structuredClone(data);
      setData({ ...next, timezone_name: c.timezone_name, reviewed: false });
      draftBase.current = c.data; setContext(c); setParent(c.reference); setSourceHash(c.sources.source_hash);
      setPending(retained); setBlocked(false); setPersistencePaused(false); setRejected(false); setFailure(""); setOpen(5);
      draftPendingId.current = null;
      const notice = retained
        ? "Az adatok megmaradtak. A korábbi, ellenőrizhető mentést az eredeti kéréssel folytathatod; a közben beírt módosításokat utána külön mentsd el."
        : "Az eredeti helyi adatok külön másolatban megmaradtak. Nézd át az összegzést, jelöld az átnézést, majd mentsd a felmérést.";
      setMessage(notice); setSaveNotice({ tone: "info", text: notice });
    } catch (e) {
      const detail = e instanceof Error ? e.message : "A helyi adatok megőrzése vagy a mentési alap beolvasása nem sikerült.";
      setFailure(detail); setSaveNotice({ tone: "error", text: detail + " A mezők szerkeszthetők, az eredeti adatok a letöltőgombbal megőrizhetők." });
    } finally { writing.current = false; setBusy(false); }
  }
  async function adoptSources() {
    if (blocked) { await prepareRecovery(); return; }
    if (!context || writing.current) return;
    writing.current = true;
    setBusy(true);
    setSaveNotice({ tone: "info", text: "A friss mentett adatok betöltése folyamatban…" });
    try {
      const c = await refresh();
      if (!c) return;
      if (pending && !rejected)
        throw Error("Előbb a függő mentés eredményét kell tisztázni.");
      localStorage.removeItem(key(c.athlete_id, "pending"));
      setPending(null);
      setRejected(false);
      setParent(c.reference);
      setSourceHash(c.sources.source_hash);
      const base = draftBase.current;
      setData((d) => d ? { ...(c.data ? mergeAssessmentAnswers(base, d, c.data) : d), timezone_name: c.timezone_name, reviewed: false } : d);
      draftBase.current = c.data;
      setOpen(5);
      setMessage(
        "A friss forrásokat átvetted. A saját válaszaid megmaradtak; nézd át őket az új mentés előtt.",
      );
      setSaveNotice({ tone: "info", text: "A friss források és mentett eredmények átvéve. Az újabb mentett felmérés dátumát is megőrizzük. Nézd át az összegzést, jelöld az átnézést, majd ments." });
    } catch (e) {
      setFailure(
        e instanceof Error ? e.message : "A források átvétele nem sikerült.",
      );
      setSaveNotice({ tone: "error", text: e instanceof Error ? e.message : "A friss adatok átvétele nem sikerült. A saját válaszaid megmaradtak." });
    } finally {
      writing.current = false;
      setBusy(false);
    }
  }
  async function save() {
    if (!context || !data || writing.current || blocked) return;
    writing.current = true;
    setBusy(true);
    setFailure("");
    setMessage("");
    setSaveNotice({ tone: "info", text: "A felmérés mentése folyamatban…" });
    let frozen: Pending | null = pending;
    const previousBase: Data | null = pending ? JSON.parse(pending.body).data : draftBase.current;
    let submittedDraft = data;
    let sent = false;
    try {
      if (!frozen) {
        const normalized = assessmentSaveData(data, context.local_today);
        submittedDraft = normalized;
        frozen = {
          version: "initial-assessment-pending-v0.1",
          owner: context.athlete_id,
          body: JSON.stringify({
            request_id: crypto.randomUUID(),
            previous_reference: parent,
            source_hash: sourceHash,
            data: normalized,
          }),
        };
        localStorage.setItem(
          key(context.athlete_id, "pending"),
          JSON.stringify(frozen),
        );
        readPending(
          localStorage.getItem(key(context.athlete_id, "pending"))!,
          context.athlete_id,
        );
        setPending(frozen);
        setData(normalized);
      }
      sent = true;
      const receipt = await sendAssessment(frozen);
      setVerified(receipt);
      setParent({
        artifact_id: receipt.artifact.artifact_id,
        content_hash: receipt.artifact.content_hash,
      });
      setSourceHash(receipt.artifact.proposal.source_hash);
      const afterReceipt = mergeAssessmentAnswers(previousBase, submittedDraft, receipt.artifact.proposal.data);
      setData(canonical(afterReceipt) === canonical(receipt.artifact.proposal.data) ? afterReceipt : { ...afterReceipt, reviewed: false });
      draftBase.current = receipt.artifact.proposal.data;
      localStorage.removeItem(key(context.athlete_id, "pending"));
      setPending(null);
      setRejected(false);
      setMessage(
        `Tartós mentés visszaigazolva · ${receipt.artifact.revision}. változat. ${receipt.artifact.summary.form_complete ? "A kérdéssor kitöltött." : "Részleges felmérésként megőrizve."}`,
      );
      setSaveNotice({ tone: "success", text: `A felmérés mentve · ${receipt.artifact.revision}. változat. ${receipt.artifact.summary.recorded_reference_count} gyakorlat rögzített referenciája megmaradt. A tervezés indíthatóságát frissítjük.` });
      const refreshed = await refresh();
      if (refreshed?.data) {
        // A retry acknowledges frozen bytes, while the editable draft may have
        // advanced independently. Keep those edits and the newest saved sets.
        const merged = mergeAssessmentAnswers(previousBase, submittedDraft, refreshed.data);
        const clean = canonical(merged) === canonical(refreshed.data);
        setData(clean ? merged : { ...merged, reviewed: false }); setParent(refreshed.reference);
        setSourceHash(refreshed.saved!.artifact.proposal.source_hash); draftBase.current = refreshed.data;
        if (!clean) {
          setMessage("A korábbi mentés visszaigazolva. A közben szerkesztett válaszok megmaradtak; ezeket átnézés után külön mentsd el.");
          setSaveNotice({ tone: "info", text: "A korábbi mentés visszaigazolva. A közben beírt módosításaid megmaradtak, de még nincsenek elmentve. Nézd át az összegzést, majd ments újra." });
        } else if (refreshed.saved!.artifact.revision > receipt.artifact.revision) {
          setMessage("A korábbi mentés visszaigazolva. A legfrissebb mentett felmérés és eredményei látszanak.");
          setSaveNotice({ tone: "success", text: `A korábbi mentés visszaigazolva. A legfrissebb felmérés ${refreshed.summary!.recorded_reference_count} gyakorlat rögzített referenciáját tartalmazza; a mezők szerkeszthetők.` });
        }
      }
      if (!refreshed) setSaveNotice({ tone: "success", text: "A felmérés mentve. A tervezés állapotát még újra kell olvasni a Szerverállapot frissítése gombbal." });
      if (onCommitted) {
        try {
          await onCommitted(receipt);
        } catch {
          setMessage(
            "A felmérés tartósan mentve. Az indíthatóság frissítése nem sikerült; használd a Szerverállapot frissítése gombot.",
          );
          setSaveNotice({ tone: "success", text: "A felmérés mentve. A tervezés állapotát még újra kell olvasni a Szerverállapot frissítése gombbal." });
        }
      }
    } catch (e) {
      const detail = e instanceof Error ? e.message : "A mentés eredménye még nem ismert.";
      const refused = e instanceof AssessmentError && [400, 404, 409, 422].includes(e.status);
      if (
        e instanceof AssessmentError &&
        [400, 404, 409, 422].includes(e.status)
      )
        setRejected(true);
      setFailure(
        e instanceof Error
          ? e.message
          : "A mentés eredménye még nem ismert; azonos tartalommal újrapróbálható.",
      );
      setSaveNotice({ tone: "error", text: !sent ? `A mentés nem indult el: ${detail}` : refused ? `A szerver elutasította a mentést: ${detail}` : `A mentés eredménye még nem igazolt: ${detail} Az eredeti kérés változatlanul megmaradt; az ellenőrzőgombbal próbálható újra.`,
        ...(e instanceof AssessmentSaveInputError ? { target: { controls: `assessment-step-${e.step}`, label: "Felmérés dátumának ellenőrzése" } } : {}) });
    } finally {
      writing.current = false;
      setBusy(false);
    }
  }
  if (!context || !data)
    return (
      <div className="pt-options-message" role={failure ? "alert" : "status"}>
        {failure || "A felmérés és a mentett források betöltése…"}
      </div>
    );
  const latestRef = latest
    ? {
        artifact_id: latest.artifact.artifact_id,
        content_hash: latest.artifact.content_hash,
      }
    : null;
  const changedSources = sourceHash !== context.sources.source_hash,
    changedParent = canonical(parent) !== canonical(latestRef),
    stale = changedSources || changedParent;
  const dirty =
    !latest || canonical(data) !== canonical(latest.artifact.proposal.data);
  const visibleSaveNotice: SaveFeedback | undefined = saveNotice?.tone === "success" && dirty && !busy && !pending
    ? { tone: "info", text: "A legutóbbi mentés óta módosítottad a válaszokat. Az új változtatásokat még mentsd el." } : saveNotice;
  const disabled = busy;
  const summary = summarize(data, context.sources, context.local_today);
  const recoveryPanel = blocked ? <aside className="pt-options-warning" role="alert">
    <strong>A korábbi helyi mentés helyreállítást igényel.</strong>
    <p>{message || failure || "A helyi mentés beolvasása nem sikerült."}</p>
    <p>A mezőket szerkesztheted. A folytatás megőrzi az eredeti helyi adatokat, majd az itt látható válaszokból készít új mentési alapot.</p>
    <button type="button" className={buttonClass} disabled={busy} onClick={() => void prepareRecovery()}>Mentés előkészítése a megőrzött adatokkal</button>{" "}
    <button type="button" className={secondaryClass} disabled={busy} onClick={downloadRecovery}>Megőrzött adatok letöltése</button>
  </aside> : null;
  return (
    <div className="pt-initial-assessment">
      <div className="pt-options-message">
        <p>
          <strong>
            {latest
              ? `Mentett felmérés · ${latest.artifact.revision}. változat`
              : "Még nincs szerverre mentett felmérés"}
          </strong>
        </p>
        <p>
          {dirty
            ? "A jelenlegi válaszok helyi piszkozatban vannak; a szervermentés külön gombbal történik."
            : "A betöltött válaszok egyeznek a mentett változattal."}
        </p>
        <p className="pt-options-meta">
          A hiányzó mérésekkel is továbbhaladhatsz és részleges felmérést is
          menthetsz.
        </p>
      </div>
      {storageFailure && <p role="alert">{storageFailure}</p>}
      {failure && (
        <p className="pt-options-message" role="alert">
          {failure}
        </p>
      )}
      {message && (
        <p className="pt-options-message" role="status">
          {message}
        </p>
      )}
      {stale && (
        <div className="pt-options-message" role="status">
          <p>
            A piszkozat forrásai vagy a szerveren mentett felmérés megváltoztak.
            A saját válaszaid megmaradtak.
          </p>
          <button
            type="button"
            className={secondaryClass}
            disabled={busy || (!!pending && !rejected)}
            onClick={() => void adoptSources()}
          >
            Friss források és mentési alap átvétele
          </button>
        </div>
      )}
      {pending && (
        <div className="pt-options-message">
          <p>
            {rejected
              ? "A szerver elutasította ezt a kérést. A friss adatokkal új mentés készíthető."
              : "Egy korábbi mentés eredménye még nem tisztázott. A mezőket szerkesztheted; az ellenőrzés az eredeti kérést folytatja, az új módosításokat utána külön mentheted."}
          </p>
          {rejected ? (
            <button
              type="button"
              className={secondaryClass}
              disabled={busy}
              onClick={() => void adoptSources()}
            >
              Új mentés előkészítése a friss adatokkal
            </button>
          ) : (
            <button
              type="button"
              className={buttonClass}
              disabled={busy}
              onClick={() => void save()}
            >
              Azonos mentés újrapróbálása
            </button>
          )}
        </div>
      )}
      {latest && !pending && !embedded && (
        <p className="pt-options-message">
          A következő tervfelülvizsgálat a legfrissebb szerverre mentett
          felmérést használja. Az erőjavaslatnál a még hiányzó adatok is
          megjelennek.{" "}
          <Link href="/training-planning#plan" className="underline">
            Tovább az edzéstervhez
          </Link>
        </p>
      )}
      {!embedded && (
        <p className="pt-panel">
          A mentett jártassági válaszok alapján{" "}
          <Link href="/strength-assessment" className="underline">
            vezetett kezdő erőfelmérő alkalmat indíthatsz
          </Link>
          , és létrehozhatod az első saját sorozatreferenciákat.
        </p>
      )}
      <AssessmentEditor
        context={context}
        data={data}
        open={open}
        onOpen={setOpen}
        onChange={setData}
        disabled={disabled}
        notice={recoveryPanel}
      />
      <p id="pt-assessment-save-status" role="status">
        {blocked
          ? "A mezők szerkeszthetők. A lenti Mentés rendezése gombbal őrizheted meg a korábbi adatokat és készítheted elő az új mentést."
          : stale
          ? "A mentéshez először vedd át a friss forrásokat a fenti gombbal. A saját válaszaid megmaradnak; utána jelöld az átnézést a 6. lépésben."
          : pending
            ? "A függő mentést a fenti azonos újrapróbálással lehet tisztázni."
            : embedded && !data.reviewed
              ? "A mentéshez jelöld az átnézést a 6. lépésben. Korábbi referenciasorozat nem szükséges."
              : embedded
                ? "A kezdeti válaszok mentése után itt frissül a felmérőalkalom indíthatósága. A teljes kérdéssor hiányzó részei és a hiányzó referenciasorozatok nem akadályozzák ezt a mentést."
                : "A válaszaid a lenti mentés gombbal kerülnek a szerverre. Hiányzó mérésekkel részleges felmérés is menthető."}
      </p>
      <div className="pt-options-actions">
        <SaveActionButton saveLabel={busy ? "Mentés folyamatban…" : blocked ? "Mentés rendezése" : pending ? rejected ? "Új mentés előkészítése a friss adatokkal" : "Azonos mentés ellenőrzése" : "Kezdeti válaszok mentése"} saveFeedback={visibleSaveNotice} saveHint={blocked ? "Az eredeti adatok megőrzésével előkészíti a mentést." : stale && !pending ? "Előbb vedd át a friss forrásokat." : pending ? "Először a korábbi mentést ellenőrzi. Az új módosításokat utána külön mentheted." : embedded && !data.reviewed ? "Jelöld az átnézést az összegzésben." : "A megadott kezdeti válaszokat menti."}
          type="button"
          className={buttonClass}
          disabled={busy || (!blocked && !pending && (stale || (embedded && !data.reviewed)))}
          aria-describedby="pt-assessment-save-status"
          onClick={() => blocked ? void prepareRecovery() : pending && rejected ? void adoptSources() : void save()}
        >
          {busy
            ? "Mentés…"
            : embedded
              ? "Kezdeti válaszok mentése"
              : summary.form_complete
                ? "Felmérés mentése"
                : "Részleges felmérés mentése"}
        </SaveActionButton>
        <button
          type="button"
          className={secondaryClass}
          disabled={busy}
          onClick={() => void refresh()}
        >
          Szerverállapot frissítése
        </button>
        {latest && !pending && !blocked && (
          <button
            type="button"
            className={secondaryClass}
            disabled={busy}
            onClick={() => {
              setData(structuredClone(latest.artifact.proposal.data));
              draftBase.current = latest.artifact.proposal.data;
              setParent(latestRef);
              setSourceHash(latest.artifact.proposal.source_hash);
              setMessage(
                "A szerveren visszaigazolt változat került a helyi piszkozat helyére.",
              );
            }}
          >
            Mentett változat betöltése a helyi piszkozat helyére
          </button>
        )}
      </div>
    </div>
  );
}
