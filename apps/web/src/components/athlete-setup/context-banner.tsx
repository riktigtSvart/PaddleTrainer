"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { loadContext } from "@/lib/athlete-setup/client";
import { gateLabels, reasonLabels } from "@/lib/athlete-setup/contracts";
import type { Context } from "@/lib/athlete-setup/contracts";
import type { AthleteContext } from "@/lib/planning-cycles/contracts";
import { Message, secondaryClass } from "@/components/planning-goals/fields";
import { loadConstraints } from "@/lib/calendar/constraint-client";
import { setupSteps } from "@/lib/athlete-setup/journey";
import type { ScheduleContext } from "@/lib/calendar/constraints";
export default function AthleteContextBanner({
  onChange,
}: {
  onChange?: (value: AthleteContext | undefined) => void;
}) {
  const [context, setContext] = useState<Context | null>(null),
    [failure, setFailure] = useState(""),
    [reload, setReload] = useState(0);
  const [schedule, setSchedule] = useState<ScheduleContext | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    Promise.all([
      loadContext(abort.signal),
      loadConstraints(null, abort.signal),
    ])
      .then(([c, s]) => {
        if (!abort.signal.aborted) {
          if (s.athlete_id !== c.athlete_id)
            throw Error("A naptár és a felmérés tulajdonosa eltér.");
          setContext(c);
          setSchedule(s);
          setFailure("");
          onChange?.(c.references.profile_reference ? c.references : undefined);
        }
      })
      .catch((e) => {
        if (!abort.signal.aborted) {
          setFailure(
            e instanceof Error ? e.message : "A felmérés nem tölthető be.",
          );
          onChange?.(undefined);
        }
      });
    return () => abort.abort();
  }, [reload, onChange]);
  return (
    <div className="space-y-3 rounded-xl border border-zinc-700 p-4 text-sm leading-6">
      <p className="font-semibold">Sportolói felmérés és edzéslehetőségek</p>
      {failure ? (
        <Message error>{failure}</Message>
      ) : !context ? (
        <p>Felmérés betöltése…</p>
      ) : !context.profile ? (
        <p>
          A felkészülés megadása előtt rögzítsd a sportmúltat, a korlátozásokat
          és a gyakorlati keretet. A bizonytalan adatokat is külön jelölheted.
        </p>
      ) : (
        <>
          <p>
            {gateLabels[context.current_review?.global_entry_gate ?? ""] ??
              "A keretek felülvizsgálandók"}
          </p>
          {!!context.current_review?.reasons.length && (
            <ul className="list-disc pl-5">
              {context.current_review.reasons.map((r) => (
                <li key={r}>{reasonLabels[r] ?? r}</li>
              ))}
            </ul>
          )}
          <ol className="grid gap-3 sm:grid-cols-3">
            {setupSteps(context, schedule).map((step, i) => (
              <li
                key={step.key}
                className="rounded-lg border border-zinc-700 p-3"
              >
                <p className="text-xs text-teal-400">
                  {i + 1}. lépés ·{" "}
                  {step.state === "ready"
                    ? "Mentett adat"
                    : step.state === "optional"
                      ? "Pontosítható"
                      : "Még szükséges"}
                </p>
                <Link
                  className="font-medium underline"
                  href={`/athlete-setup#${step.key}`}
                >
                  {step.title}
                </Link>
                <p className="mt-2 text-xs leading-5 text-zinc-400">
                  {step.detail}
                </p>
              </li>
            ))}
          </ol>
        </>
      )}
      <div className="flex flex-wrap gap-3">
        <Link className={secondaryClass} href="/athlete-setup">
          {context?.profile
            ? "Felmérés és naptár szerkesztése"
            : "Sportolói felmérés kitöltése"}
        </Link>
        <button
          type="button"
          className={secondaryClass}
          onClick={() => setReload((n) => n + 1)}
        >
          Felmérés frissítése
        </button>
      </div>
    </div>
  );
}
