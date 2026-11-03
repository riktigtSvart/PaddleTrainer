"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { canonical, addDays } from "@/lib/planning-cycles/contracts";
import { loadConstraints } from "@/lib/calendar/constraint-client";
import type { ScheduleContext } from "@/lib/calendar/constraints";
import { LOCAL_REFRESH_EVENT } from "@/lib/data-connections/preferences";
import {
  loadOptions,
  OptionsHTTPError,
  sendOptions,
} from "@/lib/training-options/client";
import {
  OPTIONS_UPDATED,
  PENDING_KEY,
  readPending,
  readOptionsData,
} from "@/lib/training-options/contracts";
import type {
  OptionsContext,
  OptionsData,
  OptionsPending,
} from "@/lib/training-options/contracts";
import {
  buttonClass,
  secondaryClass,
} from "@/components/planning-goals/fields";
import LocationEditor from "./location-editor";
import ScheduleEditor from "./schedule-editor";
import CurrentWeek from "./current-week";

export default function OptionsWorkspace({
  mode = "locations",
  onContinue,
}: {
  mode?: "locations" | "schedule" | "week";
  onContinue?: () => void;
}) {
  const [context, setContext] = useState<OptionsContext | null>(null),
    [schedule, setSchedule] = useState<ScheduleContext | null>(null),
    [first, setFirst] = useState<string | null>(null),
    [reload, setReload] = useState(0),
    [failure, setFailure] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [pending, setPending] = useState<OptionsPending | null>(null),
    [blocked, setBlocked] = useState(false),
    [ready, setReady] = useState(false),
    [rejected, setRejected] = useState(false);
  const writing = useRef(false);
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try {
        const raw = sessionStorage.getItem(PENDING_KEY);
        if (raw) setPending(readPending(raw));
      } catch {
        setBlocked(true);
        setFailure(
          "A korábbi függő mentés nem olvasható. Ellenőrizd a mentett állapotot, mielőtt új kérést indítasz.",
        );
      }
      setReady(true);
    });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void loadOptions(
      first ? { start: first, end: addDays(first, 6) } : undefined,
      controller.signal,
    )
      .then(async (c) => {
        const constraints =
          mode === "week"
            ? await loadConstraints(
                { start: c.start_date, end: c.end_date },
                controller.signal,
              )
            : null;
        if (controller.signal.aborted) return;
        if (constraints && constraints.athlete_id !== c.athlete_id)
          throw Error("Az órarend és a felmérés tulajdonosa eltér.");
        setContext(c);
        setSchedule(constraints);
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setFailure(
            e instanceof Error
              ? e.message
              : "Az edzési lehetőségek nem tölthetők be.",
          );
      });
    return () => controller.abort();
  }, [first, reload, mode]);
  const locked = busy || !!pending || blocked || !ready || !context;
  async function perform(value: OptionsPending): Promise<boolean> {
    if (
      writing.current ||
      !context ||
      value.owner !== context.athlete_id ||
      blocked
    )
      return false;
    writing.current = true;
    setBusy(true);
    setFailure("");
    setRejected(false);
    try {
      const receipt = await sendOptions(value);
      if (receipt.artifact.athlete_id !== context.athlete_id)
        throw Error("Másik sportoló mentési válasza érkezett.");
      sessionStorage.removeItem(PENDING_KEY);
      setPending(null);
      setMessage(
        "A módosítások mentve. A helyszínek és az órarend a következő tervezésben rendelkezésre állnak.",
      );
      try {
        const c = await loadOptions({
          start: context.start_date,
          end: context.end_date,
        });
        const nextSchedule =
          mode === "week"
            ? await loadConstraints({ start: c.start_date, end: c.end_date })
            : null;
        if (
          c.athlete_id !== context.athlete_id ||
          (nextSchedule && nextSchedule.athlete_id !== context.athlete_id)
        )
          throw Error("A frissítés másik sportolóhoz tartozik.");
        setContext(c);
        setSchedule(nextSchedule);
      } catch {
        setContext(null);
        setFailure(
          "A mentés sikerült, de a friss állapotot még nem sikerült visszaolvasni. Olvasd újra a mentett állapotot.",
        );
      }
      window.dispatchEvent(new Event(OPTIONS_UPDATED));
      window.dispatchEvent(new Event(LOCAL_REFRESH_EVENT));
      return true;
    } catch (e) {
      setFailure(
        e instanceof Error ? e.message : "A mentés eredménye nem ismert.",
      );
      setRejected(
        e instanceof OptionsHTTPError && e.status >= 400 && e.status < 500,
      );
      return false;
    } finally {
      writing.current = false;
      setBusy(false);
    }
  }
  async function save(data: OptionsData) {
    if (writing.current || locked || !context) return false;
    try {
      readOptionsData(data);
      if (canonical(data) === canonical(context.data)) {
        setMessage("Nincs eltérés a mentett állapothoz képest.");
        return true;
      }
      const value: OptionsPending = {
        version: "training-options-pending-v0.1",
        owner: context.athlete_id,
        body: JSON.stringify({
          request_id: crypto.randomUUID(),
          previous_reference: context.reference,
          data,
        }),
      };
      sessionStorage.setItem(PENDING_KEY, JSON.stringify(value));
      setPending(value);
      return await perform(value);
    } catch (e) {
      setFailure(
        e instanceof Error ? e.message : "A mentés nem készíthető elő.",
      );
      return false;
    }
  }
  return (
    <div className="pt-options-workspace">
      {failure && (
        <div role="alert" className="pt-options-message">
          <p>{failure}</p>
          <button
            type="button"
            className={secondaryClass}
            disabled={busy}
            onClick={() => {
              setFailure("");
              setReload((n) => n + 1);
            }}
          >
            Mentett állapot újraolvasása
          </button>
        </div>
      )}
      {message && (
        <p role="status" className="pt-options-message">
          {message}
        </p>
      )}
      {pending && (
        <div className="pt-panel">
          <p>
            A mentési kérés eredményét még ellenőrizni kell. Ugyanaz a kérés
            újraküldve nem hoz létre másolatot.
          </p>
          {context && pending.owner !== context.athlete_id ? (
            <p role="alert">
              A függő kérés másik sportolóhoz tartozik; nem küldhető el ehhez a
              profilhoz.
            </p>
          ) : (
            <button
              type="button"
              className={buttonClass}
              disabled={busy || !context || blocked}
              onClick={() => void perform(pending)}
            >
              Ugyanazon mentés ellenőrzése
            </button>
          )}
          {rejected && (
            <button
              type="button"
              className={secondaryClass}
              disabled={busy}
              onClick={() => {
                sessionStorage.removeItem(PENDING_KEY);
                setPending(null);
                setRejected(false);
                setReload((n) => n + 1);
              }}
            >
              Elutasított kérés elvetése
            </button>
          )}
        </div>
      )}
      {!context ? (
        !failure && <p role="status">Edzési lehetőségek betöltése…</p>
      ) : (
        <>
          {context.saved && (
            <p className="pt-options-meta">
              Mentett állapot ·{" "}
              {new Intl.DateTimeFormat("hu-HU", {
                timeZone: context.timezone_name,
                dateStyle: "short",
                timeStyle: "short",
              }).format(new Date(context.saved.artifact.created_at))}
            </p>
          )}
          {mode === "locations" && (
            <LocationEditor data={context.data} disabled={locked} save={save} />
          )}
          {mode === "schedule" && (
            <ScheduleEditor
              key={context.reference?.content_hash ?? "new"}
              data={context.data}
              today={context.local_today}
              disabled={locked}
              save={save}
            />
          )}
          {mode === "week" && (
            <>
              <div className="pt-options-actions">
                <button
                  type="button"
                  className={secondaryClass}
                  disabled={locked || context.start_date <= context.local_today}
                  onClick={() => setFirst(addDays(context.start_date, -1))}
                >
                  ← Egy nappal korábbról
                </button>
                <span>
                  {context.start_date} – {context.end_date}
                </span>
                <button
                  type="button"
                  className={secondaryClass}
                  disabled={locked}
                  onClick={() => setFirst(context.local_today)}
                >
                  Mától 7 nap
                </button>
                <button
                  type="button"
                  className={secondaryClass}
                  disabled={locked}
                  onClick={() => setFirst(addDays(context.start_date, 1))}
                >
                  Egy nappal későbbről →
                </button>
              </div>
              <CurrentWeek
                key={`${context.reference?.content_hash ?? "new"}:${context.start_date}`}
                context={context}
                schedule={schedule}
                disabled={locked}
                save={save}
                onContinue={onContinue}
              />
            </>
          )}
          {mode !== "week" && (
            <div className="pt-options-actions">
              <Link
                className={secondaryClass}
                href={
                  mode === "locations"
                    ? "/training-options/schedule"
                    : "/training-planning#week"
                }
              >
                {mode === "locations"
                  ? "Tovább az általános órarendhez"
                  : "Tovább az aktuális hét áttekintéséhez"}
              </Link>
            </div>
          )}
        </>
      )}
    </div>
  );
}
