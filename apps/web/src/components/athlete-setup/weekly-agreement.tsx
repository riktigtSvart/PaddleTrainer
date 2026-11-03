"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { addDays } from "@/lib/planning-cycles/contracts";
import {
  loadConstraints,
  previewConstraints,
  sendEditor,
} from "@/lib/calendar/constraint-client";
import {
  defaultDetails,
  EDITOR_PENDING,
  readProposal,
  weekLabels,
} from "@/lib/calendar/constraints";
import type { Proposal, ScheduleContext } from "@/lib/calendar/constraints";
import {
  EDITOR_UNDO,
  makeUndo,
  readRecovery,
  withHistory,
} from "@/lib/calendar/editor-history";
import type { Recovery } from "@/lib/calendar/editor-history";
import {
  buttonClass,
  Field,
  secondaryClass,
} from "@/components/planning-goals/fields";
import { LOCAL_REFRESH_EVENT } from "@/lib/data-connections/preferences";

export function weeklyProposal(
  context: ScheduleContext,
  input: {
    start: string;
    end: string;
    weekdays: number[];
    from: string;
    to: string;
    minutes: number;
  },
): Proposal {
  return readProposal({
    request_id: crypto.randomUUID(),
    previous_reference: context.reference,
    data: {
      ...context.data,
      rules: [
        ...context.data.rules,
        {
          id: crypto.randomUUID(),
          start_date: input.start,
          end_date: input.end || null,
          repeat: "weekly",
          weekdays: [...input.weekdays].sort(),
          details: {
            ...defaultDetails("available"),
            title: "Általános heti edzéslehetőség",
            start_time: input.from,
            end_time: input.to,
            max_minutes: input.minutes,
          },
        },
      ],
    },
  });
}

export function generalAgreementProposal(
  context: ScheduleContext,
  id: string,
  today: string,
): Proposal {
  const original = context.data.rules.find((r) => r.id === id);
  if (
    !original ||
    original.repeat !== "weekly" ||
    original.details.kind !== "available"
  )
    throw Error("Az időmegállapodás időközben megváltozott.");
  let first = original.start_date > today ? original.start_date : today;
  while (
    !original.weekdays.includes(
      (new Date(first + "T12:00Z").getUTCDay() + 6) % 7,
    )
  )
    first = addDays(first, 1);
  if (original.end_date && first > original.end_date)
    throw Error("Ez az időmegállapodás már véget ért.");
  const newId = crypto.randomUUID();
  const next = {
    ...original,
    id: newId,
    start_date: first,
    details: {
      ...original.details,
      sport_scope:
        original.details.sport_scope === "unknown"
          ? ("any" as const)
          : original.details.sport_scope,
      effort_cap:
        original.details.effort_cap === "unknown"
          ? ("any" as const)
          : original.details.effort_cap,
    },
  };
  return readProposal({
    request_id: crypto.randomUUID(),
    previous_reference: context.reference,
    data: {
      ...context.data,
      rules: [
        ...context.data.rules.filter((r) => r.id !== id),
        ...(first > original.start_date
          ? [{ ...original, end_date: addDays(first, -1) }]
          : []),
        next,
      ],
      exceptions: context.data.exceptions.map((e) =>
        e.rule_id === id && e.date >= first ? { ...e, rule_id: newId } : e,
      ),
    },
  });
}

export default function WeeklyAgreement({
  owner,
  today,
  onSaved,
}: {
  owner: string;
  today: string;
  onSaved: (context: ScheduleContext) => void;
}) {
  const [context, setContext] = useState<ScheduleContext | null>(null),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const [start, setStart] = useState(today),
    [end, setEnd] = useState(""),
    [weekdays, setWeekdays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [from, setFrom] = useState("18:00"),
    [to, setTo] = useState("19:00"),
    [minutes, setMinutes] = useState(60);
  const [busy, setBusy] = useState(false),
    [pending, setPending] = useState<Recovery | null>(null),
    [blocked, setBlocked] = useState(false),
    [recoveryReady, setRecoveryReady] = useState(false);
  const [review, setReview] = useState<{
    proposal: Proposal;
    context: ScheduleContext;
    summary: string;
  } | null>(null);
  const [reload, setReload] = useState(0),
    writing = useRef(false),
    callback = useRef(onSaved);
  useEffect(() => {
    callback.current = onSaved;
  }, [onSaved]);
  useEffect(() => {
    const abort = new AbortController();
    loadConstraints({ start: today, end: addDays(today, 6) }, abort.signal)
      .then(async (c) => {
        if (abort.signal.aborted) return;
        if (c.athlete_id !== owner)
          throw Error("Az időmegállapodás másik sportolóhoz tartozik.");
        setContext(c);
        callback.current(c);
        const raw = localStorage.getItem(EDITOR_PENDING);
        if (raw) {
          const p = await readRecovery(raw);
          if (abort.signal.aborted) return;
          if (p.owner !== owner)
            throw Error("Másik sportoló függő naptármentése található.");
          setPending(p);
        }
        setRecoveryReady(true);
      })
      .catch((e) => {
        if (!abort.signal.aborted) {
          setError(
            e instanceof Error
              ? e.message
              : "Az időmegállapodás nem tölthető be.",
          );
          setBlocked(true);
        }
      });
    return () => abort.abort();
  }, [owner, today, reload]);
  async function inspect(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!context || pending || blocked || !recoveryReady || busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    setReview(null);
    try {
      const proposal = weeklyProposal(context, {
        start,
        end,
        weekdays,
        from,
        to,
        minutes,
      });
      const preview = await previewConstraints(
        proposal,
        owner,
        start,
        addDays(start, 6),
      );
      if (
        preview.timezone_review_required ||
        preview.occurrences.some((o) => o.issue)
      )
        throw Error(
          "Az időpontok vagy az időzóna pontosításra szorul. Ellenőrizd a Napirend részletes szerkesztőjében.",
        );
      setReview({
        proposal,
        context: preview,
        summary: `${weekdays.map((d) => weekLabels[d]).join(", ")} · ${from}–${to} · legfeljebb ${minutes} edzésperc · ${start}-tól ${end || "módosításig"}.`,
      });
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Az időablak nem ellenőrizhető.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function generalize(id: string) {
    if (!context || busy || pending || blocked || !recoveryReady) return;
    setBusy(true);
    setError("");
    setMessage("");
    setReview(null);
    try {
      const rule = context.data.rules.find((r) => r.id === id);
      if (!rule) throw Error("Az időmegállapodás időközben megváltozott.");
      const proposal = generalAgreementProposal(context, id, today);
      const preview = await previewConstraints(
        proposal,
        owner,
        today,
        addDays(today, 6),
      );
      if (
        preview.timezone_review_required ||
        preview.occurrences.some((o) => o.issue)
      )
        throw Error("Az időpontok a Napirendben pontosítandók.");
      setReview({
        proposal,
        context: preview,
        summary: `${proposal.data.rules.at(-1)!.start_date}-tól · ${rule.weekdays.map((d) => weekLabels[d]).join(", ")} · ${rule.details.start_time}–${rule.details.end_time}: a korábban ismeretlen sportági vagy terhelési beállítás az általános megállapodást követi. A korábbi napok, a kifejezetten megadott korlátok és napi kivételek megmaradnak.`,
      });
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Az időmegállapodás nem ellenőrizhető.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function save(request: Recovery) {
    if (writing.current || blocked || !recoveryReady || request.owner !== owner)
      return;
    writing.current = true;
    setBusy(true);
    setError("");
    try {
      const existing = localStorage.getItem(EDITOR_PENDING);
      if (existing) {
        const saved = await readRecovery(existing);
        if (
          saved.body !== request.body ||
          saved.owner !== request.owner ||
          saved.operation !== request.operation
        )
          throw Error(
            "Egy másik napirendi mentés eredményét előbb ellenőrizni kell a Napirendben.",
          );
        request = saved;
      }
      const raw = JSON.stringify(request);
      localStorage.setItem(EDITOR_PENDING, raw);
      if (localStorage.getItem(EDITOR_PENDING) !== raw)
        throw Error("A böngésző nem őrizte meg a mentési kérést.");
      setPending(request);
      const receipt = await sendEditor(request);
      try {
        const undo = await makeUndo(request, receipt);
        if (undo) localStorage.setItem(EDITOR_UNDO, JSON.stringify(undo));
        else localStorage.removeItem(EDITOR_UNDO);
      } catch {
        /* A verified save remains successful if optional undo storage is unavailable. */
      }
      localStorage.removeItem(EDITOR_PENDING);
      setPending(null);
      setReview(null);
      setMessage(
        "A heti időmegállapodás mentve. A megadott kezdéstől módosításig ismétlődik; a kivételeket a Napirendben adhatod meg.",
      );
      setReload((n) => n + 1);
      window.dispatchEvent(new Event(LOCAL_REFRESH_EVENT));
    } catch (e) {
      setError(
        (e instanceof Error
          ? e.message
          : "A mentés eredménye még nem ismert.") +
          " A pontosan azonos kérés eredménye újraküldéssel ellenőrizhető.",
      );
    } finally {
      writing.current = false;
      setBusy(false);
    }
  }
  const recurring =
    context?.data.rules.filter(
      (r) =>
        r.repeat === "weekly" &&
        r.details.kind === "available" &&
        (!r.end_date || r.end_date >= today),
    ) ?? [];
  return (
    <section
      className="space-y-4 rounded-xl border border-teal-500/40 p-5"
      aria-label="Szokásos heti edzéslehetőség"
    >
      <div>
        <h3 className="text-lg font-semibold">
          2. Beszéljük meg a szokásos hetedet
        </h3>
        <p className="mt-2 text-sm leading-6">
          Amíg mást nem jelzel, a megbeszélt szerint ráérsz. A heti időablak
          általános edzéslehetőség: sportágat és terhelési korlátot csak külön
          igény esetén kell megadnod. Az eszközöket a mentett felmérésből
          vesszük át.
        </p>
      </div>
      {!!recurring.length && (
        <div className="rounded-lg bg-teal-500/10 p-3">
          <p className="font-medium">
            {recurring.length} mentett heti időablak
          </p>
          <ul className="mt-2 space-y-3 text-sm">
            {recurring.map((r) => (
              <li key={r.id}>
                <p>
                  {r.weekdays.map((d) => weekLabels[d]).join(", ")} ·{" "}
                  {r.details.start_time}–{r.details.end_time} · legfeljebb{" "}
                  {r.details.max_minutes} perc · {r.start_date}-tól{" "}
                  {r.end_date ? `${r.end_date}-ig` : "módosításig"}
                </p>
                <p className="mt-1 text-zinc-400">
                  {r.details.sport_scope === "specified"
                    ? r.details.sports.join(", ")
                    : r.details.sport_scope === "any"
                      ? "Általános edzéslehetőség"
                      : "Sportági beállítás még nincs tisztázva"}
                  {r.details.effort_cap === "unknown"
                    ? " · Terhelési beállítás még nincs tisztázva"
                    : r.details.effort_cap === "any"
                      ? " · Külön idősávhoz kötött terhelési korlát nélkül"
                      : ` · ${r.details.effort_cap === "easy" ? "Csak könnyű" : "Legfeljebb közepes"} terhelés`}
                </p>
                {(r.details.sport_scope === "unknown" ||
                  r.details.effort_cap === "unknown") && (
                  <button
                    type="button"
                    className={secondaryClass}
                    disabled={busy || !!pending || blocked || !recoveryReady}
                    onClick={() => void generalize(r.id)}
                  >
                    A meg nem határozott beállításoknál az általános
                    megállapodást használom
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      <Link className="inline-block text-sm underline" href="/">
        Napi kivétel, speciális sportág vagy meglévő megállapodás módosítása a
        Napirendben →
      </Link>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {blocked && (
        <button
          type="button"
          className={secondaryClass}
          onClick={() => {
            setBlocked(false);
            setError("");
            setReload((n) => n + 1);
          }}
        >
          Adatok újraolvasása
        </button>
      )}
      {pending && (
        <div className="space-y-2 rounded border border-amber-500/50 p-3">
          <p>Egy korábbi naptármentés eredménye még ellenőrzésre vár.</p>
          <button
            type="button"
            className={secondaryClass}
            disabled={busy || blocked}
            onClick={() => void save(pending)}
          >
            Azonos mentési kérés ellenőrzése
          </button>
          <p className="text-xs">
            Elutasított vagy időközben megváltozott kérés rendezéséhez nyisd meg
            a Napirendet.
          </p>
        </div>
      )}
      <details open={!recurring.length}>
        <summary className="cursor-pointer font-medium">
          {recurring.length
            ? "További heti időablak hozzáadása"
            : "Általános heti időablak megadása"}
        </summary>
        <form
          className="mt-4"
          onSubmit={inspect}
          onChange={() => setReview(null)}
        >
          <fieldset
            disabled={
              busy || pending !== null || blocked || !context || !recoveryReady
            }
            className="space-y-4"
          >
            <p className="text-sm text-zinc-400">
              Válaszd ki a napokat és a helyi időt. Ha például hétköznap
              esténként ráérsz, elég egyszer megadni. Ez rendelkezésre állás; a
              tervező választja ki a tényleges edzésnapokat.
            </p>
            <div
              className="flex flex-wrap gap-3"
              role="group"
              aria-label="Szokásos edzésnapok"
            >
              {[
                "Hétfő",
                "Kedd",
                "Szerda",
                "Csütörtök",
                "Péntek",
                "Szombat",
                "Vasárnap",
              ].map((day, i) => (
                <label
                  key={day}
                  className="flex gap-2 rounded border border-zinc-600 p-2"
                >
                  <input
                    type="checkbox"
                    checked={weekdays.includes(i)}
                    onChange={(e) =>
                      setWeekdays(
                        e.target.checked
                          ? [...weekdays, i]
                          : weekdays.filter((d) => d !== i),
                      )
                    }
                  />
                  {day}
                </label>
              ))}
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field
                label="Kezdés"
                type="time"
                required
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
              <Field
                label="Befejezés"
                type="time"
                required
                value={to}
                onChange={(e) => setTo(e.target.value)}
              />
              <Field
                label="Legfeljebb hány perc edzés fér ide?"
                type="number"
                required
                min={1}
                max={1440}
                value={minutes || ""}
                onChange={(e) => setMinutes(Number(e.target.value))}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Ettől a naptól érvényes"
                type="date"
                required
                min={today}
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
              <Field
                label="Utolsó nap · üresen módosításig"
                type="date"
                min={start}
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
            </div>
            <button
              className={secondaryClass}
              type="submit"
              disabled={!weekdays.length}
            >
              Heti megállapodás áttekintése
            </button>
          </fieldset>
        </form>
      </details>
      {review && context && (
        <div className="space-y-3 rounded-lg border border-teal-400 p-4">
          <p className="font-semibold">Ezt mentjük</p>
          <p>{review.summary}</p>
          <p className="text-sm">
            A megadott elfoglaltságok és elérhetetlen napok továbbra is
            érvényesek. {review.context.conflicts.length} meglévő tervnél jelez
            az előnézet egyeztetendő időpontot.
          </p>
          <button
            className={buttonClass}
            type="button"
            disabled={busy || !!pending || blocked}
            onClick={() =>
              void save(
                withHistory(
                  {
                    version: "calendar-editor-pending-v0.1",
                    owner,
                    operation: "constraints",
                    body: JSON.stringify(review.proposal),
                  },
                  context,
                  false,
                ),
              )
            }
          >
            Heti időmegállapodás mentése
          </button>
        </div>
      )}
    </section>
  );
}
