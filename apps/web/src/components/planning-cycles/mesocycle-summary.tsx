import Link from "next/link";
import { capabilityLabels } from "@/lib/planning-goals/labels";
import {
  blockProposals,
  waveLabels,
} from "@/lib/planning-cycles/mesocycle-coordination";
import type { TrainingReview } from "@/lib/planning-cycles/training-plan";

export default function MesocycleSummary({
  review,
}: {
  review: TrainingReview;
}) {
  const context = review.result.mesocycle_coordination;
  if (!context) return null;
  if (context.mode === "short_review")
    return (
      <p className="pt-options-meta">
        Ez egy rövid dátumablak felülvizsgálata. A teljes felépítéshez válaszd a
        „Ciklusok összehangolása” gombot: az aktuális és a következő mentett
        mezociklusra készül javaslat.
      </p>
    );
  const periods = (review.inputs?.periods ?? [])
    .filter((p) => context.blocks.some((b) => b.mesocycle_id === p.id))
    .sort((a, b) => a.start_date.localeCompare(b.start_date));
  return (
    <section
      aria-label="A mezociklusok összehangolt felépítése"
      className="space-y-4"
    >
      <h3>Hogyan épül fel ez az időszak?</h3>
      {review.calibration_review && (
        <p className="pt-options-meta">
          Rögzített ciklusalap:{" "}
          {review.calibration_review.created_at.slice(0, 10)}. A könnyebb hetek
          rövidebb edzései önmagukban nem csökkentik újra a kiinduló keretet. A
          „Ciklusok összehangolása” gombbal új alap kérhető a friss adatokból.
        </p>
      )}
      <p className="pt-options-meta">
        A rávezető és építő szakaszokat könnyebb szakasz követi. A keretek a
        saját kezdőkereten belül változnak; a ciklushatáron át is közös a
        gördülő heti korlát. Az alábbi felső keretbe a már rögzített és
        megőrzött edzések is beleszámítanak.
      </p>
      {periods.map((period) => {
        const blocks = context.blocks.filter(
          (b) => b.mesocycle_id === period.id,
        );
        const roles = [
          ...new Set(
            (review.inputs?.days ?? [])
              .filter((d) => d.mesocycle_id === period.id)
              .flatMap((d) =>
                (d.capability_roles ?? [])
                  .filter((r) => r.role === "primary_development")
                  .map((r) => r.capability_key),
              ),
          ),
        ];
        const represented = new Set(
          review.result.proposals
            .filter((c) =>
              blocks.some(
                (b) => b.start_date <= c.date && c.date <= b.end_date,
              ),
            )
            .map((c) => c.capability_key),
        );
        const missing = roles.filter((key) => !represented.has(key));
        return (
          <article key={period.id} className="pt-plan-variant">
            <header>
              <h4>{period.title}</h4>
              <span className="pt-plan-badge">
                {context.recommended_mesocycle_ids[0] === period.id
                  ? "Aktuális szakasz"
                  : context.recommended_mesocycle_ids[1] === period.id
                    ? "Következő szakasz"
                    : "További kijelölt szakasz"}
              </span>
            </header>
            <p>
              {period.start_date} – {period.end_date}
            </p>
            <p>
              Mentett fő hangsúlyok:{" "}
              {roles.length
                ? roles.map((key) => capabilityLabels[key] ?? key).join(", ")
                : "még megadandók"}
              .
            </p>
            <div className="pt-options-table-scroll">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">
                  {period.title} heti felépítése
                </caption>
                <thead>
                  <tr>
                    <th className="p-2" scope="col">
                      Szakasz
                    </th>
                    <th className="p-2" scope="col">
                      Időszak
                    </th>
                    <th className="p-2" scope="col">
                      Felső keret
                    </th>
                    <th className="p-2" scope="col">
                      Javasolt edzések
                    </th>
                    <th className="p-2" scope="col">
                      Képviselt célok
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {blocks.map((block) => {
                    const totals = blockProposals(review, block);
                    return (
                      <tr key={block.key}>
                        <th className="p-2" scope="row">
                          {block.ordinal}. hét · {waveLabels[block.kind]}
                        </th>
                        <td className="p-2 whitespace-nowrap">
                          {block.start_date} – {block.end_date}
                        </td>
                        <td className="p-2">
                          {block.max_minutes} perc · legfeljebb{" "}
                          {block.max_sessions} alkalom
                        </td>
                        <td className="p-2">
                          {totals.count} edzés · {totals.minutes} perc
                        </td>
                        <td className="p-2">
                          {totals.capabilities
                            .map((key) => capabilityLabels[key] ?? key)
                            .join(", ") || "Nincs új javaslat"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {!!missing.length && (
              <p className="pt-options-meta">
                Külön megoldást igénylő fő célok:{" "}
                {missing.map((key) => capabilityLabels[key] ?? key).join(", ")}.
                Ezekhez ebben a szakaszban nem készült külön edzésjavaslat.
              </p>
            )}
          </article>
        );
      })}
      <p className="pt-options-meta">
        Az időkeret felső határ, nem kitöltendő kvóta. Az erőedzés súlya és
        ismétlésszáma ettől nem nő automatikusan. A{" "}
        <Link className="underline" href="/planning-goals">
          mentett képességhangsúlyok
        </Link>{" "}
        és a napi változatok továbbra is módosíthatók; naptári változtatás csak
        az elfogadáskor történik.
      </p>
    </section>
  );
}
