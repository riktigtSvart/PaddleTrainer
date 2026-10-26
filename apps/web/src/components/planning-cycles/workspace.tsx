"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  CycleHTTPError,
  loadCatalog,
  loadDetail,
  loadPage,
  preview,
  send,
} from "@/lib/planning-cycles/client";
import {
  addDays,
  anniversary,
  defaultStructure,
  draftIssues,
  emptyProfile,
  modeLabels,
  normalizeProgram,
  normalizeRevision,
  PENDING_KEY,
  readPending,
  reference,
} from "@/lib/planning-cycles/contracts";
import type {
  Catalog,
  Competition,
  Detail,
  Mode,
  Pending,
  Preview,
  Program,
  Receipt,
  Revision,
  BoundaryRevision,
} from "@/lib/planning-cycles/contracts";
import {
  Area,
  buttonClass,
  Card,
  Field,
  Message,
  secondaryClass,
  Select,
} from "@/components/planning-goals/fields";
import CompetitionEditor from "./competition-editor";
import StructureEditor from "./structure-editor";
import BoundaryEditor from "./boundary-editor";
import GoalEditor, { newGoal } from "./goal-editor";
import AthleteContextBanner from "@/components/athlete-setup/context-banner";
import {
  Competitions,
  ProgramSummary,
  ContextSnapshot,
  Provenance,
  Structure,
} from "./program-details";

const modes = Object.keys(modeLabels) as Mode[];
const descriptions: Record<Mode, string> = {
  olympic: "Több szezonon át felépített felkészülés a kiválasztott játékokra.",
  season: "Egy sportév fő céljai és versenyidőszakai.",
  race: "Egy közelebbi célverseny köré épített felkészülés.",
  recreation: "Folyamatos mozgásprogram, rendszeres célfelülvizsgálattal.",
};
function problem(error: unknown) {
  return error instanceof Error ? error.message : "A művelet nem sikerült.";
}
function nextEdition(c: Catalog, start: string, kind = "summer") {
  return c.olympics.find((e) => e.kind === kind && e.end_date >= start);
}
function emptyProgram(
  mode: Mode,
  c: Catalog,
): { program: Program; end: string } {
  const edition = nextEdition(c, c.local_today);
  const end =
    mode === "olympic"
      ? (edition?.end_date ?? "")
      : mode === "season"
        ? addDays(anniversary(c.local_today), -1)
        : mode === "race"
          ? ""
          : addDays(c.local_today, 83);
  return {
    end,
    program: {
      program_id: crypto.randomUUID(),
      mode,
      title: "",
      sport: "",
      start_date: c.local_today,
      end_date: mode === "recreation" ? null : end,
      olympic_key: mode === "olympic" ? (edition?.key ?? null) : null,
      seasons: [],
      macrocycles: [],
      competitions: [],
      goals: [],
      continued_from: null,
      planning_basis: {
        version: "cycle-planning-basis-v0.1",
        mesocycle_dates: "provisional",
        initial_mesocycle_days: 28,
      },
    },
  };
}

export default function CycleWorkspace() {
  const [athleteRefs, setAthleteRefs] = useState<Program["athlete_context"]>();
  const [catalog, setCatalog] = useState<Catalog | null>(null),
    [history, setHistory] = useState<Receipt[]>([]);
  const [loadError, setLoadError] = useState(""),
    [hasMore, setHasMore] = useState(false),
    [nextOffset, setNextOffset] = useState(0);
  const [reload, setReload] = useState(0),
    [paging, setPaging] = useState(false);
  const [program, setProgram] = useState<Program | null>(null),
    [blockEnd, setBlockEnd] = useState("");
  const [endExplicit, setEndExplicit] = useState(false);
  const [step, setStep] = useState(1),
    [review, setReview] = useState<{ body: string; view: Preview } | null>(
      null,
    );
  const [detail, setDetail] = useState<Detail | null>(null),
    [editing, setEditing] = useState<Revision | null>(null);
  const [boundaryDraft, setBoundaryDraft] = useState<BoundaryRevision | null>(
    null,
  );
  const [pending, setPending] = useState<Pending | null>(null),
    [ready, setReady] = useState(false),
    [blocked, setBlocked] = useState(false);
  const [busy, setBusy] = useState(false),
    [rejected, setRejected] = useState(false),
    [failure, setFailure] = useState(""),
    [success, setSuccess] = useState("");
  const sending = useRef(false),
    detailSequence = useRef(0);
  const status = useRef<HTMLDivElement>(null);
  const locked = busy || !!pending || blocked || !ready;
  function report(text: string) {
    setFailure(text);
    requestAnimationFrame(() => {
      status.current?.focus({ preventScroll: true });
      status.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  }
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      loadCatalog(controller.signal),
      loadPage(0, controller.signal),
    ])
      .then(([c, page]) => {
        if (!controller.signal.aborted) {
          setCatalog(c);
          setHistory(page.items);
          setHasMore(page.has_more);
          setNextOffset(page.items.length);
          setLoadError("");
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setLoadError(problem(e));
      });
    return () => controller.abort();
  }, [reload]);
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try {
        const value = sessionStorage.getItem(PENDING_KEY);
        if (value) {
          setPending(readPending(value));
          setFailure(
            "Korábbi függő ciklusmentés található. A pontosan azonos kérés újraküldésével ellenőrizheted az eredményt.",
          );
        }
      } catch {
        setBlocked(true);
        setFailure(
          "A böngészőben tárolt függő kérés nem olvasható. Új mentés előtt ellenőrizd a mentett programokat és a böngésző tárhelyét.",
        );
      }
      setReady(true);
    });
    return () => {
      active = false;
    };
  }, []);

  function begin(mode: Mode) {
    if (!catalog || locked) return;
    if (!athleteRefs?.profile_reference) {
      report(
        "Először mentsd el a sportolói felmérést, majd frissítsd a felmérést ezen az oldalon.",
      );
      return;
    }
    try {
      const draft = emptyProgram(mode, catalog);
      setProgram({
        ...draft.program,
        ...(athleteRefs ? { athlete_context: athleteRefs } : {}),
      });
      setBlockEnd(draft.end);
      setEndExplicit(false);
      setStep(1);
      setReview(null);
      setEditing(null);
      setBoundaryDraft(null);
      setFailure("");
      setSuccess("");
    } catch (e) {
      report(problem(e));
    }
  }
  function changeEnd(end: string) {
    setEndExplicit(true);
    setBlockEnd(end);
    if (program)
      setProgram({
        ...program,
        end_date: program.mode === "recreation" ? null : end,
      });
  }
  function changeStart(start: string) {
    if (!program || !catalog) return;
    let p = { ...program, start_date: start };
    if (!endExplicit && start && ["season", "recreation"].includes(p.mode)) {
      try {
        const end =
          p.mode === "season"
            ? addDays(anniversary(start), -1)
            : addDays(start, 83);
        setBlockEnd(end);
        p = { ...p, end_date: p.mode === "recreation" ? null : end };
      } catch {
        /* The required date field reports an incomplete edit on submit. */
      }
    }
    if (p.mode === "olympic") {
      const old = catalog.olympics.find((e) => e.key === p.olympic_key);
      const edition =
        old && old.end_date >= start
          ? old
          : nextEdition(catalog, start, old?.kind);
      p = {
        ...p,
        olympic_key: edition?.key ?? null,
        end_date: edition?.end_date ?? "",
      };
      setBlockEnd(edition?.end_date ?? "");
    }
    setProgram(p);
  }
  function changeSport(sport: string) {
    if (!program || !catalog) return;
    let p = { ...program, sport };
    if (program.mode === "olympic") {
      const text = sport.toLowerCase(),
        winter =
          /sí|ski|snow|korcsolya|jég|szkeleton|skeleton|szánkó|luge|curling|bobsleigh|\bbob\b|biathlon|ice hockey/.test(
            text,
          );
      const known = winter || /kajak|kenu|evez|úsz|futás|kerékpár/.test(text);
      if (known) {
        const edition = nextEdition(
          catalog,
          program.start_date,
          winter ? "winter" : "summer",
        );
        p = {
          ...p,
          olympic_key: edition?.key ?? null,
          end_date: edition?.end_date ?? "",
        };
        setBlockEnd(edition?.end_date ?? "");
      }
    }
    setProgram(p);
  }
  function validateStep(until: number): boolean {
    if (!program) return false;
    const issue = draftIssues(program, blockEnd, until)[0];
    if (!issue) return true;
    setStep(issue.step);
    report(issue.message);
    requestAnimationFrame(() => {
      const field = document.getElementsByName(issue.name)[0];
      field?.focus();
      field?.scrollIntoView({ block: "center", behavior: "smooth" });
    });
    return false;
  }
  function stepOne() {
    if (!program || !catalog || !validateStep(1)) return;
    if (!program.goals.length)
      return report(
        "Válassz legalább egy célt, és fogalmazd meg, mit szeretnél elérni.",
      );
    let p = program;
    if (p.mode === "race" && !p.competitions.length)
      p = {
        ...p,
        competitions: [
          {
            key: "target-race",
            title: "",
            start_date: blockEnd,
            end_date: blockEnd,
            precision: "exact",
            priority: "main",
            status: "planned",
            profile: emptyProfile(program.sport),
          },
        ],
      };
    setProgram(p);
    setStep(2);
    setFailure("");
  }
  function changeEvents(events: Competition[]) {
    if (!program) return;
    let p = { ...program, competitions: events };
    const target = events.filter(
      (e) => e.priority === "main" && e.status === "planned",
    );
    if (p.mode === "race" && target.length === 1) {
      setBlockEnd(target[0].end_date);
      p = { ...p, end_date: target[0].end_date };
    }
    setProgram(p);
  }
  function stepTwo() {
    if (!program || !validateStep(2)) return;
    try {
      const oldEnd = program.macrocycles
        .map((m) => m.end_date)
        .sort()
        .at(-1);
      const oldStart = program.macrocycles.map((m) => m.start_date).sort()[0];
      setProgram(
        oldEnd === blockEnd && oldStart === program.start_date
          ? program
          : defaultStructure(program, blockEnd),
      );
      setStep(3);
      setFailure("");
    } catch (e) {
      report(problem(e));
    }
  }
  async function checkPreview() {
    if (!program || sending.current || locked || !validateStep(3)) return;
    setBusy(true);
    setFailure("");
    try {
      const normalized = normalizeProgram(program);
      const view = await preview(normalized);
      setProgram(normalized);
      setReview({ body: JSON.stringify(normalized), view });
      setStep(4);
    } catch (e) {
      report(problem(e));
    } finally {
      setBusy(false);
    }
  }
  async function choose(id: string) {
    const sequence = ++detailSequence.current;
    setEditing(null);
    setBoundaryDraft(null);
    try {
      const result = await loadDetail(id);
      if (sequence === detailSequence.current) {
        setDetail(result);
        setFailure("");
      }
    } catch (e) {
      if (sequence === detailSequence.current) report(problem(e));
    }
  }
  async function perform(request: Pending) {
    if (sending.current || blocked || !ready) return;
    sending.current = true;
    setBusy(true);
    setFailure("");
    setSuccess("");
    setRejected(false);
    let saved: Receipt;
    try {
      // Retain the exact body before transport. A remount never submits it automatically.
      sessionStorage.setItem(PENDING_KEY, JSON.stringify(request));
      setPending(request);
      saved = await send(request);
    } catch (e) {
      setRejected(
        e instanceof CycleHTTPError && e.status >= 400 && e.status < 500,
      );
      report(problem(e));
      setBusy(false);
      sending.current = false;
      return;
    }
    try {
      sessionStorage.removeItem(PENDING_KEY);
      setPending(null);
      setProgram(null);
      setReview(null);
      setEditing(null);
      setSuccess(
        saved.reused
          ? "A korábban mentett, azonos kérés eredménye visszaállítva."
          : "A szerver igazolta a tartós mentést.",
      );
    } catch {
      report(
        "A szerver igazolta a mentést, de a függő kérés helyi lezárása nem sikerült. Az azonos kérés biztonságosan újraküldhető.",
      );
      setBusy(false);
      sending.current = false;
      return;
    }
    const proposal = JSON.parse(request.body);
    const id =
      request.operation === "programs"
        ? saved.artifact.artifact_id
        : proposal.program_reference.artifact_id;
    await choose(id);
    setReload((n) => n + 1);
    setBusy(false);
    sending.current = false;
  }
  function editAgain() {
    if (!pending || !rejected) return;
    try {
      sessionStorage.removeItem(PENDING_KEY);
      if (pending.operation === "programs") {
        const p = JSON.parse(pending.body) as Program;
        setProgram(p);
        setBlockEnd(
          p.macrocycles
            .map((m) => m.end_date)
            .sort()
            .at(-1) ?? "",
        );
        setStep(3);
      } else if (pending.operation === "competition-revisions")
        setEditing(JSON.parse(pending.body) as Revision);
      else setBoundaryDraft(JSON.parse(pending.body) as BoundaryRevision);
      setPending(null);
      setReview(null);
      setRejected(false);
      setFailure("");
    } catch (e) {
      report(problem(e));
    }
  }
  async function more() {
    if (paging) return;
    setPaging(true);
    try {
      const page = await loadPage(nextOffset);
      setHistory((old) => {
        const ids = new Set(old.map((r) => r.artifact.artifact_id));
        return [
          ...old,
          ...page.items.filter((r) => !ids.has(r.artifact.artifact_id)),
        ];
      });
      setNextOffset(nextOffset + page.items.length);
      setHasMore(page.has_more);
    } catch (e) {
      report(problem(e));
    } finally {
      setPaging(false);
    }
  }
  function refine() {
    if (!detail || locked) return;
    const latest = detail.competition_revisions.at(-1)?.artifact;
    if (latest && latest.proposal.revision >= 64)
      return report(
        "A 64 megőrzött pontosítás elérhető; újabb változat ebben a láncban már nem hozható létre.",
      );
    setProgram(null);
    setBoundaryDraft(null);
    setEditing({
      program_reference: reference(detail.program.artifact),
      revision: latest ? latest.proposal.revision + 1 : 1,
      previous_reference: latest ? reference(latest) : null,
      competitions: structuredClone(
        latest?.proposal.competitions ??
          detail.program.artifact.proposal.competitions,
      ),
      rationale: "",
    });
  }
  function reviewBoundary() {
    if (!detail || !catalog || locked) return;
    const changes = detail.boundary_revisions;
    if (changes.length >= 64)
      return report("A 64 megőrzött ciklushatár-változat elérhető.");
    const periods =
      changes.at(-1)?.artifact.periods ?? detail.program.artifact.periods;
    const mesos = periods
      .filter((p) => p.period_type === "MESOCYCLE")
      .sort((a, b) => a.start_date.localeCompare(b.start_date));
    const i = mesos.findIndex(
      (p, i) =>
        p.end_date >= catalog.local_today &&
        mesos[i + 1]?.parent_id === p.parent_id &&
        mesos[i + 1]?.start_date === addDays(p.end_date, 1),
    );
    if (i < 0)
      return report(
        "Nincs mai vagy jövőbeli, módosítható közös mezociklushatár.",
      );
    setProgram(null);
    setEditing(null);
    setFailure("");
    setBoundaryDraft({
      program_reference: reference(detail.program.artifact),
      revision: changes.length + 1,
      previous_reference: changes.length
        ? reference(changes.at(-1)!.artifact)
        : null,
      competition_reference: reference(
        detail.competition_revisions.at(-1)?.artifact ??
          detail.program.artifact,
      ),
      left_period_id: mesos[i].id,
      right_period_id: mesos[i + 1].id,
      new_end_date: mesos[i].end_date,
      reason: "fatigue",
      observations: "",
      rationale: "",
      review_training_load: true,
    });
  }
  function continueRecreation() {
    if (!detail || !catalog || locked) return;
    try {
      const previous = detail.program.artifact;
      const start = [
        addDays(
          previous.periods
            .map((p) => p.end_date)
            .sort()
            .at(-1)!,
          1,
        ),
        catalog.local_today,
      ]
        .sort()
        .at(-1)!;
      const p = {
        ...structuredClone(previous.proposal),
        program_id: crypto.randomUUID(),
        start_date: start,
        continued_from: reference(previous),
        title: (previous.proposal.title + " – folytatás").slice(0, 200),
        seasons: [],
        macrocycles: [],
        competitions: [],
        ...(athleteRefs ? { athlete_context: athleteRefs } : {}),
        goals: previous.proposal.goals.map((g) =>
          ["weight_loss", "weight_maintenance"].includes(g.key)
            ? {
                ...g,
                details: g.details ?? newGoal(g.key).details,
                body_mass: {
                  current_kg: "",
                  ...(g.key === "weight_loss"
                    ? { target_kg: g.body_mass?.target_kg ?? "" }
                    : {}),
                },
              }
            : g,
        ),
      };
      setProgram(p);
      setBlockEnd(addDays(start, 83));
      setEndExplicit(false);
      setStep(1);
      setEditing(null);
      setReview(null);
      setFailure("");
      setSuccess("");
    } catch (e) {
      report(problem(e));
    }
  }

  return (
    <div className="space-y-7">
      <div
        ref={status}
        tabIndex={-1}
        className="space-y-3 outline-none"
        aria-live="polite"
      >
        {failure && <Message error>{failure}</Message>}
        {success && <Message>{success}</Message>}
        {pending && (
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              className={buttonClass}
              disabled={busy || blocked}
              onClick={() => void perform(pending)}
            >
              {busy ? "Ellenőrzés…" : "Ugyanaz a cikluskérés újraküldése"}
            </button>
            {rejected && (
              <button
                type="button"
                className={secondaryClass}
                disabled={busy}
                onClick={editAgain}
              >
                Vissza a javításhoz
              </button>
            )}
          </div>
        )}
      </div>
      <AthleteContextBanner onChange={setAthleteRefs} />
      {program &&
        athleteRefs?.profile_reference &&
        JSON.stringify(program.athlete_context) !==
          JSON.stringify(athleteRefs) && (
          <button
            type="button"
            className={secondaryClass}
            disabled={locked}
            onClick={() => {
              setProgram({ ...program, athlete_context: athleteRefs });
              setReview(null);
              if (step === 4) setStep(3);
            }}
          >
            Friss felmérés átvétele a szerkesztett tervbe
          </button>
        )}
      {loadError && (
        <Message error>
          {loadError}{" "}
          <button
            type="button"
            className="underline"
            onClick={() => setReload((n) => n + 1)}
          >
            Betöltés újra
          </button>
        </Message>
      )}
      {!catalog && !loadError && <Message>Ciklusadatok betöltése…</Message>}
      {catalog && (
        <>
          <Card title="Mire szeretnél felkészülni?">
            <div className="grid gap-3 sm:grid-cols-2">
              {modes.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  disabled={locked}
                  aria-pressed={program?.mode === mode}
                  aria-label={modeLabels[mode]}
                  aria-describedby={`entry-mode-${mode}`}
                  className={`${secondaryClass} text-left ${program?.mode === mode ? "border-teal-300 ring-1 ring-teal-300" : ""}`}
                  onClick={() => begin(mode)}
                >
                  <span className="block font-semibold">
                    {modeLabels[mode]}
                  </span>
                  <span
                    id={`entry-mode-${mode}`}
                    className="mt-2 block text-xs leading-5 text-zinc-400"
                  >
                    {descriptions[mode]}
                  </span>
                </button>
              ))}
            </div>
            <p className="mt-4 text-sm leading-6 text-zinc-400">
              Mindegyik út legalább egy makrociklust és hozzá tartozó
              mezociklusokat hoz létre. A mentés előtt áttekintheted a teljes
              bontást.
            </p>
          </Card>
          {program && (
            <Card
              title={`${step}. lépés · ${["", "Időkeret és célok", "Versenyek", "Ciklusbontás", "Áttekintés és mentés"][step]}`}
            >
              <ol
                aria-label="Tervezés lépései"
                className="mb-5 flex flex-wrap gap-3 text-sm"
              >
                {[
                  "Időkeret és célok",
                  "Versenyek",
                  "Ciklusbontás",
                  "Áttekintés és mentés",
                ].map((label, i) => (
                  <li
                    key={label}
                    aria-current={step === i + 1 ? "step" : undefined}
                    className={
                      step === i + 1
                        ? "font-semibold text-teal-200"
                        : "text-zinc-400"
                    }
                  >
                    {i + 1}. {label}
                  </li>
                ))}
              </ol>
              {failure && (
                <div className="mb-5">
                  <Message error>{failure}</Message>
                </div>
              )}
              <fieldset disabled={locked} className="space-y-6">
                {step === 1 && (
                  <form
                    className="space-y-5"
                    onSubmit={(e) => {
                      e.preventDefault();
                      stepOne();
                    }}
                  >
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field
                        label="Felkészülés neve"
                        name="title"
                        value={program.title}
                        required
                        maxLength={200}
                        onChange={(e) =>
                          setProgram({ ...program, title: e.target.value })
                        }
                      />
                      <Field
                        label="Sportág / szakág"
                        name="sport"
                        list="cycle-sports"
                        value={program.sport}
                        required
                        maxLength={200}
                        onChange={(e) => changeSport(e.target.value)}
                      />
                      <datalist id="cycle-sports">
                        <option value="Kajak" />
                        <option value="Kenu" />
                        <option value="Evezés" />
                        <option value="Futás" />
                        <option value="Kerékpár" />
                        <option value="Úszás" />
                        <option value="Sífutás" />
                        <option value="Általános fittség" />
                      </datalist>
                      <Field
                        label="Kezdőnap"
                        name="start_date"
                        type="date"
                        value={program.start_date}
                        required
                        onChange={(e) => changeStart(e.target.value)}
                        hint={`A mai nap alapértelmezése a sportoló időzónájából származik: ${catalog.timezone_name}.`}
                      />
                      {program.mode === "olympic" && (
                        <Select
                          label="Célolimpia"
                          name="olympic_key"
                          value={program.olympic_key ?? ""}
                          required
                          onChange={(e) => {
                            const edition = catalog.olympics.find(
                              (o) => o.key === e.target.value,
                            );
                            setProgram({
                              ...program,
                              olympic_key: edition?.key ?? null,
                              end_date: edition?.end_date ?? "",
                            });
                            setBlockEnd(edition?.end_date ?? "");
                          }}
                        >
                          <option value="">Válassz elérhető játékokat</option>
                          {catalog.olympics
                            .filter((o) => o.end_date >= program.start_date)
                            .map((o) => (
                              <option key={o.key} value={o.key}>
                                {o.kind === "summer" ? "Nyári" : "Téli"} ·{" "}
                                {o.title} · {o.start_date} – {o.end_date}
                              </option>
                            ))}
                        </Select>
                      )}
                      <Field
                        label={
                          program.mode === "recreation"
                            ? "Az első makrociklus vége"
                            : program.mode === "race"
                              ? "Célverseny napja vagy időablakának vége"
                              : program.mode === "olympic"
                                ? "Olimpiai időkeret vége"
                                : "Szezon vége"
                        }
                        name="end_date"
                        type="date"
                        value={blockEnd}
                        required
                        readOnly={program.mode === "olympic"}
                        onChange={(e) => changeEnd(e.target.value)}
                      />
                    </div>
                    {program.continued_from && (
                      <p className="text-sm text-teal-200">
                        Egy meglévő rekreációs program következő makrociklusát
                        készíted. A korábbi célokat átvettük; most
                        felülvizsgálhatod őket.
                      </p>
                    )}
                    {program.mode === "race" && (
                      <p className="text-sm leading-6 text-zinc-300">
                        Az aktuális teljes felkészülés időkerete 28 nap–12
                        hónap. Ez tervezési szabály; a cél elérhetőségét a
                        kiinduló állapot és a feladat alapján kell megítélni. A
                        távolabbi versenyt a cél leírásában is megőrizheted.
                      </p>
                    )}
                    {program.mode === "recreation" && (
                      <p className="text-sm leading-6 text-zinc-300">
                        A program folyamatos. Kezdő javaslatként 12 hetes
                        makrociklust adunk, amelynek végén újra áttekintheted a
                        céljaidat. A testsúlycsökkentést és a megtartást külön
                        célként kezeljük.
                      </p>
                    )}
                    <div className="space-y-4">
                      <p className="font-semibold">Célok</p>
                      {Object.entries(catalog.goals).map(([key, label]) => {
                        const goal = program.goals.find((g) => g.key === key);
                        return (
                          <div
                            key={key}
                            className="rounded-lg border border-zinc-700 p-4"
                          >
                            <label className="flex items-center gap-3 text-sm">
                              <input
                                type="checkbox"
                                className="h-5 w-5 accent-teal-300"
                                checked={!!goal}
                                onChange={(e) =>
                                  setProgram({
                                    ...program,
                                    goals: e.target.checked
                                      ? [...program.goals, newGoal(key)]
                                      : program.goals.filter(
                                          (g) => g.key !== key,
                                        ),
                                  })
                                }
                              />
                              {label}
                            </label>
                            {goal && (
                              <GoalEditor
                                value={goal}
                                events={program.competitions}
                                onChange={(value) =>
                                  setProgram({
                                    ...program,
                                    goals: program.goals.map((g) =>
                                      g.key === key ? value : g,
                                    ),
                                  })
                                }
                              />
                            )}
                          </div>
                        );
                      })}
                    </div>
                    <p className="text-sm text-zinc-400">
                      Itt a felkészülés szándékát rögzítjük. A képességek pontos
                      szerepét és mérését a létrehozott ciklusoknál adhatod meg.
                    </p>
                    <button type="submit" className={buttonClass}>
                      Tovább a versenyekhez
                    </button>
                  </form>
                )}
                {step === 2 && (
                  <form
                    className="space-y-5"
                    onSubmit={(e) => {
                      e.preventDefault();
                      stepTwo();
                    }}
                  >
                    {program.mode === "olympic" && (
                      <Message>
                        Legalább az első megtervezett szezonhoz adj meg
                        főversenyt. A további szezonokat később is
                        kiegészítheted.
                      </Message>
                    )}
                    <CompetitionEditor
                      value={program.competitions}
                      sport={program.sport}
                      structured={!!program.planning_basis}
                      change={changeEvents}
                    />
                    <div className="flex flex-wrap gap-3">
                      <button
                        type="button"
                        className={secondaryClass}
                        onClick={() => setStep(1)}
                      >
                        Vissza az időkerethez
                      </button>
                      <button type="submit" className={buttonClass}>
                        Ciklusbontás készítése
                      </button>
                    </div>
                  </form>
                )}
                {step === 3 && (
                  <form
                    className="space-y-5"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void checkPreview();
                    }}
                  >
                    <StructureEditor
                      value={program}
                      change={setProgram}
                      invalid={report}
                    />
                    <div className="flex flex-wrap gap-3">
                      <button
                        type="button"
                        className={secondaryClass}
                        onClick={() => setStep(2)}
                      >
                        Vissza a versenyekhez
                      </button>
                      <button type="submit" className={buttonClass}>
                        Tovább az áttekintéshez és mentéshez
                      </button>
                    </div>
                  </form>
                )}
                {step === 4 && review && (
                  <div className="space-y-6">
                    <ProgramSummary value={program} labels={catalog.goals} />
                    <ContextSnapshot
                      value={review.view.athlete_context_snapshot}
                    />
                    <p className="text-sm text-zinc-400">
                      Időzóna: {review.view.timezone_name}
                    </p>
                    <Structure periods={review.view.periods} />
                    <p className="text-sm leading-6 text-zinc-300">
                      A mentés a bemutatott ciklusokat és a felkészülés
                      rögzített előzményét együtt hozza létre. Ezután
                      folytathatod a képességcélok mezociklusonkénti
                      felosztásával.
                    </p>
                    <div className="flex flex-wrap gap-3">
                      <button
                        type="button"
                        className={secondaryClass}
                        onClick={() => {
                          setReview(null);
                          setStep(3);
                        }}
                      >
                        Vissza a ciklusbontáshoz
                      </button>
                      <button
                        type="button"
                        className={buttonClass}
                        onClick={() =>
                          void perform({
                            schema_version: "cycle-pending-v0.1",
                            operation: "programs",
                            body: review.body,
                          })
                        }
                      >
                        Felkészülés és ciklusok létrehozása
                      </button>
                    </div>
                  </div>
                )}
              </fieldset>
            </Card>
          )}
          <Card title="Mentett felkészülések">
            {!history.length ? (
              <p className="text-sm text-zinc-400">
                Még nincs ezen a felületen létrehozott felkészülés.
              </p>
            ) : (
              <ul className="space-y-3">
                {history.map((r) => (
                  <li key={r.artifact.artifact_id}>
                    <button
                      type="button"
                      className={`${secondaryClass} w-full text-left`}
                      onClick={() => void choose(r.artifact.artifact_id)}
                    >
                      <span className="block font-medium">
                        {r.artifact.proposal.title}
                      </span>
                      <span className="mt-1 block text-xs text-zinc-400">
                        {modeLabels[r.artifact.proposal.mode]} ·{" "}
                        {r.artifact.proposal.start_date} –{" "}
                        {r.artifact.proposal.end_date ?? "folyamatos program"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {hasMore && (
              <button
                type="button"
                className={`${secondaryClass} mt-4`}
                disabled={paging}
                onClick={() => void more()}
              >
                {paging ? "Betöltés…" : "További felkészülések betöltése"}
              </button>
            )}
          </Card>
          {detail && (
            <Card title="A kiválasztott felkészülés">
              <div className="space-y-6">
                <ProgramSummary
                  value={{
                    ...detail.program.artifact.proposal,
                    competitions:
                      detail.competition_revisions.at(-1)?.artifact.proposal
                        .competitions ??
                      detail.program.artifact.proposal.competitions,
                  }}
                  labels={catalog.goals}
                />
                <p className="text-sm text-zinc-400">
                  Versenynaptár:{" "}
                  {detail.competition_revisions.length
                    ? `${detail.competition_revisions.length}. pontosított változat`
                    : "a létrehozáskor rögzített változat"}
                  . A pontosítás a ciklusok időhatárait külön áttervezés nélkül
                  megőrzi.
                </p>
                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    disabled={locked}
                    className={secondaryClass}
                    onClick={refine}
                  >
                    Versenyek és dátumok pontosítása
                  </button>
                  <button
                    type="button"
                    disabled={locked}
                    className={secondaryClass}
                    onClick={reviewBoundary}
                  >
                    Mezociklushatár felülvizsgálata
                  </button>
                  {detail.program.artifact.proposal.mode === "recreation" && (
                    <button
                      type="button"
                      disabled={locked}
                      className={buttonClass}
                      onClick={continueRecreation}
                    >
                      Következő rekreációs makrociklus tervezése
                    </button>
                  )}
                </div>
                {boundaryDraft && (
                  <fieldset disabled={locked}>
                    <BoundaryEditor
                      value={boundaryDraft}
                      change={setBoundaryDraft}
                      today={catalog.local_today}
                      periods={
                        detail.boundary_revisions.at(-1)?.artifact.periods ??
                        detail.program.artifact.periods
                      }
                      invalid={report}
                      submit={(proposal) =>
                        void perform({
                          schema_version: "cycle-pending-v0.1",
                          operation: "boundary-revisions",
                          body: JSON.stringify(proposal),
                        })
                      }
                    />
                  </fieldset>
                )}
                {!!detail.boundary_revisions.length && (
                  <details className="space-y-4">
                    <summary className="cursor-pointer text-sm text-teal-200">
                      Ciklushatárok felülvizsgálatának előzményei
                    </summary>
                    {detail.boundary_revisions.map((r) => (
                      <div
                        key={r.artifact.artifact_id}
                        className="space-y-2 pt-3 text-sm"
                      >
                        <p>
                          {r.artifact.proposal.revision}. változat ·{" "}
                          {r.artifact.proposal.reason} ·{" "}
                          {r.artifact.proposal.observations}
                        </p>
                        <p>{r.artifact.proposal.rationale}</p>
                        <p>
                          Új közös határ: {r.artifact.proposal.new_end_date}. Az
                          érintett terhelés, képességszerepek és mérési
                          időablakok külön felülvizsgálandók.
                        </p>
                      </div>
                    ))}
                  </details>
                )}
                {editing && (
                  <form
                    className="space-y-5 rounded-xl border border-zinc-600 p-4"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void perform({
                        schema_version: "cycle-pending-v0.1",
                        operation: "competition-revisions",
                        body: JSON.stringify(normalizeRevision(editing)),
                      });
                    }}
                  >
                    <fieldset disabled={locked} className="space-y-5">
                      <CompetitionEditor
                        value={editing.competitions}
                        sport={detail.program.artifact.proposal.sport}
                        structured={
                          !!detail.program.artifact.proposal.planning_basis
                        }
                        refining
                        change={(competitions) =>
                          setEditing({ ...editing, competitions })
                        }
                      />
                      <Area
                        label="A pontosítás indoklása"
                        name="revision.rationale"
                        value={editing.rationale}
                        required
                        maxLength={2000}
                        onChange={(e) =>
                          setEditing({ ...editing, rationale: e.target.value })
                        }
                      />
                      <button className={buttonClass} type="submit">
                        Versenypontosítás új változatának mentése
                      </button>
                    </fieldset>
                  </form>
                )}
                {!!detail.competition_revisions.length && (
                  <details className="space-y-4">
                    <summary className="cursor-pointer text-sm text-teal-200">
                      Korábbi versenyadatok és pontosítások
                    </summary>
                    <p className="pt-3 text-sm font-medium">
                      Létrehozáskor rögzített versenyek
                    </p>
                    <Competitions
                      value={detail.program.artifact.proposal.competitions}
                    />
                    {detail.competition_revisions.map((r) => (
                      <div
                        key={r.artifact.artifact_id}
                        className="space-y-3 pt-3"
                      >
                        <p className="text-sm">
                          {r.artifact.proposal.revision}. változat ·{" "}
                          {r.artifact.proposal.rationale}
                        </p>
                        <Competitions
                          value={r.artifact.proposal.competitions}
                        />
                      </div>
                    ))}
                  </details>
                )}
                <p className="text-sm text-zinc-400">
                  Ciklusbontás:{" "}
                  {detail.boundary_revisions.length
                    ? `${detail.boundary_revisions.length}. jóváhagyott határváltozat`
                    : "a létrehozáskor rögzített tervezett időkeretek"}
                  .
                </p>
                <Structure
                  periods={
                    detail.boundary_revisions.at(-1)?.artifact.periods ??
                    detail.program.artifact.periods
                  }
                  saved
                  cycleId={detail.program.artifact.artifact_id}
                />
                {!!detail.boundary_revisions.length && (
                  <details>
                    <summary className="cursor-pointer text-sm text-teal-200">
                      Eredeti ciklusbontás
                    </summary>
                    <Structure periods={detail.program.artifact.periods} />
                  </details>
                )}
                <ContextSnapshot
                  value={detail.program.artifact.athlete_context_snapshot}
                />
                <Provenance value={detail.program.artifact} />
              </div>
            </Card>
          )}
          <p className="text-sm text-zinc-400">
            <Link
              href="/planning-goals"
              className="text-teal-200 underline underline-offset-4"
            >
              Célok és mérések megnyitása
            </Link>
          </p>
        </>
      )}
    </div>
  );
}
