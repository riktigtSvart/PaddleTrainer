"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { getJSON, readPeriods } from "@/lib/planning-goals/client";
import { addDays, object, sha } from "@/lib/planning-cycles/contracts";
import {
  history,
  loadContext,
  previewCalendar,
  send,
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
const message = (e: unknown) =>
  e instanceof Error ? e.message : "A művelet nem sikerült.";
export default function AthleteWorkspace({
  initialTab = "profile",
}: { initialTab?: "profile" | "calendar" | "history" } = {}) {
  const [context, setContext] = useState<Context | null>(null),
    [profile, setProfile] = useState<Profile>(emptyProfile),
    [calendar, setCalendar] = useState<Calendar | null>(null),
    [periods, setPeriods] = useState<PeriodChoice[]>([]);
  const [tab, setTab] = useState<"profile" | "calendar" | "history">(
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
  const locked = busy || !!pending || blocked || !ready;
  function report(text: string) {
    setError(text);
    requestAnimationFrame(() => {
      status.current?.focus({ preventScroll: true });
      status.current?.scrollIntoView({ block: "nearest" });
    });
  }
  function install(c: Context, replace: boolean) {
    setContext(c);
    setFrozen(c.profile?.artifact.imported_observations ?? []);
    if (replace) {
      setProfile(
        (c.profile?.artifact.proposal.data as Profile) ?? emptyProfile(),
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
  async function run(queue: PendingQueue) {
    if (sending.current || !context) return;
    if (queue.athlete_id !== context.athlete_id) {
      report(
        "A függő kérés másik sportolóhoz tartozik; nem küldhető el a jelenlegi felhasználó adataihoz.",
      );
      return;
    }
    sending.current = true;
    stop.current = false;
    setBusy(true);
    setRejected(false);
    setError("");
    let remaining = queue;
    try {
      while (remaining.items.length) {
        setProgress(`${remaining.items.length} kérés van hátra.`);
        const saved = await send(remaining.items[0]);
        if (saved.artifact.athlete_id !== queue.athlete_id)
          throw new Error("A bizonylat másik sportolóhoz tartozik.");
        applyReceipt(saved);
        const next = { ...remaining, items: remaining.items.slice(1) };
        if (next.items.length)
          sessionStorage.setItem(PENDING_KEY, JSON.stringify(next));
        else sessionStorage.removeItem(PENDING_KEY);
        setPending(next.items.length ? next : null);
        remaining = next;
        if (stop.current) break;
      }
      const fresh = await loadContext();
      install(fresh, false);
      if (!remaining.items.length) {
        setSuccess(
          queue.items[0].operation === "polar-imports"
            ? "Az órás lekérések befejeződtek. A nyers adatok megmaradtak; a profilba külön választhatod ki a felismert megfigyeléseket."
            : "A sportolói adatok mentése igazolt.",
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
    } catch (e) {
      setRejected(
        e instanceof SetupHTTPError && e.status >= 400 && e.status < 500,
      );
      report(`${message(e)} A függő kérés azonos tartalommal újraküldhető.`);
    } finally {
      sending.current = false;
      setBusy(false);
      setProgress("");
    }
  }
  function applyReceipt(saved: Receipt) {
    const a = saved.artifact;
    if (a.kind === "profile") {
      setProfile(a.proposal.data as Profile);
      setFrozen(a.imported_observations ?? []);
      setFormKey(a.content_hash);
    } else if (a.kind === "availability") {
      setCalendar(a.proposal.data as Calendar);
      setReview(null);
    }
  }
  function stage(queue: PendingQueue) {
    if (locked) return;
    try {
      sessionStorage.setItem(PENDING_KEY, JSON.stringify(queue));
      if (sessionStorage.getItem(PENDING_KEY) !== JSON.stringify(queue))
        throw new Error("A böngésző nem őrizte meg a függő kérést.");
      setPending(queue);
      setSuccess("");
      void run(queue);
    } catch (e) {
      report(message(e));
    }
  }
  function saveProfile() {
    if (!context || locked) return;
    try {
      const body = JSON.stringify({
        request_id: crypto.randomUUID(),
        previous_reference: context.references.profile_reference,
        data: normalizeProfile(profile, context.local_today),
      });
      stage({
        schema_version: "athlete-queue-v0.1",
        athlete_id: context.athlete_id,
        items: [
          {
            schema_version: "athlete-pending-v0.1",
            operation: "profiles",
            body,
          },
        ],
      });
    } catch (e) {
      report(message(e));
    }
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
  return (
    <div className="space-y-6">
      <div ref={status} tabIndex={-1} className="space-y-3 outline-none">
        {error && <Message error>{error}</Message>}
        {success && <Message>{success}</Message>}
        {progress && <Message>{progress}</Message>}
      </div>
      {pending && (
        <Card title="Függő mentés / lekérés">
          <p className="mb-4 text-sm leading-6">
            {pending.items.length} kérés vár igazolásra. Az eredeti kérés és
            azonosító megmaradt. Új adatírás előtt ennek az eredményét kell
            rendezni.
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              className={buttonClass}
              disabled={
                busy || !context || pending.athlete_id !== context.athlete_id
              }
              onClick={() => void run(pending)}
            >
              Azonos kérések folytatása
            </button>
            {busy && (
              <button
                className={secondaryClass}
                onClick={() => {
                  stop.current = true;
                }}
              >
                Megállás az aktuális kérés után
              </button>
            )}
            {rejected && !busy && (
              <button
                className={secondaryClass}
                onClick={() => {
                  try {
                    sessionStorage.removeItem(PENDING_KEY);
                    setPending(null);
                    setRejected(false);
                    setError("");
                    setReload((n) => n + 1);
                  } catch (e) {
                    report(message(e));
                  }
                }}
              >
                Elutasított kérés és hátralévő lekérések elvetése
              </button>
            )}
          </div>
        </Card>
      )}
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
          {context.current_review && (
            <Card title="Jelenlegi tervezési keret">
              <p className="font-semibold">
                {gateLabels[context.current_review.global_entry_gate] ??
                  context.current_review.global_entry_gate}
              </p>
              <p className="mt-2 text-sm">
                Életkor: {context.current_review.age_years ?? "még nem ismert"}{" "}
                · értékelés napja: {context.current_review.evaluated_on}
              </p>
              {!!context.current_review.reasons.length && (
                <ul className="mt-3 list-disc pl-5 text-sm leading-6">
                  {context.current_review.reasons.map((r) => (
                    <li key={r}>{reasonLabels[r] ?? r}</li>
                  ))}
                </ul>
              )}
              <p className="mt-3 text-xs text-zinc-400">
                A megadott kereteket felhasználjuk a ciklusok áttekintéséhez. Az
                egyéni edzésterheléshez külön tervezési döntés szükséges.
              </p>
            </Card>
          )}
          <nav
            aria-label="Sportolói felmérés részei"
            className="flex flex-wrap gap-3"
          >
            {(
              [
                ["profile", "Sportolói alapok"],
                ["calendar", "Naponkénti edzéslehetőségek"],
                ["history", "Mérések és órás adatok"],
              ] as const
            ).map(([key, label]) => (
              <button
                type="button"
                key={key}
                className={tab === key ? buttonClass : secondaryClass}
                aria-pressed={tab === key}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </nav>
          {tab === "profile" && (
            <Card title="Sportolói alapok">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  saveProfile();
                }}
              >
                <fieldset disabled={locked} className="space-y-6">
                  <ProfileForm
                    key={formKey}
                    value={profile}
                    onChange={setProfile}
                    today={context.local_today}
                  />
                  <button className={buttonClass} type="submit">
                    Felmérés mentése
                  </button>
                </fieldset>
              </form>
            </Card>
          )}
          {tab === "calendar" && calendar && (
            <Card title="Naponkénti edzéslehetőségek">
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
                    Mentendő naptár: {calendar.start_date} – {calendar.end_date}
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
          )}
          {tab === "history" && (
            <Card title="Mérések és órás adatok">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  saveProfile();
                }}
              >
                <fieldset disabled={locked} className="space-y-6">
                  <HistoryForm
                    value={profile}
                    onChange={setProfile}
                    context={context}
                    candidates={candidates}
                    frozen={frozen}
                    onSearch={(a, b) => void search(a, b)}
                    onImport={importHistory}
                    busy={busy}
                    onError={report}
                  />
                  <button className={buttonClass} type="submit">
                    Felmérés és kiválasztott adatok mentése
                  </button>
                </fieldset>
              </form>
            </Card>
          )}
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
    </div>
  );
}
