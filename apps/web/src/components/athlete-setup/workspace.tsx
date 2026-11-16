"use client";
import { SaveActionButton, SaveActionHint } from "@/components/planning-data/save-actions";
import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { getJSON, readPeriods } from "@/lib/planning-goals/client";
import { addDays, object, sha } from "@/lib/planning-cycles/contracts";
import {
  history,
  loadContext,
  previewCalendar,
  send,
  recoverPending,
  SetupHTTPError,
} from "@/lib/athlete-setup/client";
import {
  dates,
  emptyProfile,
  gateLabels,
  normalizeProfile,
  PENDING_KEY,
  readQueue,
  reasonLabels,
  resizeCalendar,
  validateCalendar,
} from "@/lib/athlete-setup/contracts";
import type {
  Calendar,
  Candidate,
  Context,
  Domain,
  PendingQueue,
  Profile,
  Receipt,
} from "@/lib/athlete-setup/contracts";
import {
  buttonClass,
  Card,
  Message,
  secondaryClass,
} from "@/components/planning-goals/fields";
import ProfileForm from "./profile-form";
import CalendarForm from "./calendar-form";
import type { PeriodChoice } from "./calendar-form";
import HistoryForm from "./history-form";
import SetupProgress from "./setup-progress";
import WeeklyAgreement from "./weekly-agreement";
import { LOCAL_REFRESH_EVENT } from "@/lib/data-connections/preferences";
import { loadConstraints } from "@/lib/calendar/constraint-client";
import type { ScheduleContext } from "@/lib/calendar/constraints";
import { pendingDescription, profileChanges, retainProfileEdits, sectionProfile, editingProfile } from "@/lib/planning-data/profile-state";
import { bodyChangedKey } from "@/lib/athlete-setup/body-mass";
import type { ProfileEditState, ProfileSection } from "@/lib/planning-data/profile-state";
export type AthletePanels = { personal: ReactNode; sports: ReactNode; history: ReactNode; notices: ReactNode };
const message = (e: unknown) =>
  e instanceof Error ? e.message : "A művelet nem sikerült.";
export default function AthleteWorkspace({
  initialTab = "profile",
  embedded = false,
  profileSection = "all",
  onDirtyChange,
  activeTab,
  renderPanels,
  onEditStateChange,
}: {
  initialTab?: "profile" | "calendar" | "history";
  embedded?: boolean;
  profileSection?: "all" | "personal" | "sports";
  onDirtyChange?: (dirty: boolean) => void;
  activeTab?: "profile" | "calendar" | "history";
  renderPanels?: (panels: AthletePanels) => ReactNode;
  onEditStateChange?: (state: ProfileEditState) => void;
} = {}) {
  const [context, setContext] = useState<Context | null>(null),
    [profile, setProfile] = useState<Profile>(emptyProfile),
    [calendar, setCalendar] = useState<Calendar | null>(null),
    [periods, setPeriods] = useState<PeriodChoice[]>([]);
  const [tabSelection, setTab] = useState<"profile" | "calendar" | "history">(
      initialTab,
    ),
    [candidates, setCandidates] = useState<Candidate[]>([]),
    [frozen, setFrozen] = useState<Candidate[]>([]),
    [formKey, setFormKey] = useState("new");
  const [pending, setPending] = useState<PendingQueue | null>(null),
    [blocked, setBlocked] = useState(false),
    [ready, setReady] = useState(false),
    [busy, setBusy] = useState(false),
    [rejected, setRejected] = useState(false),
    [error, setError] = useState(""),
    [success, setSuccess] = useState("");
  const [review, setReview] = useState<{
      body: string;
      coverage: Record<string, number>;
    } | null>(null),
    [reload, setReload] = useState(0),
    [progress, setProgress] = useState("");
  const sending = useRef(false),
    stop = useRef(false),
    status = useRef<HTMLDivElement>(null);
  const tab = activeTab ?? tabSelection;
  const locked = busy || !!pending || blocked || !ready;
  const [schedule, setSchedule] = useState<ScheduleContext | null>(null);
  useEffect(() => {
    if (context) onDirtyChange?.(Object.values(profileChanges(profile, editingProfile(context))).some(Boolean));
  }, [profile, context, onDirtyChange]);
  useEffect(() => {
    if (context) onEditStateChange?.({
      ...profileChanges(profile, editingProfile(context)),
      profilePending: !!pending?.items.some((item) => item.operation === "profiles"),
      saving: locked,
    });
  }, [profile, context, pending, locked, onEditStateChange]);
  useEffect(() => {
    if (embedded || activeTab) return;
    const select = () => {
      const key = window.location.hash.slice(1);
      if (["profile", "calendar", "history"].includes(key))
        setTab(key as "profile" | "calendar" | "history");
    };
    select();
    window.addEventListener("hashchange", select);
    return () => window.removeEventListener("hashchange", select);
  }, [embedded, activeTab]);
  useEffect(() => {
    if (!context) return;
    const abort = new AbortController();
    loadConstraints(
      { start: context.local_today, end: addDays(context.local_today, 6) },
      abort.signal,
    )
      .then((c) => {
        if (!abort.signal.aborted && c.athlete_id === context.athlete_id)
          setSchedule(c);
      })
      .catch(() => {
        /* The calendar step offers a concrete reload/error state. */
      });
    return () => abort.abort();
  }, [context]);
  function report(text: string) {
    setError(text);
    requestAnimationFrame(() => {
      status.current?.focus({ preventScroll: true });
      status.current?.scrollIntoView({ block: "nearest" });
    });
  }
  useEffect(() => {
    if (!context) return;
    const base = context;
    let active = true;
    const refresh = () => {
      if (sending.current || pending || busy) return;
      void loadContext().then((fresh) => {
        if (!active || fresh.athlete_id !== base.athlete_id || sending.current) return;
        setProfile((draft) => retainProfileEdits(editingProfile(fresh), draft, editingProfile(base)));
        install(fresh, false);
      }).catch(() => { /* Explicit reload remains available. */ });
    };
    const storage = (event: StorageEvent) => { if (event.key === bodyChangedKey(base.athlete_id)) refresh(); };
    window.addEventListener(LOCAL_REFRESH_EVENT, refresh); window.addEventListener("focus", refresh); window.addEventListener("storage", storage);
    return () => { active = false; window.removeEventListener(LOCAL_REFRESH_EVENT, refresh); window.removeEventListener("focus", refresh); window.removeEventListener("storage", storage); };
  }, [context, pending, busy]);
  function install(c: Context, replace: boolean) {
    setContext(c);
    setFrozen(c.profile?.artifact.imported_observations ?? []);
    if (replace) {
      setProfile(
        editingProfile(c),
      );
      setFormKey(c.profile?.artifact.content_hash ?? "new");
      setCalendar(
        (c.availability?.artifact.proposal.data as Calendar) ??
          resizeCalendar(
            null,
            c.local_today,
            addDays(c.local_today, 13),
            c.timezone_name,
          ),
      );
    }
  }
  useEffect(() => {
    const abort = new AbortController();
    Promise.all([
      loadContext(abort.signal),
      getJSON("periods", abort.signal).then(readPeriods),
    ])
      .then(([c, p]) => {
        if (abort.signal.aborted) return;
        install(c, true);
        setPeriods(p.filter((p) => p.period_type === "MESOCYCLE"));
        setError("");
      })
      .catch((e) => {
        if (!abort.signal.aborted) report(message(e));
      });
    return () => abort.abort();
  }, [reload]);
  useEffect(
    () => () => {
      stop.current = true;
    },
    [],
  );
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try {
        const saved = sessionStorage.getItem(PENDING_KEY);
        if (saved) setPending(readQueue(saved));
      } catch {
        setBlocked(true);
        report(
          "A függő mentés nem olvasható. Új írás előtt ellenőrizd a korábbi mentéseket és a böngésző tárhelyét.",
        );
      }
      setReady(true);
    });
    return () => {
      active = false;
    };
  }, []);
  async function search(first: string, last: string) {
    if (locked || !context) return;
    setBusy(true);
    setError("");
    try {
      dates(first, last);
      if (last > context.local_today)
        throw new Error("A történelmi időszak nem nyúlhat a jövőbe.");
      const items = await history(first, last);
      setCandidates(items);
      setProfile((p) => ({
        ...p,
        source_window: { start_date: first, end_date: last },
      }));
      setSuccess(
        `${items.length} átvételi javaslat betöltve. Válaszd ki a felhasználandó adatokat.`,
      );
    } catch (e) {
      report(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function run(queue: PendingQueue, preserveDraft = false, retainedDraft?: { draft: Profile; base?: Profile }): Promise<{ context: Context; profile: Profile } | null> {
    if (sending.current || !context) return null;
    if (queue.athlete_id !== context.athlete_id) {
      report(
        "A függő kérés másik sportolóhoz tartozik; nem küldhető el a jelenlegi felhasználó adataihoz.",
      );
      return null;
    }
    const retained = retainedDraft ?? (preserveDraft ? { draft: profile, base: editingProfile(context) } : null);
    let settledDraft = profile;
    sending.current = true;
    stop.current = false;
    setBusy(true);
    setRejected(false);
    setError("");
    let remaining = queue;
    let newerDraftRemains = false;
    let confirmedProfile: { saved: Profile; draft: Profile } | null = null;
    try {
      while (remaining.items.length) {
        setProgress(`Még ${remaining.items.length} lépés van hátra.`);
        const saved = await (preserveDraft ? recoverPending(remaining.items[0], queue.athlete_id) : send(remaining.items[0]));
        if (saved.artifact.athlete_id !== queue.athlete_id)
          throw new Error("A bizonylat másik sportolóhoz tartozik.");
        applyReceipt(saved, retained);
        if (retained && saved.artifact.kind === "profile") {
          const data = saved.artifact.proposal.data as Profile;
          const changes = profileChanges(retainProfileEdits(data, retained.draft, retained.base), data);
          newerDraftRemains = changes.personal || changes.sports || changes.history;
        }
        if (saved.artifact.kind === "profile") {
          const data = saved.artifact.proposal.data as Profile;
          confirmedProfile = { saved: data, draft: retained ? retainProfileEdits(data, retained.draft, retained.base) : data };
        }
        const next = { ...remaining, items: remaining.items.slice(1) };
        if (next.items.length)
          sessionStorage.setItem(PENDING_KEY, JSON.stringify(next));
        else sessionStorage.removeItem(PENDING_KEY);
        setPending(next.items.length ? next : null);
        remaining = next;
        if (stop.current) break;
      }
      const fresh = await loadContext();
      if (fresh.athlete_id !== queue.athlete_id) throw new Error("Közben megváltozott a felhasználó. Töltsd újra az oldalt.");
      install(fresh, false);
      if (confirmedProfile) {
        const saved = editingProfile(fresh);
        if (!saved) throw new Error("A visszaigazolt személyes adatok most nem olvashatók. Töltsd újra az oldalt.");
        const draft = retainProfileEdits(saved, confirmedProfile.draft, confirmedProfile.saved);
        setProfile(draft); settledDraft = draft;
        const changes = profileChanges(draft, saved);
        newerDraftRemains = changes.personal || changes.sports || changes.history;
      }
      window.dispatchEvent(new Event(LOCAL_REFRESH_EVENT));
      if (!remaining.items.length) {
        setSuccess(
          queue.items[0].operation === "polar-imports"
            ? "Az órás lekérések befejeződtek. A nyers adatok megmaradtak; a profilba külön választhatod ki a felismert megfigyeléseket."
            : newerDraftRemains ? "A korábbi mentés sikeres. A közben beírt változtatások megmaradtak; ezeket még külön mentsd el." : "A sportolói adatok mentése igazolt.",
        );
        if (queue.history_window) {
          setCandidates(
            await history(
              queue.history_window.start_date,
              queue.history_window.end_date,
            ),
          );
          setProfile((p) => ({ ...p, source_window: queue.history_window! }));
        }
      } else
        setSuccess(
          "A lekérés a következő napi kérés előtt megállt. Később folytatható.",
        );
      return remaining.items.length ? null : { context: fresh, profile: settledDraft };
    } catch (e) {
      setRejected(
        e instanceof SetupHTTPError && e.status >= 400 && e.status < 500,
      );
      report(`${message(e)} A művelet az eredeti adatokkal folytatható.`);
      return null;
    } finally {
      sending.current = false;
      setBusy(false);
      setProgress("");
    }
  }
  function applyReceipt(saved: Receipt, retained: { draft: Profile; base?: Profile } | null = null) {
    const a = saved.artifact;
    if (a.kind === "profile") {
      setProfile(retained ? retainProfileEdits(a.proposal.data as Profile, retained.draft, retained.base) : a.proposal.data as Profile);
      setFrozen(a.imported_observations ?? []);
      setFormKey(a.content_hash);
    } else if (a.kind === "availability") {
      setCalendar(a.proposal.data as Calendar);
      setReview(null);
    }
  }
  async function stage(queue: PendingQueue, retainedDraft?: { draft: Profile; base?: Profile }) {
    if (sending.current || blocked || !ready || !context || queue.athlete_id !== context.athlete_id) return null;
    try {
      const existing = sessionStorage.getItem(PENDING_KEY);
      if (existing && existing !== JSON.stringify(queue)) throw Error("Előbb ellenőrizd a korábbi mentés eredményét.");
      sessionStorage.setItem(PENDING_KEY, JSON.stringify(queue));
      if (sessionStorage.getItem(PENDING_KEY) !== JSON.stringify(queue)) throw Error("A böngésző nem őrizte meg a mentést.");
      setPending(queue); setSuccess("");
      return await run(queue, false, retainedDraft);
    } catch (e) { report(message(e)); return null; }
  }
  const recoverableProfile = !!pending && pending.athlete_id === context?.athlete_id && pending.items.every((item) => item.operation === "profiles");
  const profileSaveDisabled = busy || blocked || !ready || !context || (!!pending && !recoverableProfile);
  const profileSaveHint = busy ? "Mentés folyamatban."
    : !context || !ready ? "Az adatok betöltése után menthető."
    : blocked ? "A böngészőben tárolt korábbi mentést előbb ellenőrizni kell."
    : pending && !recoverableProfile ? "Előbb fejezd be a fent jelzett korábbi adatátvételt vagy edzésidő-mentést."
    : pending ? "Előbb ellenőrizzük a korábbi mentést, majd elmentjük ennek a blokknak az új adatait."
    : "A gomb ennek a blokknak az adatait menti. A többi blokk mentetlen módosításai megmaradnak.";
  async function saveProfile(section: ProfileSection = "all") {
    if (!context || sending.current || profileSaveDisabled) return;
    try {
      let source = context, draft = profile;
      if (pending) {
        const recovered = await run(pending, true);
        if (!recovered) return;
        source = recovered.context; draft = recovered.profile;
      }
      const previous = editingProfile(source);
      const data = normalizeProfile(sectionProfile(draft, previous, section), source.local_today);
      const nextDraft = sectionProfile(data, draft, section);
      const body = JSON.stringify({ request_id: crypto.randomUUID(), previous_reference: source.references.profile_reference, data });
      setProfile(nextDraft);
      await stage({ schema_version: "athlete-queue-v0.1", athlete_id: source.athlete_id,
        items: [{ schema_version: "athlete-pending-v0.1", operation: "profiles", body }],
      }, { draft: nextDraft, base: previous });
    } catch (e) { report(message(e)); }
  }
  async function calendarPreview() {
    if (!calendar || !context || locked) return;
    setBusy(true);
    setError("");
    try {
      validateCalendar(calendar);
      const body = JSON.stringify({
        request_id: crypto.randomUUID(),
        previous_reference: context.references.availability_reference,
        data: calendar,
      });
      const result = object(await previewCalendar(body));
      if (
        result.schema_version !== "athlete-setup-v0.1" ||
        result.committed !== false ||
        result.planning_authorized !== false ||
        result.proposal_hash !== (await sha(JSON.parse(body)))
      )
        throw new Error("A naptár előnézete nem egyezik az adatokkal.");
      setReview({
        body,
        coverage: object(object(result.calendar).coverage) as Record<
          string,
          number
        >,
      });
      setSuccess("A naptár előnézete elkészült. Az alábbi gombbal menthető.");
    } catch (e) {
      setReview(null);
      report(message(e));
    } finally {
      setBusy(false);
    }
  }
  function importHistory(first: string, last: string, domain: Domain) {
    if (!context || locked) return;
    try {
      if (last > context.local_today)
        throw new Error("Válassz már elmúlt vagy mai napokat.");
      const items = dates(first, last, 31).map((day) => ({
        schema_version: "athlete-pending-v0.1" as const,
        operation: "polar-imports" as const,
        body: JSON.stringify({ request_id: crypto.randomUUID(), day, domain }),
      }));
      stage({
        schema_version: "athlete-queue-v0.1",
        athlete_id: context.athlete_id,
        history_window: { start_date: first, end_date: last },
        items,
      });
    } catch (e) {
      report(message(e));
    }
  }
  async function discardRejected() {
    if (!rejected || busy || !context) return;
    setBusy(true);
    try {
      const fresh = await loadContext();
      if (fresh.athlete_id !== context.athlete_id) throw new Error("Közben megváltozott a felhasználó. Töltsd újra az oldalt.");
      const draft = retainProfileEdits(editingProfile(fresh), profile, editingProfile(context));
      sessionStorage.removeItem(PENDING_KEY);
      install(fresh, false); setProfile(draft); setPending(null); setRejected(false); setError("");
    } catch (e) { report(message(e)); }
    finally { setBusy(false); }
  }
  const notices = <>
      <div ref={status} tabIndex={-1} className="space-y-3 outline-none">
        {error && <Message error>{error}</Message>}
        {success && <Message>{success}</Message>}
        {progress && <Message>{progress}</Message>}
      </div>
      {pending && <section className="pt-profile-pending" aria-label="Mentés vagy adatátvétel folytatása" role="status">
        <div><strong>{pendingDescription(pending, busy).title}</strong><p>{pendingDescription(pending, busy).detail}</p></div>
        <div className="pt-profile-pending-actions">
          <button type="button" className={buttonClass} disabled={busy || !context || pending.athlete_id !== context.athlete_id} onClick={() => void run(pending, true)}>{busy ? "Folyamatban…" : pendingDescription(pending).action}</button>
          {busy && <button type="button" className={secondaryClass} onClick={() => { stop.current = true; }}>Megállítás az aktuális lépés után</button>}
          {pending.athlete_id !== context?.athlete_id && context && <p>Ez a félbemaradt művelet másik felhasználóhoz tartozik.</p>}
          {rejected && !busy && <button type="button" className={secondaryClass} onClick={() => void discardRejected()}>Elutasított művelet lezárása</button>}
        </div>
      </section>}
  </>;
  function profileForm(section: "all" | "personal" | "sports") {
    if (!context) return <div role="status">Személyes adatok betöltése…{error && <button type="button" className={secondaryClass} onClick={() => setReload((n) => n + 1)}>Betöltés újra</button>}</div>;
    const reviewReasons = context.current_review?.reasons.filter((code) => section === "all" || (section === "personal" ? code === "AGE_UNKNOWN" : code !== "AGE_UNKNOWN")) ?? [];
    return <form onSubmit={(e) => { e.preventDefault(); void saveProfile(section); }}>
      {renderPanels && reviewReasons.length > 0 && <p className="pt-options-meta">A mentett adatok alapján még pontosítandó: {reviewReasons.map((code) => reasonLabels[code] ?? code).join("; ")}.</p>}
      <fieldset disabled={busy || blocked || !ready} className="space-y-6">
        <ProfileForm key={formKey} value={profile} onChange={setProfile} today={context.local_today} planning={embedded} section={section} lastMass={context.body_mass?.current ?? null} />
      </fieldset>
      <SaveActionButton saveLabel={section === "sports" ? "Sportelőélet mentése" : "Személyes adatok mentése"} saveHint={profileSaveHint} className={buttonClass + " mt-5"} type="submit" disabled={profileSaveDisabled} title={profileSaveHint}>
        {section === "sports" ? "Sportelőélet mentése" : embedded ? "Személyes adatok mentése" : "Felmérés mentése"}
      </SaveActionButton>
      <SaveActionHint>{profileSaveHint}</SaveActionHint>
      {!embedded && <button className={secondaryClass + " mt-5"} type="button" onClick={() => setTab("calendar")}>Tovább: mikor érek rá? →</button>}
    </form>;
  }
  function historyForm() {
    if (!context) return <div role="status">Mérések és előzmények betöltése…{error && <button type="button" className={secondaryClass} onClick={() => setReload((n) => n + 1)}>Betöltés újra</button>}</div>;
    return <form onSubmit={(e) => { e.preventDefault(); void saveProfile("history"); }}>
      <fieldset disabled={busy || blocked || !ready} className="space-y-6">
        <HistoryForm value={profile} onChange={setProfile} context={context} candidates={candidates} frozen={frozen}
          onSearch={(a, b) => void search(a, b)} onImport={importHistory} busy={locked} onError={report} />
      </fieldset>
      <SaveActionButton saveLabel="Mérések és kiválasztott adatok mentése" saveHint={profileSaveHint} className={buttonClass + " mt-5"} type="submit" disabled={profileSaveDisabled} title={profileSaveHint}>Felmérés és kiválasztott adatok mentése</SaveActionButton>
    </form>;
  }
  if (renderPanels) return renderPanels({ personal: profileForm("personal"), sports: profileForm("sports"), history: historyForm(), notices });
  return (
    <div className={`space-y-6${embedded ? " pt-athlete-planning" : ""}`}>
      {notices}
      {!context ? (
        <Card title="Sportolói felmérés betöltése">
          <p className="mb-4 text-sm">A sportoló adatait töltjük be.</p>
          <button
            className={secondaryClass}
            onClick={() => setReload((n) => n + 1)}
          >
            Betöltés újra
          </button>
        </Card>
      ) : (
        <>
          {!embedded && (
            <SetupProgress
              context={context}
              schedule={schedule}
              active={tab}
              onSelect={setTab}
            />
          )}
          {context.current_review &&
            (!embedded ||
              (tab === "profile" &&
                context.current_review.global_entry_gate !== "OPEN")) && (
              <Card title="Jelenlegi tervezési keret">
                <p className="font-semibold">
                  {gateLabels[context.current_review.global_entry_gate] ??
                    context.current_review.global_entry_gate}
                </p>
                <p className="mt-2 text-sm">
                  Életkor:{" "}
                  {context.current_review.age_years ?? "még nem ismert"} ·
                  értékelés napja: {context.current_review.evaluated_on}
                </p>
                {!!context.current_review.reasons.length && (
                  <ul className="mt-3 list-disc pl-5 text-sm leading-6">
                    {context.current_review.reasons.map((r) => (
                      <li key={r}>{reasonLabels[r] ?? r}</li>
                    ))}
                  </ul>
                )}
                <p className="mt-3 text-xs text-zinc-400">
                  A megadott kereteket felhasználjuk a ciklusok áttekintéséhez.
                  Az egyéni edzésterheléshez külön tervezési döntés szükséges.
                </p>
              </Card>
            )}
          {tab === "profile" && <Card title={profileSection === "sports" ? "Sportelőélet" : embedded ? "Személyes adatok a tervezéshez" : "Sportolói alapok"}>{profileForm(profileSection)}</Card>}
          {tab === "calendar" && (
            <WeeklyAgreement
              owner={context.athlete_id}
              today={context.local_today}
              onSaved={setSchedule}
            />
          )}
          {tab === "calendar" && calendar && (
            <details className="rounded-xl border border-zinc-700 p-4">
              <summary className="cursor-pointer font-medium">
                Napi eltérések és részletes időszaki naptár · opcionális
              </summary>
              <Card title="Naponkénti edzéslehetőségek">
                <p className="mb-4 text-sm leading-6">
                  A szokásos hetet a fenti időmegállapodás adja. Ezt a részletes
                  naptárt csak az eltérő napokhoz vagy egy külön időszakhoz
                  szükséges kitölteni. Egy elérhetetlennek jelölt nap felülírja
                  a heti lehetőséget.
                </p>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void calendarPreview();
                  }}
                >
                  <fieldset disabled={locked} className="space-y-6">
                    <CalendarForm
                      key={
                        calendar.start_date +
                        calendar.end_date +
                        (calendar.mesocycle_id ?? "")
                      }
                      value={calendar}
                      periods={periods}
                      onError={report}
                      onChange={(v) => {
                        setCalendar(v);
                        setReview(null);
                      }}
                    />
                    <p className="text-sm">
                      Szerkesztett időszak: {calendar.start_date} –{" "}
                      {calendar.end_date}
                    </p>
                    <button className={buttonClass} type="submit">
                      Naptár ellenőrzése és áttekintése
                    </button>
                  </fieldset>
                </form>
                {review && (
                  <div className="mt-6 space-y-4 rounded-xl border border-teal-500/50 p-4">
                    <p className="font-semibold">
                      Mentendő naptár: {calendar.start_date} –{" "}
                      {calendar.end_date}
                    </p>
                    <p className="text-sm">
                      Elérhető: {review.coverage.available} nap · Nem elérhető:{" "}
                      {review.coverage.unavailable} nap · Még nincs megadva:{" "}
                      {review.coverage.unknown} nap.
                    </p>
                    <button
                      className={buttonClass}
                      disabled={locked}
                      onClick={() =>
                        stage({
                          schema_version: "athlete-queue-v0.1",
                          athlete_id: context.athlete_id,
                          items: [
                            {
                              schema_version: "athlete-pending-v0.1",
                              operation: "availability",
                              body: review.body,
                            },
                          ],
                        })
                      }
                    >
                      Naptár mentése
                    </button>
                  </div>
                )}
              </Card>
            </details>
          )}
          {tab === "history" && <Card title="Mérések és órás adatok">{historyForm()}</Card>}
          {!embedded && (
            <>
              <div className="flex flex-wrap gap-3">
                <Link className={secondaryClass} href="/planning-cycles">
                  Tovább a felkészülés és ciklusok tervezéséhez
                </Link>
                <Link className={secondaryClass} href="/planning-goals">
                  Ciklusonkénti képességcélok és mérési protokollok
                </Link>
              </div>
              <p className="text-xs leading-5 text-zinc-400">
                A lap részei között váltva a szerkesztett adatok megmaradnak.
                Oldalelhagyás előtt mentsd el a felmérést és külön a naptárt.
              </p>
            </>
          )}
        </>
      )}
    </div>
  );
}
