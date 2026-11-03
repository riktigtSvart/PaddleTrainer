"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { secondaryClass } from "@/components/planning-goals/fields";
import { addDays } from "@/lib/planning-cycles/contracts";
import type { Reference } from "@/lib/planning-cycles/contracts";
import { CycleHTTPError } from "@/lib/planning-cycles/client";
import { capabilityLabels } from "@/lib/planning-goals/labels";
import { LOCAL_REFRESH_EVENT } from "@/lib/data-connections/preferences";
import { UPDATED_EVENT } from "@/lib/data-connections/contracts";
import {
  loadTrainingStatus,
  readTrainingPending,
  reviewTraining,
  sendTraining,
  trainingReasons,
  chooseTraining,
} from "@/lib/planning-cycles/training-plan";
import PlanOutput from "./plan-output";
import { detailedEnd, reviewChanges } from "@/lib/planning-cycles/plan-view";
import type { PlanPeriod } from "@/lib/planning-cycles/plan-view";
import {
  DaysWithoutProposal,
  ProfileReviewNotice,
  PreparationChecklist,
  TrainingEvents,
} from "./training-plan-feedback";
import type {
  Acceptance,
  TrainingPending,
  TrainingReview,
} from "@/lib/planning-cycles/training-plan";

export function TrainingPlanPanel({
  owner,
  reference,
  zone,
  today,
  initialDate = today,
  periods,
}: {
  owner: string;
  reference: Reference;
  zone: string;
  today: string;
  initialDate?: string;
  periods?: PlanPeriod[];
}) {
  const [first, setFirst] = useState(initialDate),
    [last, setLast] = useState(
      periods?.length
        ? detailedEnd(periods, initialDate)
        : addDays(initialDate, 6),
    );
  const [review, setReview] = useState<TrainingReview | null>(null);
  const [accepted, setAccepted] = useState<Acceptance | null>(null);
  const [pending, setPending] = useState<TrainingPending | null>(null);
  const [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  const [checked, setChecked] = useState(false),
    [message, setMessage] = useState("");
  const [rejected, setRejected] = useState(false);
  const [recoveryBlocked, setRecoveryBlocked] = useState(false);
  const [choiceChanges, setChoiceChanges] = useState<
    { date: string; before: string; after: string }[]
  >([]);
  const [undoChoice, setUndoChoice] = useState<{
    date: string;
    key: string;
  } | null>(null);
  const controller = useRef<AbortController | null>(null),
    writing = useRef(false);
  const editingRange = useRef(false),
    readingReview = useRef(false),
    shownReview = useRef("");
  const expected = useRef({ owner, reference, zone });
  const storageKey = `paddletrainer.training-plan.pending.v1:${owner}:${reference.artifact_id}`;
  const report = (e: unknown) => {
    if (
      e instanceof CycleHTTPError &&
      [
        "TRAINING_PLAN_REVIEW_CHANGED",
        "TRAINING_PLAN_OUTCOME_CHANGED",
      ].includes(e.code)
    )
      setFailure(
        "Az edzések vagy a bemeneti adatok időközben megváltoztak. Készíts friss javaslatot és nézd át újra.",
      );
    else
      setFailure(
        e instanceof Error ? e.message : "A tervadatok nem érhetők el.",
      );
  };
  const read = useCallback(async (signal?: AbortSignal) => {
    const data = await loadTrainingStatus(expected.current, signal);
    if (!signal?.aborted && !writing.current) {
      setAccepted(data.acceptance);
      if (
        !editingRange.current &&
        !readingReview.current &&
        (data.review?.artifact_id ?? "") !== shownReview.current
      ) {
        shownReview.current = data.review?.artifact_id ?? "";
        setReview(data.review);
        setChecked(false);
        if (data.review) {
          setFirst(data.review.start_date);
          setLast(data.review.end_date);
        }
      }
    }
  }, []);
  useEffect(() => {
    const c = new AbortController();
    queueMicrotask(() => {
      if (c.signal.aborted) return;
      try {
        const raw = sessionStorage.getItem(storageKey);
        if (raw)
          setPending(readTrainingPending(raw, owner, reference.artifact_id));
      } catch {
        setRecoveryBlocked(true);
        setFailure(
          "A függő mentés helyi adatai nem olvashatók. Új mentés előtt a tárolt kérést helyre kell állítani; automatikusan nem küldjük újra.",
        );
      }
    });
    void read(c.signal).catch((e) => {
      if (!c.signal.aborted) report(e);
    });
    return () => {
      c.abort();
      controller.current?.abort();
    };
  }, [owner, reference.artifact_id, storageKey, read]);
  useEffect(() => {
    if (!accepted || pending) return;
    const refresh = () => {
      if (writing.current || document.visibilityState === "hidden") return;
      void read().catch(report);
    };
    const interval = window.setInterval(refresh, 60000);
    window.addEventListener(UPDATED_EVENT, refresh);
    window.addEventListener(LOCAL_REFRESH_EVENT, refresh);
    window.addEventListener("focus", refresh);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener(UPDATED_EVENT, refresh);
      window.removeEventListener(LOCAL_REFRESH_EVENT, refresh);
      window.removeEventListener("focus", refresh);
    };
  }, [accepted, pending, read]);
  async function inspect() {
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    readingReview.current = true;
    setBusy(true);
    setFailure("");
    setMessage("");
    setChecked(false);
    setChoiceChanges([]);
    setUndoChoice(null);
    try {
      const value = await reviewTraining(
        expected.current,
        first,
        last,
        c.signal,
      );
      if (!c.signal.aborted) {
        setReview(value);
        shownReview.current = value.artifact_id;
        editingRange.current = false;
      }
    } catch (e) {
      if (!c.signal.aborted) report(e);
    } finally {
      if (!c.signal.aborted) {
        setBusy(false);
        readingReview.current = false;
      }
    }
  }
  async function selectChoice(date: string, key: string, undo = false) {
    if (
      !review ||
      busy ||
      pending ||
      writing.current ||
      readingReview.current ||
      recoveryBlocked
    )
      return;
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    readingReview.current = true;
    setBusy(true);
    setFailure("");
    setChecked(false);
    const before = review,
      previous = before.result.proposals.find(
        (candidate) => candidate.date === date,
      )?.candidate_key;
    try {
      const next = await chooseTraining(
        expected.current,
        before,
        date,
        key,
        c.signal,
      );
      if (!c.signal.aborted) {
        setReview(next);
        shownReview.current = next.artifact_id;
        setChoiceChanges(reviewChanges(before, next));
        setUndoChoice(!undo && previous ? { date, key: previous } : null);
        setMessage(
          "Az edzésváltozat és az érintett későbbi napok javaslata újraszámolva. Áttekintés után fogadd el a naptári változtatásokat.",
        );
      }
    } catch (e) {
      if (!c.signal.aborted) report(e);
    } finally {
      if (!c.signal.aborted) {
        readingReview.current = false;
        setBusy(false);
      }
    }
  }
  async function save(request: TrainingPending) {
    if (writing.current) return;
    writing.current = true;
    controller.current?.abort();
    setBusy(true);
    setFailure("");
    setMessage("");
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(request));
      setPending(request);
      setRejected(false);
      await sendTraining(request);
      sessionStorage.removeItem(storageKey);
      setPending(null);
      setChecked(false);
      setMessage(
        request.operation === "accept"
          ? "A tervváltoztatások mentve. A Napirendben láthatók."
          : "A kihagyás megerősítve.",
      );
      try {
        const currentDay = new Intl.DateTimeFormat("sv-SE", {
          timeZone: zone,
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
        }).format(new Date());
        const nextFirst = first > currentDay ? first : currentDay;
        const value = await reviewTraining(
          expected.current,
          nextFirst,
          last > nextFirst ? last : nextFirst,
        );
        setReview(value);
        setFirst(value.start_date);
        setLast(value.end_date);
        shownReview.current = value.artifact_id;
        writing.current = false;
        await read();
      } catch {
        setFailure(
          "A mentést a szerver igazolta; az új felülvizsgálat még nem tölthető be. Frissítsd az előnézetet.",
        );
      }
      window.dispatchEvent(new Event(LOCAL_REFRESH_EVENT));
    } catch (e) {
      setRejected(
        e instanceof CycleHTTPError && e.status >= 400 && e.status < 500,
      );
      report(e);
    } finally {
      writing.current = false;
      setBusy(false);
    }
  }
  function submit() {
    if (!review || !checked) return;
    void save({
      owner,
      program: reference.artifact_id,
      operation: "accept",
      body: JSON.stringify({
        request_id: crypto.randomUUID(),
        review_reference: {
          artifact_id: review.artifact_id,
          content_hash: review.content_hash,
        },
        acknowledge_reviewed_plan: true,
      }),
    });
  }
  function change(set: (v: string) => void, value: string) {
    controller.current?.abort();
    editingRange.current = true;
    readingReview.current = false;
    setBusy(false);
    setReview(null);
    setChecked(false);
    set(value);
  }
  const changes = review
    ? review.result.create.length + review.result.cancel.length
    : 0;
  const time = (value: string) =>
    new Intl.DateTimeFormat("hu-HU", {
      timeZone: zone,
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(value));
  const title = (id: string) =>
    review?.plan_snapshots.find((p) => p.workout.id === id)?.workout.title ??
    "Edzés";
  return (
    <section className="space-y-4 rounded-xl border border-teal-500/40 p-4 text-sm">
      <h3 className="font-semibold">Edzésterv és újraértékelés</h3>
      <p className="text-zinc-400">
        A mentett képességszerepekhez és az ismert időlehetőségekhez illesztett
        kezdőterv. A változtatásokat átnézés után lehet elfogadni.
      </p>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void inspect();
        }}
      >
        <label>
          Kezdőnap
          <input
            className="block rounded border border-zinc-600 bg-transparent p-2"
            type="date"
            min={today}
            required
            value={first}
            disabled={busy || !!pending}
            onChange={(e) => change(setFirst, e.target.value)}
          />
        </label>
        <label>
          Utolsó nap
          <input
            className="block rounded border border-zinc-600 bg-transparent p-2"
            type="date"
            min={first}
            max={
              periods?.length
                ? detailedEnd(periods, first || today)
                : addDays(first || today, 365)
            }
            required
            value={last}
            disabled={busy || !!pending}
            onChange={(e) => change(setLast, e.target.value)}
          />
        </label>
        <button className={secondaryClass} disabled={busy || !!pending}>
          {busy
            ? "Ellenőrzés…"
            : review
              ? "Újraértékelés"
              : "Tervjavaslat készítése"}
        </button>
        {!!periods?.length && (
          <button
            type="button"
            className={secondaryClass}
            disabled={busy || !!pending}
            onClick={() => {
              change(setFirst, initialDate);
              change(setLast, detailedEnd(periods, initialDate));
            }}
          >
            Aktuális és következő mezociklus
          </button>
        )}
      </form>
      {failure && (
        <div role="alert">
          <p>{failure}</p>
          <button
            type="button"
            className={secondaryClass}
            disabled={busy || !!pending}
            onClick={() => {
              setFailure("");
              void read().catch(report);
            }}
          >
            Legutóbbi felülvizsgálat újraolvasása
          </button>
        </div>
      )}
      {message && (
        <p role="status">
          {message}{" "}
          <Link className="underline" href="/">
            Napirend megnyitása
          </Link>
        </p>
      )}
      {pending && (
        <div className="space-y-2 rounded border border-amber-500/40 p-3">
          <p>
            Egy mentési kérés eredményét még ellenőrizni kell. Az ismétlés nem
            hoz létre másolatot.
          </p>
          <button
            className={secondaryClass}
            disabled={busy}
            onClick={() => void save(pending)}
          >
            Ugyanazon mentés ellenőrzése
          </button>
          {rejected && (
            <button
              className={secondaryClass}
              disabled={busy}
              onClick={() => {
                sessionStorage.removeItem(storageKey);
                setPending(null);
                setRejected(false);
                setReview(null);
                setChecked(false);
              }}
            >
              Elutasított kérés elvetése
            </button>
          )}
        </div>
      )}
      {accepted && (
        <p className="text-xs text-zinc-400">
          Az elfogadott időszak tervét a működő API percenként felülvizsgálja az
          új teljesítések, visszajelzések és lejárt edzések alapján. A javaslat
          elfogadásig nem módosítja a naptárt.
        </p>
      )}
      {review && (
        <div className="space-y-4">
          <PreparationChecklist review={review} />
          <p>
            Felülvizsgálat: {time(review.created_at)} ·{" "}
            {review.result.create.length} új edzés · {review.result.keep.length}{" "}
            megtartott edzés · {review.result.cancel.length} javasolt
            lecserélés.
          </p>
          {review.result.blockers.includes("PROFILE_REVIEW_REQUIRED") && (
            <ProfileReviewNotice entry={review.result.entry_review} />
          )}
          {review.result.blockers
            .filter((reason) => reason !== "PROFILE_REVIEW_REQUIRED")
            .map((reason) => (
              <p key={reason} role="status">
                {trainingReasons[reason] ?? reason}
              </p>
            ))}
          <PlanOutput
            review={review}
            disabled={busy || !!pending || recoveryBlocked}
            onChoose={(date, key) => void selectChoice(date, key)}
            changes={choiceChanges}
            onUndo={
              undoChoice
                ? () => void selectChoice(undoChoice.date, undoChoice.key, true)
                : undefined
            }
          />
          {!!review.result.cancel.length && (
            <div>
              <p>Elfogadáskor töröltnek jelöljük, az előzményét megőrizzük:</p>
              <ul className="list-disc pl-5">
                {review.result.cancel.map((id) => (
                  <li key={id}>{title(id)}</li>
                ))}
              </ul>
            </div>
          )}
          {!!review.result.events.length && (
            <TrainingEvents
              review={review}
              zone={zone}
              disabled={busy || !!pending || recoveryBlocked}
              onConfirmMissed={(event) =>
                void save({
                  owner,
                  program: reference.artifact_id,
                  operation: "missed",
                  body: JSON.stringify({
                    request_id: crypto.randomUUID(),
                    workout_id: event.workout_id,
                    expected_workout_hash: event.workout_hash,
                  }),
                })
              }
            />
          )}
          {!!review.result.days_without_proposal.length && (
            <DaysWithoutProposal days={review.result.days_without_proposal} />
          )}
          {!!review.result.uncovered_capabilities.length && (
            <p className="text-zinc-400">
              Még külön tervezést igénylő fejlesztési célok:{" "}
              {review.result.uncovered_capabilities
                .map((key) => capabilityLabels[key] ?? key)
                .join(", ")}
              . A mintaterv ezek teljesítését nem igazolja.
            </p>
          )}
          {changes > 0 && !review.result.blockers.length && !pending && (
            <div className="space-y-3 border-t border-zinc-700 pt-3">
              <label className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => setChecked(e.target.checked)}
                  disabled={busy}
                />
                Átnéztem a javasolt edzéseket és változtatásokat.
              </label>
              <button
                className={secondaryClass}
                disabled={!checked || busy || recoveryBlocked}
                onClick={submit}
              >
                Változtatások elfogadása
              </button>
            </div>
          )}
          {!changes && !review.result.blockers.length && (
            <p>A felülvizsgálat jelenleg nem javasol tervmódosítást.</p>
          )}
        </div>
      )}
    </section>
  );
}
