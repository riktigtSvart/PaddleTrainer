"use client";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import Icon from "@/components/ui/icon";
import { LOCAL_REFRESH_EVENT } from "@/lib/data-connections/preferences";
import { UPDATED_EVENT } from "@/lib/data-connections/contracts";
import { CalendarHTTPError, loadFeed, saveGoal } from "@/lib/calendar/client";
import {
  addDays,
  calendarEntries,
  dayList,
  eventsFrom,
  familyLabels,
  formatDay,
  GOAL_PENDING_KEY,
  goalLabels,
  readGoalBody,
  requireValue,
  viewRange,
} from "@/lib/calendar/contracts";
import type {
  CalendarEvent,
  Family,
  Feed,
  GoalBody,
  GoalTag,
  Span,
} from "@/lib/calendar/contracts";
import TimeGrid, { eventLabel } from "./time-grid";
import PeriodGrid from "./period-grid";
import OverviewCalendar from "./overview-calendar";
import EventPreview from "./event-preview";
import { eventHref } from "@/lib/calendar/event-preview";
import StateSummary from "./state-summary";
import ConflictSummary from "./conflict-summary";
import MoveEditor from "./move-editor";
import type { MoveRequest } from "./move-editor";
import type { MoveUndoState } from "@/lib/calendar/moves";
import QuickEditor, { UndoControl } from "./quick-editor";
import type { EditRequest } from "./quick-editor";
import { loadConstraints } from "@/lib/calendar/constraint-client";
import { constraintEvents } from "@/lib/calendar/constraint-forms";
import { conflictKind } from "@/lib/calendar/constraints";
import type { ScheduleContext } from "@/lib/calendar/constraints";
import type { SlotChange } from "@/lib/calendar/slot-transform";

type Pending = { owner: string; body: string };
type Selection = { key: string; base: GoalTag | null };
const spans: Span[] = [1, 7, 28, 168],
  spanNames = ["1 nap", "1 hét", "4 hét", "Áttekintés"];
const message = (e: unknown) =>
  e instanceof Error ? e.message : "A művelet nem sikerült.";
export default function CalendarWorkspace() {
  const [constraints, setConstraints] = useState<ScheduleContext | null>(null),
    [constraintError, setConstraintError] = useState(""),
    [constraintLoading, setConstraintLoading] = useState(true),
    [editRequest, setEditRequest] = useState<EditRequest | null>(null),
    [editorLocked, setEditorLocked] = useState(true),
    [moveRequest, setMoveRequest] = useState<MoveRequest | null>(null),
    [moveLocked, setMoveLocked] = useState(true),
    [moveUndo, setMoveUndo] = useState<MoveUndoState | null>(null),
    [editorTools, setEditorTools] = useState<HTMLDivElement | null>(null);
  const [data, setData] = useState<Feed | null>(null),
    [view, setView] = useState<{ date: string | null; span: Span }>({
      date: null,
      span: 7,
    });
  const [reload, setReload] = useState(0),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [success, setSuccess] = useState("");
  const [selection, setSelection] = useState<Selection | null>(null),
    [draftGoal, setDraftGoal] = useState("");
  const [layers, setLayers] = useState({
      availability: true,
      commitments: true,
      training: true,
      preparation: true,
      state: false,
    }),
    [fullDay, setFullDay] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null),
    [ready, setReady] = useState(false),
    [storageBlocked, setStorageBlocked] = useState(false),
    [sending, setSending] = useState(false),
    [rejected, setRejected] = useState(false);
  const sendingRef = useRef(false),
    detailRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!selection) return;
    const dialog = detailRef.current;
    const previous = document.activeElement as HTMLElement | null;
    dialog?.showModal();
    return () => {
      dialog?.close();
      previous?.focus();
    };
  }, [selection]);
  const activeDate = view.date ?? data?.local_today ?? "";
  const range = useMemo(
    () => (view.date ? viewRange(view.date, view.span) : null),
    [view],
  );
  useEffect(() => {
    const abort = new AbortController();
    loadFeed(range, abort.signal)
      .then((feed) => {
        if (!abort.signal.aborted) {
          setData(feed);
          setError("");
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!abort.signal.aborted) {
          setError(message(e));
          setLoading(false);
        }
      });
    return () => abort.abort();
  }, [range, reload]);
  useEffect(() => {
    const abort = new AbortController();
    loadConstraints(range, abort.signal)
      .then((value) => {
        if (!abort.signal.aborted) {
          setConstraints(value);
          setConstraintError("");
          setConstraintLoading(false);
        }
      })
      .catch((e) => {
        if (!abort.signal.aborted) {
          setConstraintError(message(e));
          setConstraintLoading(false);
        }
      });
    return () => abort.abort();
  }, [range, reload]);
  useEffect(() => {
    function updated() {
      setLoading(true);
      setConstraintLoading(true);
      setReload((n) => n + 1);
    }
    window.addEventListener(UPDATED_EVENT, updated);
    window.addEventListener(LOCAL_REFRESH_EVENT, updated);
    return () => {
      window.removeEventListener(UPDATED_EVENT, updated);
      window.removeEventListener(LOCAL_REFRESH_EVENT, updated);
    };
  }, []);
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try {
        const saved = sessionStorage.getItem(GOAL_PENDING_KEY);
        if (saved) {
          const value = JSON.parse(saved);
          requireValue(
            value.schema_version === "calendar-goal-pending-v0.1" &&
              typeof value.owner === "string" &&
              typeof value.body === "string",
          );
          readGoalBody(JSON.parse(value.body));
          setPending({ owner: value.owner, body: value.body });
        }
      } catch {
        setStorageBlocked(true);
        setError(
          "A függő célmentés vagy a böngésző tárhelye nem olvasható. Az előző mentés eredményét ellenőrizni kell.",
        );
      }
      setReady(true);
    });
    return () => {
      active = false;
    };
  }, []);
  const constraintsMatch =
    !!data &&
    !!constraints &&
    !constraintError &&
    data.athlete_id === constraints.athlete_id &&
    data.timezone_name === constraints.timezone_name &&
    data.start_date === constraints.start_date &&
    data.end_date === constraints.end_date &&
    (data.availability.reference?.artifact_id ?? null) ===
      (constraints.availability?.artifact.artifact_id ?? null) &&
    (data.availability.reference?.content_hash ?? null) ===
      (constraints.availability?.artifact.content_hash ?? null);
  const allEvents = useMemo(() => {
    if (!data) return [];
    const source = eventsFrom(data);
    if (!constraints || !constraintsMatch) return source;
    return [
      ...source.map((event) => {
        if (event.kind !== "planned") return event;
        const impacts = constraints.conflicts.filter(
          (c) => c.plan_id === event.entityId && conflictKind(c) !== "unknown",
        );
        const conflict: CalendarEvent["conflict"] = impacts.some(
          (c) => c.severity === "fixed",
        )
          ? "fixed"
          : impacts.some((c) => c.severity === "flexible")
            ? "flexible"
            : impacts.length
              ? "review"
              : undefined;
        return { ...event, conflict };
      }),
      ...constraintEvents(constraints),
    ];
  }, [data, constraints, constraintsMatch]);
  const entries = useMemo(() => calendarEntries(allEvents), [allEvents]);
  const visibleEvents = entries.filter((e) =>
    e.kind === "availability"
      ? layers.availability
      : e.kind === "constraint"
        ? layers.commitments
        : layers.training,
  );
  const selected = allEvents.find((e) => e.key === selection?.key) ?? null;
  const staleGoal =
    selected &&
    selection &&
    (selected.goalTag?.artifact_id !== selection.base?.artifact_id ||
      selected.goalTag?.content_hash !== selection.base?.content_hash ||
      selected.goalTag?.primary_goal !== selection.base?.primary_goal);
  const locked = loading || sending || !!pending || !ready || storageBlocked;
  function refresh() {
    setLoading(true);
    setConstraintLoading(true);
    setReload((n) => n + 1);
  }
  function changeView(date: string, span: Span) {
    try {
      viewRange(date, span);
      setView({ date, span });
      setSelection(null);
      setLoading(true);
      setConstraintLoading(true);
      setError("");
    } catch (e) {
      setError(message(e));
    }
  }
  function shift(direction: number) {
    try {
      changeView(addDays(activeDate, direction * view.span), view.span);
    } catch (e) {
      setError(message(e));
    }
  }
  function open(event: CalendarEvent) {
    if (event.kind === "availability" || event.kind === "constraint") {
      editSlot(event.date, event);
      return;
    }
    const href = eventHref(event);
    if (href) window.location.assign(href);
  }
  function editGoal(event: CalendarEvent) {
    setSelection({ key: event.key, base: event.goalTag });
    setDraftGoal(event.goal ?? "");
  }
  function editSlot(
    date: string,
    event: CalendarEvent | null = null,
    change?: SlotChange,
  ) {
    if (
      !constraintsMatch ||
      constraintLoading ||
      loading ||
      editorLocked ||
      moveLocked
    )
      return;
    setEditRequest((old) => ({
      serial: (old?.serial ?? 0) + 1,
      date,
      event,
      change,
    }));
  }
  function movePlan(event: CalendarEvent, change?: SlotChange) {
    if (
      loading ||
      constraintLoading ||
      !constraintsMatch ||
      editorLocked ||
      moveLocked ||
      event.kind !== "planned"
    )
      return;
    setMoveRequest((old) => ({
      serial: (old?.serial ?? 0) + 1,
      planId: event.entityId,
      change,
      expectedSourceHash: change ? event.reschedule?.source_hash : undefined,
    }));
  }
  async function transmit(value: Pending) {
    if (!data || sendingRef.current || value.owner !== data.athlete_id) return;
    sendingRef.current = true;
    setSending(true);
    setError("");
    setSuccess("");
    setRejected(false);
    try {
      const artifact = await saveGoal(value.body, value.owner),
        body = readGoalBody(JSON.parse(value.body));
      sessionStorage.removeItem(GOAL_PENDING_KEY);
      setPending(null);
      setSelection((current) =>
        current?.key === `${body.entity_kind}:${body.entity_id}`
          ? {
              key: current.key,
              base: {
                artifact_id: String(artifact.artifact_id),
                content_hash: String(artifact.content_hash),
                primary_goal: body.primary_goal,
              },
            }
          : current,
      );
      setSuccess("Az edzés fő célja elmentve.");
      refresh();
    } catch (e) {
      setError(message(e));
      setRejected(
        e instanceof CalendarHTTPError &&
          [400, 404, 409, 422].includes(e.status),
      );
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }
  async function submitGoal(event: FormEvent) {
    event.preventDefault();
    if (
      !data ||
      !selected ||
      (selected.kind !== "planned" && selected.kind !== "session") ||
      locked ||
      sendingRef.current ||
      staleGoal
    )
      return;
    const body: GoalBody = {
      request_id: crypto.randomUUID(),
      entity_kind: selected.kind,
      entity_id: selected.entityId,
      previous_reference: selection?.base
        ? {
            artifact_id: selection.base.artifact_id,
            content_hash: selection.base.content_hash,
          }
        : null,
      primary_goal: draftGoal || null,
    };
    const value = { owner: data.athlete_id, body: JSON.stringify(body) };
    try {
      sessionStorage.setItem(
        GOAL_PENDING_KEY,
        JSON.stringify({
          schema_version: "calendar-goal-pending-v0.1",
          ...value,
        }),
      );
    } catch {
      setStorageBlocked(true);
      setError(
        "A böngésző nem tudta megőrizni a mentési kérést. A mentés nem indult el.",
      );
      return;
    }
    setPending(value);
    await transmit(value);
  }
  function discardRejected() {
    if (!rejected || sending) return;
    try {
      sessionStorage.removeItem(GOAL_PENDING_KEY);
      setPending(null);
      setRejected(false);
      setSelection(null);
      refresh();
    } catch {
      setError("A függő kérés nem törölhető a böngésző tárhelyéről.");
    }
  }
  const rangeMatches =
    data &&
    (!range ||
      (data.start_date === range.start && data.end_date === range.end));
  const days = data ? dayList(data.start_date, data.end_date) : [];
  return (
    <main className="pt-calendar">
      <h1 className="pt-sr-only">Napirend</h1>
      <div className="pt-calendar-toolbar">
        <div className="pt-date-controls">
          <button
            type="button"
            className="pt-button pt-icon-button"
            aria-label="Előző időszak"
            disabled={!activeDate || sending}
            onClick={() => shift(-1)}
          >
            <Icon name="left" />
          </button>
          <label>
            <span className="sr-only">Kiválasztott nap</span>
            <input
              type="date"
              value={activeDate}
              min="1900-01-01"
              max="2100-12-31"
              disabled={!data || sending}
              onChange={(e) => {
                if (e.target.value) changeView(e.target.value, view.span);
              }}
            />
          </label>
          <button
            type="button"
            className="pt-button pt-icon-button"
            aria-label="Következő időszak"
            disabled={!activeDate || sending}
            onClick={() => shift(1)}
          >
            <Icon name="right" />
          </button>
          <button
            type="button"
            className="pt-button"
            disabled={!data || sending}
            onClick={() => data && changeView(data.local_today, view.span)}
          >
            Ma
          </button>
        </div>
        <div className="pt-zoom">
          <div className="pt-zoom-labels">
            {spans.map((span, i) => (
              <button
                type="button"
                key={span}
                aria-pressed={view.span === span}
                disabled={!activeDate || sending}
                onClick={() => changeView(activeDate, span)}
              >
                {spanNames[i]}
              </button>
            ))}
          </div>
        </div>
        <div className="pt-calendar-edit-actions">
          <details className="pt-view-options">
            <summary>
              <Icon name="settings" />
              Nézet
            </summary>
            <div className="pt-layers">
              {(
                [
                  ["availability", "Edzéslehetőségek"],
                  ["commitments", "Elfoglaltságok"],
                  ["training", "Edzések"],
                  ["preparation", "Felkészülés"],
                  ["state", "Állapotadatok"],
                ] as const
              ).map(([key, label]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={layers[key]}
                    onChange={(e) =>
                      setLayers((x) => ({ ...x, [key]: e.target.checked }))
                    }
                  />
                  {label}
                </label>
              ))}
              {view.span <= 7 && (
                <label className="pt-hours-choice">
                  <input
                    type="checkbox"
                    checked={fullDay}
                    onChange={(e) => setFullDay(e.target.checked)}
                  />
                  Teljes 24 óra
                </label>
              )}
            </div>
          </details>
          <div ref={setEditorTools}>{!editorTools && <UndoControl />}</div>
          <button
            className="pt-button"
            type="button"
            disabled={
              editorLocked ||
              moveLocked ||
              !constraintsMatch ||
              constraintLoading ||
              loading ||
              !!constraints?.timezone_review_required
            }
            onClick={() => editSlot(activeDate)}
          >
            <Icon name="clock" />+ Idősáv
          </button>
        </div>
      </div>
      {error && (
        <div className="pt-message is-error" role="alert">
          {error}
        </div>
      )}
      {success && (
        <div className="pt-message" role="status">
          {success}
        </div>
      )}
      {constraintError && (
        <div className="pt-message is-error" role="alert">
          A napirendi korlátok nem tölthetők be: {constraintError} A Frissítés
          gombbal újrapróbálható.
        </div>
      )}
      {data &&
        constraints &&
        !constraintsMatch &&
        !constraintError &&
        !loading &&
        !constraintLoading && (
          <div className="pt-message is-error" role="alert">
            A naptár és az idősávok közben megváltoztak. A Frissítés gombbal
            olvasd újra az időszakot.
          </div>
        )}
      {constraints?.timezone_review_required && (
        <div className="pt-message is-error" role="alert">
          A tárolt idősávok időzónája eltér a profilétól. Az időpontok
          felülvizsgálandók.
        </div>
      )}
      <QuickEditor
        context={constraintsMatch ? constraints : null}
        request={editRequest}
        disabled={
          moveLocked || loading || constraintLoading || !constraintsMatch
        }
        onSaved={refresh}
        onLockedChange={setEditorLocked}
        toolbarTarget={editorTools}
        workoutUndo={
          moveUndo && moveUndo.owner === data?.athlete_id
            ? {
                ...moveUndo,
                disabled: moveUndo.disabled,
                run: () =>
                  setMoveRequest((old) => ({
                    serial: (old?.serial ?? 0) + 1,
                    planId: moveUndo.planId,
                    undo: true,
                  })),
              }
            : null
        }
      />
      <MoveEditor
        owner={data?.athlete_id ?? null}
        request={moveRequest}
        disabled={
          editorLocked || loading || constraintLoading || !constraintsMatch
        }
        onSaved={refresh}
        onLockedChange={setMoveLocked}
        onUndoChange={setMoveUndo}
      />
      {constraintsMatch && constraints && (
        <ConflictSummary
          conflicts={constraints.conflicts}
          estimates={constraints.duration_estimates}
          openPlan={(id) => {
            const event = allEvents.find(
              (e) => e.kind === "planned" && e.entityId === id,
            );
            if (event) open(event);
          }}
        />
      )}
      {pending && (
        <div className="pt-message" role="status">
          Függő célmentés. Az eredmény azonos kéréssel ellenőrizhető.
          {pending.owner !== data?.athlete_id ? (
            <p>Ez a kérés másik sportolói fiókhoz tartozik.</p>
          ) : (
            <button
              type="button"
              className="pt-button"
              disabled={sending || !data}
              onClick={() => transmit(pending)}
            >
              {sending ? "Ellenőrzés…" : "Ugyanaz a kérés újraküldése"}
            </button>
          )}
          {rejected && (
            <button
              type="button"
              className="pt-button"
              disabled={sending}
              onClick={discardRejected}
            >
              Elutasított kérés elvetése és újraolvasás
            </button>
          )}
        </div>
      )}
      {data && rangeMatches ? (
        <>
          {layers.state && activeDate && (
            <StateSummary date={activeDate} refresh={reload} />
          )}
          <div className="pt-calendar-layout">
            <div className="pt-calendar-main" aria-busy={loading}>
              <div className="pt-calendar-range">
                <span>
                  {view.span === 168 ? (
                    "Áttekintés"
                  ) : (
                    <>
                      {formatDay(data.start_date)}
                      {data.start_date !== data.end_date &&
                        " – " + formatDay(data.end_date)}
                    </>
                  )}{" "}
                  · {data.timezone_name}
                  {loading ? " · újraolvasás…" : ""}
                </span>
                {layers.preparation && (
                  <details className="pt-period-menu">
                    <summary>Felkészülés</summary>
                    <div className="pt-period-strip">
                      {data.periods
                        .filter((p) => p.period_type === "MESOCYCLE")
                        .map((p) => (
                          <Link key={p.id} href={`/training-periods/${p.id}`}>
                            {p.title}{" "}
                            <small>
                              · {formatDay(p.start_date)} –{" "}
                              {formatDay(p.end_date)} · iránymutató határok
                            </small>
                          </Link>
                        ))}
                      <Link href="/planning-cycles">
                        Felkészülés és versenyek →
                      </Link>
                    </div>
                  </details>
                )}
              </div>
              <EventPreview
                feed={data}
                events={view.span === 168 ? [] : visibleEvents}
                onEditGoal={editGoal}
                onMove={(event) => movePlan(event)}
                editDisabled={
                  locked ||
                  editorLocked ||
                  moveLocked ||
                  !constraintsMatch ||
                  constraintLoading
                }
              >
                {view.span === 168 ? (
                  <OverviewCalendar
                    key={`${data.athlete_id}:${data.start_date}:${data.retrieved_at}:${reload}`}
                    feed={data}
                    context={constraintsMatch ? constraints : null}
                    layers={layers}
                    selectDay={(date) => changeView(date, 1)}
                  />
                ) : view.span <= 7 ? (
                  <TimeGrid
                    feed={data}
                    events={visibleEvents}
                    days={days}
                    fullDay={fullDay}
                    open={open}
                    selectDay={(d) => changeView(d, 1)}
                    expandHours={() => setFullDay(true)}
                    opportunities={
                      constraintsMatch ? constraints?.opportunities : undefined
                    }
                    onTransform={(event, change) =>
                      event.kind === "planned"
                        ? movePlan(event, change)
                        : editSlot(event.date, event, change)
                    }
                    editDisabled={
                      editorLocked ||
                      moveLocked ||
                      loading ||
                      constraintLoading ||
                      !constraintsMatch ||
                      !!constraints?.timezone_review_required
                    }
                    addSlot={
                      constraintsMatch &&
                      !constraintLoading &&
                      !loading &&
                      !editorLocked &&
                      !moveLocked
                        ? (date) => editSlot(date)
                        : undefined
                    }
                  />
                ) : (
                  <PeriodGrid
                    feed={data}
                    events={visibleEvents}
                    days={days}
                    selected={activeDate}
                    overview={false}
                    open={open}
                    selectDay={(d) => changeView(d, 1)}
                    addSlot={
                      constraintsMatch &&
                      !constraintLoading &&
                      !loading &&
                      !editorLocked &&
                      !moveLocked
                        ? (date) => editSlot(date)
                        : undefined
                    }
                  />
                )}
              </EventPreview>
              <details className="pt-calendar-explanation">
                <summary>Jelmagyarázat és további lehetőségek</summary>{" "}
                <div
                  className="pt-goal-legend"
                  aria-label="Fő cél szerinti színek"
                >
                  {Object.entries(familyLabels).map(([family, label]) => (
                    <span key={family}>
                      <b className={`pt-goal-${family as Family}`} />
                      {label}
                    </span>
                  ))}
                </div>
                <div className="pt-status-legend">
                  <span>
                    <Icon name="calendar" />
                    Terv
                  </span>
                  <span>
                    <Icon name="check" />
                    Teljesített
                  </span>
                  <span>
                    <Icon name="calendar" />
                    <Icon name="check" />
                    Tervhez párosított
                  </span>
                  <span>
                    <Icon name="clock" />
                    Megadott edzéslehetőség
                  </span>
                  <span>
                    <Icon name="calendar" />
                    Elfoglaltság · folytonos: rögzített, szaggatott: rugalmas
                  </span>
                  <Link href="/athlete-setup?tab=calendar">
                    Teljes edzésablak-naptár →
                  </Link>
                </div>
                <div className="pt-future-lane">
                  <Icon name="cart" />
                  Táplálkozás · későbbi modul
                </div>
              </details>
              {!data.planned.length && !data.sessions.length && (
                <div className="pt-message" style={{ marginTop: 14 }}>
                  Ebben az időszakban nincs tárolt edzésterv vagy teljesített
                  edzés.{" "}
                  <Link href="/athlete-setup?tab=history">
                    Órás előzmények és kézi adatok
                  </Link>
                </div>
              )}
              <details className="pt-event-list">
                <summary>Események listában · {visibleEvents.length}</summary>
                <ul>
                  {visibleEvents.map((e) => (
                    <li key={e.key}>
                      <button
                        type="button"
                        data-calendar-event={e.key}
                        onClick={() => open(e)}
                      >
                        {formatDay(e.date)} ·{" "}
                        {eventLabel(e, data.timezone_name)}
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
              {constraintsMatch &&
                constraints &&
                constraints.data.exceptions.some(
                  (e) =>
                    e.replacement === null &&
                    e.date >= data.start_date &&
                    e.date <= data.end_date,
                ) && (
                  <details className="pt-event-list">
                    <summary>Kihagyott ismétlődő alkalmak</summary>
                    <ul>
                      {constraints.data.exceptions
                        .filter(
                          (e) =>
                            e.replacement === null &&
                            e.date >= data.start_date &&
                            e.date <= data.end_date,
                        )
                        .map((e) => {
                          const rule = constraints.data.rules.find(
                            (r) => r.id === e.rule_id,
                          )!;
                          const occurrence = {
                            key: `${e.rule_id}:${e.date}`,
                            rule_id: e.rule_id,
                            source_date: e.date,
                            repeat: rule.repeat,
                            overridden: true,
                            details: rule.details,
                            start_at: null,
                            end_at: null,
                            elapsed_minutes: null,
                            issue: null,
                          };
                          return (
                            <li key={occurrence.key}>
                              {formatDay(e.date)} · {rule.details.title}{" "}
                              <button
                                type="button"
                                className="pt-more"
                                disabled={loading || constraintLoading}
                                onClick={() =>
                                  editSlot(e.date, {
                                    key: "constraint:" + occurrence.key,
                                    entityId: e.rule_id,
                                    kind:
                                      rule.details.kind === "available"
                                        ? "availability"
                                        : "constraint",
                                    date: e.date,
                                    title: rule.details.title,
                                    sport: "UNKNOWN",
                                    start: null,
                                    end: null,
                                    duration: null,
                                    goal: null,
                                    goalTag: null,
                                    occurrence,
                                  })
                                }
                              >
                                Alkalom visszaállítása / szerkesztése
                              </button>
                            </li>
                          );
                        })}
                    </ul>
                  </details>
                )}
            </div>
            {selected && (
              <dialog
                ref={detailRef}
                className="pt-quick-dialog pt-goal-dialog"
                aria-labelledby="pt-goal-dialog-title"
                onCancel={() => setSelection(null)}
                onClick={(event) => {
                  if (event.target === event.currentTarget) setSelection(null);
                }}
              >
                <div className="pt-quick-header">
                  <h2 id="pt-goal-dialog-title">{selected.title} · fő cél</h2>
                  <button
                    type="button"
                    className="pt-button"
                    aria-label="Bezárás"
                    onClick={() => setSelection(null)}
                  >
                    Bezárás
                  </button>
                </div>
                {error && (
                  <p className="pt-message is-error" role="alert">
                    {error}
                  </p>
                )}
                {pending && (
                  <p className="pt-notice" role="status">
                    A cél mentése még folyamatban van vagy ellenőrzésre vár.
                    Bezárás után a naptárban folytatható.
                  </p>
                )}
                <form className="pt-goal-form" onSubmit={submitGoal}>
                  <label>
                    Edzés fő célja
                    <select
                      value={draftGoal}
                      disabled={locked}
                      onChange={(e) => setDraftGoal(e.target.value)}
                    >
                      <option value="">Nincs megadva</option>
                      {Object.entries(goalLabels).map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="pt-primary"
                    disabled={locked || !!staleGoal}
                    type="submit"
                  >
                    {sending ? "Mentés…" : "Fő cél mentése"}
                  </button>
                </form>
                {staleGoal && (
                  <div className="pt-message is-error">
                    Közben megváltozott a céljelölés.{" "}
                    <button
                      className="pt-button"
                      type="button"
                      onClick={() => editGoal(selected)}
                    >
                      Friss cél átvétele
                    </button>
                  </div>
                )}
              </dialog>
            )}
          </div>
        </>
      ) : (
        <div className="pt-message" role="status">
          {loading
            ? "Naptári adatok betöltése…"
            : "A kiválasztott időszak nem tölthető be. A Frissítés gombbal újrapróbálható."}
        </div>
      )}
    </main>
  );
}
