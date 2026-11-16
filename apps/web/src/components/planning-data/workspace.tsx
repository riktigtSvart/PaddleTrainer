"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { addDays } from "@/lib/planning-cycles/contracts";
import type { Detail } from "@/lib/planning-cycles/contracts";
import { loadCurrentDetail, loadPage } from "@/lib/planning-cycles/client";
import { detailedPeriods } from "@/lib/planning-cycles/plan-view";
import { loadPlanningInputs } from "@/lib/planning-cycles/inputs";
import { loadContext } from "@/lib/athlete-setup/client";
import type { Context, Profile } from "@/lib/athlete-setup/contracts";
import { loadOptions } from "@/lib/training-options/client";
import type { OptionsContext } from "@/lib/training-options/contracts";
import { loadAssessment } from "@/lib/initial-assessment/client";
import { loadConstraints } from "@/lib/calendar/constraint-client";
import type { ScheduleContext } from "@/lib/calendar/constraints";
import { loadAutomatic } from "@/lib/planning-data/automation";
import { LOCAL_REFRESH_EVENT } from "@/lib/data-connections/preferences";
import AthleteWorkspace from "@/components/athlete-setup/workspace";
import type { AthletePanels } from "@/components/athlete-setup/workspace";
import Icon from "@/components/ui/icon";
import { BlockSaveProvider, BlockSaveScope, BlockSaveFooter } from "./save-actions";
import { profileReadiness } from "@/lib/planning-data/profile-state";
import type { ProfileEditState } from "@/lib/planning-data/profile-state";
import OptionsWorkspace from "@/components/training-options/workspace";
import AssessmentWorkspace from "@/components/initial-assessment/workspace";
import type { AssessmentEditState } from "@/components/initial-assessment/workspace";
import GuidedWorkspace from "@/components/guided-strength/workspace";
import type { GuidedSelection } from "@/components/guided-strength/workspace";
import QuickEditor from "@/components/calendar/quick-editor";
import type { EditRequest } from "@/components/calendar/quick-editor";
import AutomaticPlanning from "./automation";
import SportGoalsWorkspace from "./sport-goals";
import { currentGoalPrograms } from "@/lib/planning-data/sport-goals";
import { NAVIGATION_EVENT } from "@/lib/ui/navigation";

export const setupSteps = [
  { key: "personal", label: "Személyes alapadatok", help: "Születési idő, biológiai nem, magasság és testtömeg." },
  { key: "sports", label: "Sportelőélet", help: "Először a sportolás keretei: korlátozások, heti edzéskeret és visszatérés. Utána a fő-, kiegészítő és szabadidős sportok, szintek és tapasztalatok." },
  { key: "goals", label: "Sportcélok és felkészülés", help: "Olimpiai ciklus, szezon, célverseny vagy általános rekreáció; versenyek, dátumok és fejlesztési célok." },
  { key: "locations", label: "Edzéshelyszínek", help: "Elérhető sportok és felszerelések. Egy helyszín részletei a saját kártyájában nyílnak meg." },
  { key: "schedule", label: "Általános edzésrend", help: "Melyik helyszínen, melyik napon és mikor tudsz edzeni? A napi eltérések külön módosíthatók." },
  { key: "assessment", label: "Állapotfelmérés", help: "Először kérdések és ismert adatok, majd a célhoz szükséges gyakorlati felmérések és a tervezés indítása." },
] as const;
type Step = typeof setupSteps[number]["key"];
type Loaded = { athlete: Context; options: OptionsContext; schedule: ScheduleContext };
const aliases: Record<string, Step> = { profile: "personal", history: "assessment", goal: "goals", strategy: "goals", week: "schedule", plan: "assessment" };
export function setupStep(hash: string): Step | null { return setupSteps.find((s) => s.key === hash)?.key ?? aliases[hash] ?? null; }
const text = (e: unknown) => e instanceof Error ? e.message : "A mentett adatok nem tölthetők be.";

export default function PlanningDataWorkspace() {
  const router = useRouter();
  const [loaded, setLoaded] = useState<Loaded | null>(null), [selected, setSelected] = useState<Detail | null>(null);
  const [step, setStep] = useState<Step>("personal"), [visited, setVisited] = useState<Set<Step>>(new Set(["personal"]));
  const [reload, setReload] = useState(0), [error, setError] = useState(""), [strategyError, setStrategyError] = useState("");
  const [assessmentSaved, setAssessmentSaved] = useState(false), [strategyReady, setStrategyReady] = useState(false);
  const [profileEdit, setProfileEdit] = useState<ProfileEditState>({ personal: false, sports: false, history: false, profilePending: false, saving: true });
  const [assessmentEdit, setAssessmentEdit] = useState<AssessmentEditState | null>(null);
  const [assessmentRequest, setAssessmentRequest] = useState<{serial: number; step: number}>();
  const [assessmentTab, setAssessmentTab] = useState<"questions" | "history" | "tests">("questions");
  const [guidedSelection, setGuidedSelection] = useState<GuidedSelection>();
  const [weekOpen, setWeekOpen] = useState(false), [goalsDirty, setGoalsDirty] = useState(false);
  const [reminder, setReminder] = useState<EditRequest | null>(null), [reminderLocked, setReminderLocked] = useState(true), [reminderNotice, setReminderNotice] = useState("");
  const initialized = useRef(false), identity = useRef<string | null>(null);
  const refresh = useCallback(() => setReload((n) => n + 1), []);
  const open = useCallback((key: Step) => {
    setStep(key); setVisited((v) => new Set([...v, key]));
    window.history.replaceState(null, "", `#${key}`); window.dispatchEvent(new Event(NAVIGATION_EVENT));
  }, []);
  const selectProgram = useCallback((detail: Detail) => {
    identity.current = detail.program.artifact.artifact_id; setSelected(detail);
    try { sessionStorage.setItem(`paddletrainer.journey.program.v1:${detail.program.artifact.athlete_id}`, identity.current); } catch { /* Navigation preference only. */ }
    refresh();
  }, [refresh]);
  useEffect(() => {
    window.addEventListener(LOCAL_REFRESH_EVENT, refresh);
    const hash = () => { const key = setupStep(window.location.hash.slice(1)); if (key) { setStep(key); setVisited((v) => new Set([...v, key])); } };
    window.addEventListener("hashchange", hash);
    return () => { window.removeEventListener(LOCAL_REFRESH_EVENT, refresh); window.removeEventListener("hashchange", hash); };
  }, [refresh]);
  useEffect(() => {
    const abort = new AbortController();
    void Promise.all([loadContext(abort.signal), loadOptions(undefined, abort.signal), loadConstraints(null, abort.signal), loadPage(0, abort.signal), loadAssessment(abort.signal)])
      .then(async ([athlete, options, schedule, history, assessment]) => {
        if ([options.athlete_id, schedule.athlete_id, assessment.athlete_id].some((owner) => owner !== athlete.athlete_id)) throw Error("A mentett adatok eltérő sportolóhoz tartoznak.");
        const automatic = await loadAutomatic(athlete.athlete_id, abort.signal);
        let id = identity.current;
        try { id ??= sessionStorage.getItem(`paddletrainer.journey.program.v1:${athlete.athlete_id}`); } catch { /* Optional. */ }
        const currentPrograms = currentGoalPrograms(history.items);
        id ??= automatic.policy?.proposal.program_reference?.artifact_id ?? currentPrograms.find((item) => !item.artifact.proposal.end_date || item.artifact.proposal.end_date >= athlete.local_today)?.artifact.artifact_id ?? null;
        const detail = id ? await loadCurrentDetail(id, abort.signal) : null;
        if (detail && detail.program.artifact.athlete_id !== athlete.athlete_id) throw Error("A felkészülés másik sportolóhoz tartozik.");
        if (abort.signal.aborted) return;
        identity.current = detail?.program.artifact.artifact_id ?? null;
        setLoaded({ athlete, options, schedule }); setSelected(detail);
        setAssessmentSaved(!!assessment.summary?.form_complete && !assessment.sources_changed); setError("");
        if (!initialized.current) {
          initialized.current = true;
          const initial = setupStep(window.location.hash.slice(1)) ?? (!athlete.profile ? "personal" : "assessment");
          setStep(initial); setVisited((v) => new Set([...v, initial]));
          if (!window.location.hash) { window.history.replaceState(null, "", `#${initial}`); window.dispatchEvent(new Event(NAVIGATION_EVENT)); }
        }
      }).catch((e) => { if (!abort.signal.aborted) setError(text(e)); });
    return () => abort.abort();
  }, [reload]);
  useEffect(() => {
    if (!loaded || !selected) return;
    const abort = new AbortController(), p = selected.program.artifact;
    const first = p.proposal.start_date > loaded.athlete.local_today ? p.proposal.start_date : loaded.athlete.local_today;
    const periods = selected.boundary_revisions.at(-1)?.artifact.periods ?? p.periods;
    const scopes = detailedPeriods(periods, first);
    void Promise.all(scopes.map((period) => {
      const begin = period.start_date > first ? period.start_date : first;
      return loadPlanningInputs({ owner: p.athlete_id, reference: { artifact_id: p.artifact_id, content_hash: p.content_hash }, zone: loaded.athlete.timezone_name, first: begin, last: period.end_date < addDays(begin, 6) ? period.end_date : addDays(begin, 6) }, abort.signal);
    })).then((inputs) => {
      if (abort.signal.aborted) return;
      setStrategyReady(inputs.length > 0 && inputs.every((input) => input.days.length > 0 && input.days.every((d) => d.mesocycle_id && d.capability_roles.length > 0))); setStrategyError("");
    }).catch((e) => { if (!abort.signal.aborted) { setStrategyReady(false); setStrategyError(text(e)); } });
    return () => abort.abort();
  }, [loaded, selected]);
  const p = selected?.program.artifact, periods = selected?.boundary_revisions.at(-1)?.artifact.periods ?? p?.periods ?? [];
  const macro = periods.find((v) => v.period_type === "MACROCYCLE" && v.end_date >= (loaded?.athlete.local_today ?? ""));
  const profile = loaded?.athlete.profile?.artifact.proposal.data as Profile | undefined;
  const profileReady = profileReadiness(profile, loaded?.athlete.current_review);
  const ready: Record<Step, boolean> = {
    personal: profileReady.personal,
    sports: profileReady.sports,
    goals: !!p && strategyReady,
    locations: !!loaded?.options.data.locations.some((v) => !v.archived),
    schedule: !!loaded?.options.data.schedule_start_date && !!loaded.options.data.weekly_slots.length && !loaded.schedule.timezone_review_required,
    assessment: assessmentSaved && !(assessmentEdit?.dirty || assessmentEdit?.sourcesChanged || assessmentEdit?.pending || assessmentEdit?.saving),
  };
  const missing = setupSteps.filter((s) => !ready[s.key]);
  const profileDirty = profileEdit.personal || profileEdit.sports || profileEdit.history;
  const assessmentStepLabels = ["Állapot és keretek", "Erőedzés-előzmények", "Sportágak, cél és helyszín", "Gyakorlatok és jártasság", "Ismert teljesítések átnézése", "Összegzés átnézése"];
  const assessmentIssue = assessmentEdit?.pending ? "A felmérés korábbi mentését még ellenőrizni kell." : assessmentEdit?.sourcesChanged ? "A kezdeti válaszokat a friss személyes, helyszíni vagy céladatokhoz kell aktualizálni és menteni. Az erőfelmérés eredményei megmaradnak." : assessmentEdit?.missingSteps.length ? `A kezdeti kérdéssorban még szükséges: ${assessmentEdit.missingSteps.map(i => assessmentStepLabels[i]).join("; ")}.` : "A kezdeti kérdéssor válaszait még el kell menteni.";
  const reviewAssessment = () => { setAssessmentTab("questions"); setAssessmentRequest(old => ({serial: (old?.serial ?? 0) + 1, step: assessmentEdit?.sourcesChanged ? 5 : assessmentEdit?.missingSteps[0] ?? 5})); };
  const prerequisites = [...missing.map(s => s.key === "assessment" ? assessmentIssue : `${s.label}: a mentett adatok még szükségesek.`),
    ...(profileEdit.personal ? ["A személyes alapadatok módosítását még mentsd el a saját blokkjában."] : []),
    ...(profileEdit.sports ? ["A sportelőélet módosítását még mentsd el a saját blokkjában."] : []),
    ...(profileEdit.history ? ["Az ismert mérések és előzmények változtatásait még mentsd el."] : []),
    ...(goalsDirty ? ["A sportcéloknál mentetlen vagy függő változtatás van."] : []),
    ...(profileEdit.saving ? ["Előbb fejezd be a személyes adatoknál jelzett mentést vagy adatátvételt."] : [])];
  const prerequisiteActions = [...missing.filter(s => s.key !== "assessment").map(s => ({label: `${s.label} megnyitása`, action: () => open(s.key)})),
    ...(!ready.assessment ? [{label: "Felmérési válaszok ellenőrzése", action: reviewAssessment}] : []),
    ...(profileEdit.personal ? [{label: "Személyes adatok mentése a blokkban", action: () => open("personal")}] : []),
    ...(profileEdit.sports ? [{label: "Sportelőélet mentése a blokkban", action: () => open("sports")}] : []),
    ...(profileEdit.history ? [{label: "Mérések és előzmények megnyitása", action: () => setAssessmentTab("history")}] : [])];
  const index = setupSteps.findIndex((s) => s.key === step);
  const afterAssessment = useCallback(() => { window.dispatchEvent(new Event(LOCAL_REFRESH_EVENT)); }, []);
  const hasLoaded = !!loaded;
  useEffect(() => {
    if (!hasLoaded) return;
    const frame = requestAnimationFrame(() => document.getElementById(step)?.scrollIntoView({ block: "start" }));
    return () => cancelAnimationFrame(frame);
  }, [step, hasLoaded]);
  const actions = <div className="pt-data-actions">
    <button type="button" className="pt-button" disabled={index === 0} onClick={() => open(setupSteps[index - 1].key)}>← Előző lépés</button>
    <span>{index + 1} / {setupSteps.length}</span>
    {index < setupSteps.length - 1 ? <button type="button" className="pt-button pt-button-primary" onClick={() => { refresh(); open(setupSteps[index + 1].key); }}>Következő: {setupSteps[index + 1].label} →</button> : <Link className="pt-button" href="/">Naptár megnyitása</Link>}
  </div>;
  return <main className="pt-data-workspace">
    <header><h1>Edzéstervezési alapadatok</h1><p>A blokkok bármikor újranyithatók. A jelzések a mentett adatok állapotát mutatják.</p></header>
    {error && <p role="alert">{error} <button type="button" className="pt-button" onClick={refresh}>Újraolvasás</button></p>}
    {!loaded && !error && <p role="status">Mentett tervezési adatok betöltése…</p>}
    {loaded && <AthleteWorkspace embedded onEditStateChange={setProfileEdit} renderPanels={(panels: AthletePanels) => {
      const content = {
        personal: <>{panels.personal}</>,
        sports: <>{panels.sports}</>,
        goals: visited.has("goals") ? <SportGoalsWorkspace owner={loaded.athlete.athlete_id} sport={profile?.target_sport ?? ""} selected={selected} onSelected={selectProgram} onDirtyChange={setGoalsDirty} /> : null,
        locations: visited.has("locations") ? <OptionsWorkspace mode="locations" /> : null,
        schedule: visited.has("schedule") ? <><OptionsWorkspace mode="schedule" /><details className="pt-data-panel" onToggle={(e) => setWeekOpen(e.currentTarget.open)}><summary>Napi eltérések · a következő hét</summary>{weekOpen && <OptionsWorkspace mode="week" />}</details></> : null,
        assessment: visited.has("assessment") ? <>
<nav className="pt-data-tabs" aria-label="Állapotfelmérés részei">{([
          ["questions", "1. Kérdések és jártasság"], ["history", "2. Ismert mérések és előzmények"], ["tests", "3. Gyakorlati felmérés"],
        ] as const).map(([key, label]) => <button type="button" key={key} className="pt-button" aria-pressed={assessmentTab === key} onClick={() => setAssessmentTab(key)}>{label}</button>)}</nav>
        <div hidden={assessmentTab !== "history"}><BlockSaveScope active={assessmentTab === "history"}>{panels.history}</BlockSaveScope></div>

        <div hidden={assessmentTab !== "questions"}><BlockSaveScope active={assessmentTab === "questions"}><AssessmentWorkspace embedded onSaved={setAssessmentSaved} onStateChange={setAssessmentEdit} navigationRequest={assessmentRequest} onCommitted={afterAssessment} /></BlockSaveScope></div>
        {assessmentTab === "tests" && <>
          <section className="pt-data-panel"><h2>A célhoz szükséges felmérések</h2><p>Az erőfelmérés az alábbi sportági ajánlásokból, a helyszín felszereléséből és a mentett jártasságból indul ki. Az első próbák az alkalmazható kezdő edzésadaghoz adnak adatot; az ismételhetőségi felmérés külön pontosítja az erőállóképességet.</p>
            <div className="pt-context-links"><Link href={macro && p ? `/planning-goals?cycle=${encodeURIComponent(p.artifact_id)}&period=${macro.id}` : "/planning-goals"}>Állóképesség, gyorsaság, technika és más képességek mérési protokolljai</Link><Link href="/personal-response">Terhelés és személyes válaszadatok</Link></div>
            <p className="pt-options-meta">A többi képességhez jelenleg célok, mérési protokollok és eredmények rögzíthetők; külön végrehajtható tesztvezetés az erőfelméréshez érhető el.</p>
            <button type="button" className="pt-button" disabled={reminderLocked || loaded.schedule.timezone_review_required} onClick={() => setReminder((v) => ({ serial: (v?.serial ?? 0) + 1, date: loaded.athlete.local_today, event: null, reminder: { title: "Erőfelmérés · időfoglalás", notes: "A gyakorlatokat és a próbák eredményeit az Edzéstervezési alapadatok → Állapotfelmérés → Gyakorlati felmérés részen rögzítsd. Ez időfoglalás, nem előírt vagy teljesített edzés." } }))}>Felmérési időpont foglalása a naptárban</button>
            {reminderNotice && <p role="status">{reminderNotice}</p>}
          </section>
          <GuidedWorkspace embedded selection={guidedSelection} onCompleted={afterAssessment} onEditIntake={(selected) => {
            setGuidedSelection(selected);
            setAssessmentTab("questions");
            setAssessmentRequest(old => ({ serial: (old?.serial ?? 0) + 1, step: 5 }));
          }} />
        </>}
        {strategyError && <p role="alert">{strategyError}</p>}
        <AutomaticPlanning owner={loaded.athlete.athlete_id} programReference={p ? { artifact_id: p.artifact_id, content_hash: p.content_hash } : null} canEnable={!missing.length && !profileDirty && !goalsDirty && !profileEdit.saving && !assessmentEdit?.saving} prerequisites={prerequisites} prerequisiteActions={prerequisiteActions} onComplete={() => router.push("/")} />

        </> : null,
      };
      return <>
        {panels.notices}
        <div className="pt-setup-blocks">
          {setupSteps.map((item, order) => {
            const expanded = item.key === step;
            const dirty = item.key === "personal" ? profileEdit.personal : item.key === "sports" ? profileEdit.sports : item.key === "assessment" ? profileEdit.history : item.key === "goals" ? goalsDirty : false;
            const pending = ["personal", "sports"].includes(item.key) && profileEdit.profilePending;
            const state = pending ? "pending" : dirty ? "dirty" : ready[item.key] ? "ready" : "missing";
            const label = pending ? "Mentés ellenőrzésre vár" : dirty ? "Mentetlen változtatás" : ready[item.key] ? "Tervezési alap megadva" : "Még szükséges vagy pontosítandó";
            return <section key={item.key} id={item.key} className="pt-setup-block" data-open={expanded} data-state={state}>
              <h2><button type="button" id={`pt-setup-heading-${item.key}`} className="pt-setup-heading" aria-expanded={expanded} aria-controls={`pt-setup-panel-${item.key}`} onClick={() => open(item.key)}>
                <span className="pt-setup-heading-title">{order + 1}. {item.label}</span>
                <span className={`pt-setup-state is-${state}`}><Icon name={state === "ready" ? "check" : state === "missing" ? "alert" : "clock"} /><span>{label}</span></span>
                <span className="pt-setup-chevron" aria-hidden="true"><Icon name="right" /></span>
              </button></h2>
              <div className="pt-setup-content" id={`pt-setup-panel-${item.key}`} role="region" aria-labelledby={`pt-setup-heading-${item.key}`} hidden={!expanded}>
                <BlockSaveProvider>
                <p className="pt-setup-help">{item.help}</p>
                {content[item.key]}
                {dirty && <p className="pt-setup-draft" role="status">A módosítások még nincsenek elmentve. Blokkváltáskor megmaradnak; az űrlap mentésével rögzítheted őket.</p>}
                {item.key !== "goals" && <BlockSaveFooter emptyHint={item.key === "locations" ? "Nyisd meg a helyszín szerkesztését vagy adj hozzá egy újat; az adatait innen is mentheted." : item.key === "assessment" ? "Válaszd ki a felmérés megfelelő részét. A válaszok vagy eredmények mentése innen is elérhető." : "Az adatok betöltése után a mentés innen is elérhető."} />}
                {actions}
                </BlockSaveProvider>
              </div>
            </section>;
          })}
        </div>
      <QuickEditor context={loaded.schedule} request={reminder} disabled={false} toolbarTarget={null} onLockedChange={setReminderLocked} onSaved={() => { setReminderNotice("A felmérés időpontja mentve a naptárban. Az eredményeket itt, a gyakorlati felmérésben adhatod meg."); refresh(); }} />
      </>;
    }} />}
  </main>;
}
