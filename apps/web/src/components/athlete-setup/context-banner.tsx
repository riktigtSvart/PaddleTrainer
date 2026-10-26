"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { loadContext } from "@/lib/athlete-setup/client";
import { gateLabels, reasonLabels } from "@/lib/athlete-setup/contracts";
import type { Context } from "@/lib/athlete-setup/contracts";
import type { AthleteContext } from "@/lib/planning-cycles/contracts";
import { Message, secondaryClass } from "@/components/planning-goals/fields";
export default function AthleteContextBanner({
  onChange,
}: {
  onChange?: (value: AthleteContext | undefined) => void;
}) {
  const [context, setContext] = useState<Context | null>(null),
    [failure, setFailure] = useState(""),
    [reload, setReload] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    loadContext(abort.signal)
      .then((c) => {
        if (!abort.signal.aborted) {
          setContext(c);
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
          <p>
            Naptár:{" "}
            {context.availability
              ? `${context.availability.artifact.proposal.data && "start_date" in context.availability.artifact.proposal.data ? context.availability.artifact.proposal.data.start_date : ""} – ${context.availability.artifact.proposal.data && "end_date" in context.availability.artifact.proposal.data ? context.availability.artifact.proposal.data.end_date : ""}`
              : "még nincs kitöltve"}
            . A heti átlag nem tölti ki a hiányzó napokat.
          </p>
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
