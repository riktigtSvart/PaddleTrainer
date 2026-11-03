"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { addDays } from "@/lib/planning-cycles/contracts";
import type { Reference } from "@/lib/planning-cycles/contracts";
import {
  inputGapLabels,
  loadPlanningInputs,
} from "@/lib/planning-cycles/inputs";
import type { PlanningInputs } from "@/lib/planning-cycles/inputs";
import { capabilityLabels } from "@/lib/planning-goals/labels";
import { secondaryClass } from "@/components/planning-goals/fields";
export function PlanningInputPanel({
  owner,
  reference,
  zone,
  today,
  initialDate = today,
}: {
  owner: string;
  reference: Reference;
  zone: string;
  today: string;
  initialDate?: string;
}) {
  const [first, setFirst] = useState(initialDate),
    [last, setLast] = useState(addDays(initialDate, 6)),
    [value, setValue] = useState<PlanningInputs | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  function change(set: (v: string) => void, next: string) {
    controller.current?.abort();
    setBusy(false);
    setValue(null);
    setError("");
    set(next);
  }
  async function inspect() {
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    setBusy(true);
    setError("");
    setValue(null);
    try {
      const result = await loadPlanningInputs(
        { owner, reference, zone, first, last },
        c.signal,
      );
      if (!c.signal.aborted) setValue(result);
    } catch (e) {
      if (!c.signal.aborted)
        setError(
          e instanceof Error ? e.message : "A tervezési adatok nem olvashatók.",
        );
    } finally {
      if (!c.signal.aborted) setBusy(false);
    }
  }
  return (
    <details className="rounded-xl border border-zinc-700 p-4 text-sm">
      <summary className="cursor-pointer font-medium">
        Edzéstervezés · bemeneti adatok
      </summary>
      <p className="my-3 text-zinc-400">
        A kiválasztott felkészülés céljai, napi lehetőségei és ismert sportolói
        adatai egy helyen. Ez az előkészítés még nem készít edzéstervet.
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
            onChange={(e) => change(setFirst, e.target.value)}
          />
        </label>
        <label>
          Utolsó nap
          <input
            className="block rounded border border-zinc-600 bg-transparent p-2"
            type="date"
            min={first}
            max={first ? addDays(first, 27) : undefined}
            required
            value={last}
            onChange={(e) => change(setLast, e.target.value)}
          />
        </label>
        <button className={secondaryClass} disabled={busy}>
          {busy ? "Összeállítás…" : "Tervezési alap összeállítása"}
        </button>
      </form>
      {error && (
        <p className="mt-3" role="alert">
          {error}
        </p>
      )}
      {value && (
        <div className="mt-4 space-y-3">
          <p className="text-xs text-zinc-400">
            <time dateTime={value.captured_at}>
              Lekérdezve:{" "}
              {new Intl.DateTimeFormat("hu-HU", {
                timeZone: zone,
                dateStyle: "short",
                timeStyle: "short",
              }).format(new Date(value.captured_at))}
            </time>
          </p>
          <p>
            Beolvasva: {value.recent_sessions.length} közelmúltbeli teljesítés ·{" "}
            {value.recovery_records.length} napi állapot ·{" "}
            {value.feedback.length} visszajelzés.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr>
                  <th className="p-2">Nap</th>
                  <th className="p-2">Időlehetőség</th>
                  <th className="p-2">Képességcélok</th>
                </tr>
              </thead>
              <tbody>
                {value.days.map((d) => (
                  <tr key={d.date} className="border-t border-zinc-700">
                    <td className="p-2">{d.date}</td>
                    <td className="p-2">
                      {
                        {
                          unknown: "Még nem ismert",
                          declared_unavailable: "Nincs megadott edzésidő",
                          opportunities: `${d.opportunities.length} megadott idősáv`,
                          blocked: "A megadott idősáv foglalt",
                        }[d.availability_state]
                      }
                    </td>
                    <td className="p-2">
                      {d.capability_roles.length
                        ? d.capability_roles
                            .map(
                              (r) =>
                                `${capabilityLabels[r.capability_key] ?? r.capability_key} · ${{ primary_development: "fejlesztés", secondary_development: "másodlagos fejlesztés", maintenance: "fenntartás", permitted_decline: "megengedett visszaesés" }[r.role] ?? r.role}`,
                            )
                            .join("; ")
                        : "Még nincs kijelölt képességszerep"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!!value.gaps.length && (
            <details>
              <summary className="cursor-pointer">
                Még tisztázandó adatok · {value.gaps.length}
              </summary>
              <ul className="mt-2 list-disc pl-5">
                {value.gaps.map((g) => (
                  <li key={g}>{inputGapLabels[g] ?? g}</li>
                ))}
              </ul>
            </details>
          )}
          <div className="flex flex-wrap gap-2">
            {value.periods
              .filter(
                (p) =>
                  p.period_type === "MACROCYCLE" &&
                  p.start_date <= last &&
                  p.end_date >= first,
              )
              .map((p) => (
                <Link
                  className={secondaryClass}
                  key={p.id}
                  href={`/planning-goals?cycle=${encodeURIComponent(reference.artifact_id)}&period=${p.id}`}
                >
                  Céljavaslat és szerepek · {p.title}
                </Link>
              ))}
          </div>
          <p className="text-xs text-zinc-400">
            Az edzéstervet az Edzésterv és újraértékelés részben lehet elkészíteni.
            A megadott napi és közös időkeretek a tervezés során is érvényesek.
          </p>
        </div>
      )}
    </details>
  );
}
