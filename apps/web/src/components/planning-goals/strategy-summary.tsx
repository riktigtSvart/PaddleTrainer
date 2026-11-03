"use client";
import type {
  GoalSuggestion,
  Suggestions,
} from "@/lib/planning-cycles/goal-suggestions";
import { capabilityLabels, roleLabels } from "@/lib/planning-goals/labels";
export function StrategySummary({
  suggestion,
  strategy,
}: {
  suggestion: GoalSuggestion;
  strategy: Suggestions;
}) {
  const context = strategy.strategy;
  if (!context) return null;
  return (
    <section
      className="mb-6 space-y-3 rounded-xl border border-teal-800 p-4"
      aria-label="Javasolt mezociklus-stratégia"
    >
      <h3 className="font-semibold">Javasolt mezociklus-stratégia</h3>
      <p className="text-sm text-zinc-300">
        Elméleti és edzésmintákra épülő kezdőterv. A személyes fejlődés–terhelés
        modell még nincs alkalmazva; a friss állapotjelzések külön
        felülvizsgálati réteget kapnak.
      </p>
      {context.profile_context.notes.map((n) => (
        <p key={n} className="text-sm">
          {n}
        </p>
      ))}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr>
              <th className="p-2">Mezociklus</th>
              <th className="p-2">Hangsúly és főverseny</th>
              <th className="p-2">Képességszerepek</th>
            </tr>
          </thead>
          <tbody>
            {suggestion.strategy_periods?.map((p) => (
              <tr
                key={p.mesocycle_period_id}
                className="border-t border-zinc-700"
              >
                <td className="p-2">
                  {p.title}
                  <br />
                  <span className="text-xs text-zinc-400">
                    {p.segments[0].start_date} – {p.segments.at(-1)?.end_date}
                  </span>
                </td>
                <td className="p-2">
                  <strong>{p.label}</strong>
                  {p.current_overlay && (
                    <p>Friss állapotjelzés: regenerációs felülvizsgálat.</p>
                  )}
                  <details>
                    <summary className="cursor-pointer">Időbeli bontás</summary>
                    {p.segments.map((s) => (
                      <p key={s.start_date} className="text-xs my-1">
                        {s.start_date} – {s.end_date}: {s.label}
                        {s.event_title ? ` · ${s.event_title}` : ""}
                        {s.event_precision === "window"
                          ? " · közelítő versenydátum"
                          : ""}
                      </p>
                    ))}
                  </details>
                </td>
                <td className="p-2">
                  {suggestion.rows.map((r) => {
                    const d = r.mesocycle_directives.find(
                      (v) => v.mesocycle_period_id === p.mesocycle_period_id,
                    );
                    return (
                      <p key={r.capability_key}>
                        {capabilityLabels[r.capability_key] ?? r.capability_key}
                        :{" "}
                        <span
                          className={
                            d?.role === "primary_development"
                              ? "text-teal-200 font-semibold"
                              : "text-zinc-300"
                          }
                        >
                          {d?.role ? roleLabels[d.role] : "Felülvizsgálandó"}
                        </span>
                      </p>
                    );
                  })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer">
          A stratégia alapja és bizonytalanságai
        </summary>
        <p className="my-2">
          A pontos időablakok és a legfeljebb két új elsődleges hangsúly
          termékszabályok, nem élettani állandók. Egy mezociklus több
          hangsúlyablakot is érinthet; a táblázat a napok szerinti fő hangsúlyt
          mutatja. A részletes szerkesztő alább érhető el.
        </p>
        {context.sources.map((s) => (
          <p className="my-2" key={s.key}>
            <a
              className="underline"
              href={s.url}
              target="_blank"
              rel="noreferrer"
            >
              {s.key}
            </a>
            : {s.use} {s.limit}
          </p>
        ))}
        <p>{context.personal_response_model.reason}</p>
      </details>
    </section>
  );
}
