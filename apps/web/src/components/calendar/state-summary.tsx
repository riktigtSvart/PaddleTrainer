"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { history, loadContext } from "@/lib/athlete-setup/client";
import { aggregations, methods } from "@/lib/athlete-setup/contracts";
import { stateMetricLabels as wanted, stateRows } from "@/lib/calendar/state";
import type { StateRow } from "@/lib/calendar/state";
import {
  formatDay,
  formatDuration,
  formatNumber,
} from "@/lib/calendar/contracts";
export default function StateSummary({
  date,
  refresh,
}: {
  date: string;
  refresh: number;
}) {
  const [result, setResult] = useState<{
    date: string;
    rows: StateRow[];
    error: string;
  } | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    Promise.allSettled([
      history(date, date, abort.signal),
      loadContext(abort.signal),
    ])
      .then(([historical, context]) => {
        if (!abort.signal.aborted)
          setResult({
            date,
            rows: stateRows(
              historical.status === "fulfilled" ? historical.value : [],
              context.status === "fulfilled"
                ? (context.value.profile?.artifact ?? null)
                : null,
              date,
            ),
            error: [historical, context]
              .filter((result) => result.status === "rejected")
              .map((result) =>
                result.status === "rejected"
                  ? String(
                      result.reason instanceof Error
                        ? result.reason.message
                        : "Egy adatforrás nem olvasható.",
                    )
                  : "",
              )
              .join(" "),
          });
      })
      .catch((e) => {
        if (!abort.signal.aborted)
          setResult({
            date,
            rows: [],
            error:
              e instanceof Error
                ? e.message
                : "Az állapotadatok nem olvashatók.",
          });
      });
    return () => abort.abort();
  }, [date, refresh]);
  const current = result?.date === date ? result : null;
  return (
    <details className="pt-state-strip">
      <summary>
        Tárolt állapotadatok · {formatDay(date)}
        {current ? ` · ${current.rows.length} forrásadat` : " · betöltés…"}
      </summary>
      {current?.error && (
        <p className="pt-notice" role="status">
          {current.error}
        </p>
      )}
      {current ? (
        current.rows.length ? (
          <div className="pt-state-values">
            {current.rows.map((row) => (
              <div key={row.id}>
                <span>
                  {wanted[row.metric]}:{" "}
                  {row.metric === "sleep_duration_sec"
                    ? formatDuration(Number(row.value))
                    : formatNumber(
                        Number(row.value),
                        row.unit === "count" ? "" : row.unit,
                      )}
                </span>
                <small>
                  {row.provider} · {methods[row.method]} ·{" "}
                  {aggregations[row.aggregation]}
                  {row.replaced ? " · korábbi, kézzel helyesbített forrás" : ""}
                  {row.partial ? " · részleges minták" : ""}
                </small>
              </div>
            ))}
          </div>
        ) : !current.error ? (
          <p className="pt-notice">
            Ehhez a naphoz nincs tárolt adat ezekből a mutatókból.{" "}
            <Link href="/athlete-setup?tab=history">
              Előzmények és kézi adatok
            </Link>
          </p>
        ) : null
      ) : null}
      {current && current.rows.length > 1 && (
        <p className="pt-notice">Az eltérő források külön szerepelnek.</p>
      )}
    </details>
  );
}
