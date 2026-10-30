"use client";
import { ExecutionConnection } from "./execution-connection";
import { useEffect, useState } from "react";
import { loadLearning, learningLabels } from "@/lib/session-analysis/learning";
import type { LearningContext } from "@/lib/session-analysis/learning";
export function LearningStatus({
  owner,
  session,
  revisionKey,
  automatic = false,
}: {
  owner: string;
  session: string;
  revisionKey: string;
  automatic?: boolean;
}) {
  const [data, setData] = useState<LearningContext | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    const abort = new AbortController();
    loadLearning(owner, session, false, abort.signal)
      .then(async (initial) => {
        const v =
          automatic &&
          !abort.signal.aborted &&
          initial.items.some((item) => item.state === "ready_to_freeze")
            ? await loadLearning(owner, session, true, abort.signal)
            : initial;
        if (!abort.signal.aborted) {
          setData(v);
          setError("");
        }
      })
      .catch((e) => {
        if (!abort.signal.aborted)
          setError(
            e instanceof Error ? e.message : "A kapcsolat nem ellenőrizhető.",
          );
      });
    return () => abort.abort();
  }, [owner, session, revisionKey, automatic]);
  async function refresh() {
    setBusy(true);
    setError("");
    try {
      setData(await loadLearning(owner, session, true));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Az ellenőrzés nem sikerült.");
    } finally {
      setBusy(false);
    }
  }
  const waiting = data?.items.some(
    (x) => x.state === "waiting_for_execution" || x.state === "ready_to_freeze",
  );
  return (
    <details className="pt-feedback-learning">
      <summary>
        Tanulási kapcsolat{error ? " · ellenőrzésre vár" : ""}
        {data?.items.length
          ? ` · ${waiting ? "előkészítés alatt" : "ellenőrizve"}`
          : ""}
      </summary>
      {!data && !error && <p role="status">Kapcsolat ellenőrzése…</p>}
      {data && !data.items.length && (
        <p className="pt-notice">
          Még nincs az elemzéshez kiválasztható mentett visszajelzés.
        </p>
      )}
      {data?.items.map((a) => (
        <div key={a.timing}>
          <strong>
            {a.timing === "IMMEDIATE" ? "Edzés utáni" : "Másnap reggeli"} ·{" "}
            {a.revision}. változat
          </strong>
          <p>{learningLabels[a.state]}</p>
          <p className="pt-notice">
            Megfigyelés: {new Date(a.observed_at).toLocaleString("hu-HU")}.
            Adatként elérhető:{" "}
            {new Date(a.available_at).toLocaleString("hu-HU")}.
          </p>
          {a.reporting_delay_seconds >= 3600 && (
            <p className="pt-notice">
              Utólagos kitöltés: kb.{" "}
              {Math.floor(a.reporting_delay_seconds / 3600)} órával később.
              Korábbi elemzésekben nem szerepelhetett.
            </p>
          )}
        </div>
      ))}
      {error && <p role="alert">{error}</p>}
      <ExecutionConnection
        owner={owner}
        session={session}
        needed={!!data?.items.some((x) => x.state === "waiting_for_execution")}
        onConnected={refresh}
      />
      <button
        type="button"
        className="pt-button"
        disabled={busy}
        onClick={() => void refresh()}
      >
        {busy ? "Ellenőrzés…" : "Tanulási kapcsolat frissítése"}
      </button>
      <p className="pt-notice">
        Csak a kiválasztott változat számít. Az önbevallás önmagában nem
        bizonyít edzéshatást, és nem módosítja automatikusan a tervedet.
      </p>
    </details>
  );
}
