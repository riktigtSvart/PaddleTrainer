"use client";
import { useEffect, useRef, useState } from "react";
import { loadPlanningInputs } from "@/lib/planning-cycles/inputs";
import {
  checkedSuggestion,
  familyNames,
} from "@/lib/planning-cycles/goal-suggestions";
import type { GoalSuggestion } from "@/lib/planning-cycles/goal-suggestions";
import type { Reference } from "@/lib/planning-cycles/contracts";
import { macroProposal } from "@/lib/planning-goals/forms";
import { StrategySummary } from "./strategy-summary";
import { capabilityLabels, roleLabels } from "@/lib/planning-goals/labels";
import type {
  Catalog,
  MacroArtifact,
  Period,
  Receipt,
} from "@/lib/planning-goals/types";
import { Area, buttonClass, Card, Select } from "./fields";

type Props = {
  catalog: Catalog;
  period: Period;
  periods: Period[];
  base?: Receipt<MacroArtifact>;
  locked: boolean;
  submit: (proposal: unknown) => void;
  invalid: (message: string) => void;
  suggestedCapabilities?: string[];
  cycle?: { owner: string; reference: Reference; zone: string; today: string };
};
export default function MacroForm({
  catalog,
  period,
  periods,
  base,
  locked,
  submit,
  invalid,
  suggestedCapabilities = [],
  cycle,
}: Props) {
  const [selected, setSelected] = useState(
    () =>
      new Set(base?.artifact.proposal.goals.map((g) => g.capability_key) ?? []),
  );
  const children = periods.filter(
    (p) => p.parent_id === period.id && p.period_type === "MESOCYCLE",
  );
  const [suggestion, setSuggestion] = useState<GoalSuggestion | null>(null);
  const [strategy, setStrategy] = useState<
    import("@/lib/planning-cycles/goal-suggestions").Suggestions | null
  >(null);
  const [captureHash, setCaptureHash] = useState("");
  const [suggesting, setSuggesting] = useState(false);
  const [generation, setGeneration] = useState(0);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function suggest() {
    if (!cycle) return;
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    setSuggesting(true);
    try {
      const data = await loadPlanningInputs(
        {
          owner: cycle.owner,
          reference: cycle.reference,
          zone: cycle.zone,
          first: cycle.today,
          last: cycle.today,
        },
        c.signal,
      );
      const draft = checkedSuggestion(
        data,
        period,
        children,
        catalog.capabilities,
        base
          ? {
              reference: base.artifact,
              revision: base.artifact.proposal.revision,
            }
          : undefined,
      );
      if (!c.signal.aborted) {
        setCaptureHash(data.content_hash);
        setStrategy(data.goal_suggestions ?? null);
        setSuggestion(draft);
        setSelected(new Set(draft.rows.map((r) => r.capability_key)));
        setGeneration((n) => n + 1);
      }
    } catch (e) {
      if (!c.signal.aborted)
        invalid(
          e instanceof Error ? e.message : "A céljavaslat nem olvasható.",
        );
    } finally {
      if (!c.signal.aborted) setSuggesting(false);
    }
  }
  return (
    <Card
      title={
        base
          ? `Új makrociklus-verzió: ${base.artifact.proposal.revision + 1}.`
          : "Makrocikluscélok rögzítése · 1. verzió"
      }
    >
      <p className="mb-5 text-sm leading-6 text-zinc-300">
        Válaszd ki a képességeket és a szerepüket a teljes makrociklusban, majd
        minden közvetlen mezociklusban. A kimaradó képesség nincs hozzárendelve;
        ez nem engedély a leépülésére.
      </p>
      {cycle && !suggestion && (
        <button
          type="button"
          className="mb-4 rounded border border-zinc-600 px-4 py-2"
          disabled={locked || suggesting}
          onClick={() => void suggest()}
        >
          {suggesting
            ? "Céljavaslat betöltése…"
            : "Céljavaslat a felkészülés adataiból"}
        </button>
      )}
      {suggestion && (
        <div className="mb-4 space-y-2 text-sm" role="status">
          <p>
            Kitöltött stratégiai kezdőterv. A rögzített szerepek megmaradtak; az
            új szerepeket az alkalmazás javasolja. Áttekintés után elfogadhatod
            vagy szerkesztheted őket. A mentésig nincs változás.
          </p>
          <p className="text-zinc-400">
            A hangsúlyok és a verseny előtti frissítési ablakok kiinduló
            javaslatok. A ciklushatárok és a versenydátumok változatlanok; napi
            edzést és dózist ez a lépés még nem ír elő.
          </p>
          {!!suggestion.unprofiled_event_keys.length && (
            <p>
              Hiányzó versenyprofil:{" "}
              {suggestion.unprofiled_event_keys
                .map((k) => strategy?.event_titles?.[k] ?? k)
                .join(", ")}
            </p>
          )}
          {!!suggestion.unmapped_goal_keys.length && (
            <p>
              Önálló képességre itt nem leképezett cél:{" "}
              {suggestion.unmapped_goal_keys
                .map(
                  (k) =>
                    ({
                      weight_loss: "Testsúlycsökkentés",
                      weight_maintenance: "Testsúly megtartása",
                      performance: "Versenyeredmény",
                      regular_activity: "Rendszeres mozgás",
                      mobility: "Mobilitás",
                    })[k] ?? k,
                )
                .join(", ")}
              . Ezek a felkészülés céljai között megmaradnak.
            </p>
          )}
          {!suggestion.rows.length && (
            <p>
              Nincs elegendő megadott képességcél. Válassz alább kézzel, vagy
              egészítsd ki a versenyprofilt.
            </p>
          )}
        </div>
      )}
      {suggestion && strategy?.strategy && (
        <StrategySummary suggestion={suggestion} strategy={strategy} />
      )}
      {!children.length ? (
        <p className="text-amber-200">
          Előbb hozz létre legalább egy közvetlen mezociklust ehhez a
          makrociklushoz.
        </p>
      ) : (
        <form
          key={generation}
          onSubmit={(event) => {
            event.preventDefault();
            try {
              if (
                suggestion &&
                new FormData(event.currentTarget).get("reviewed") !== "on"
              )
                throw Error(
                  "Előbb tekintsd át és jelöld jóvá a képességszerepeket.",
                );
              submit(
                macroProposal(
                  new FormData(event.currentTarget),
                  catalog,
                  period,
                  children,
                  base,
                ),
              );
            } catch (error) {
              invalid(
                error instanceof Error
                  ? error.message
                  : "Ellenőrizd az űrlapot.",
              );
            }
          }}
        >
          <fieldset disabled={locked || suggesting} className="space-y-6">
            {!!suggestedCapabilities.length && (
              <div className="space-y-3 text-sm">
                <p>
                  A kapcsolódó versenyek előzetes képességprofilja:{" "}
                  {suggestedCapabilities
                    .map((k) => capabilityLabels[k] ?? k)
                    .join(", ")}
                  . A javasolt szerepek és indoklások szerkeszthetők.
                </p>
                <button
                  type="button"
                  className="rounded-lg border border-zinc-600 px-4 py-2 text-teal-200"
                  onClick={() =>
                    setSelected(
                      new Set([
                        ...selected,
                        ...suggestedCapabilities.filter((k) =>
                          catalog.capabilities.includes(k),
                        ),
                      ]),
                    )
                  }
                >
                  Versenyprofil képességeinek kijelölése
                </button>
              </div>
            )}
            {catalog.capabilities.map((key) => {
              const suggested = suggestion?.rows.find(
                (r) => r.capability_key === key,
              );
              const goal =
                suggested ??
                base?.artifact.proposal.goals.find(
                  (g) => g.capability_key === key,
                );
              return (
                <div
                  key={key}
                  className="rounded-xl border border-zinc-700 p-4"
                >
                  <label className="flex items-center gap-3 font-medium">
                    <input
                      type="checkbox"
                      name="capability"
                      value={key}
                      checked={selected.has(key)}
                      onChange={(event) => {
                        const next = new Set(selected);
                        if (event.target.checked) next.add(key);
                        else next.delete(key);
                        setSelected(next);
                      }}
                      className="h-5 w-5 accent-teal-300"
                    />
                    {capabilityLabels[key] ?? key}
                  </label>
                  {selected.has(key) && (
                    <div className="mt-5 space-y-5">
                      {suggested && (
                        <details className="text-sm">
                          <summary>
                            Javaslat alapja és edzéscsalád-kapcsolatok
                          </summary>
                          <p className="my-2">
                            {suggested.sources
                              .map((s) =>
                                s.kind === "recorded_goal"
                                  ? "Rögzített célváltozat"
                                  : s.kind === "declared_goal"
                                    ? `Megadott cél: ${s.key}`
                                    : `Versenyprofil: ${s.key} · ${s.basis}`,
                              )
                              .join("; ")}
                          </p>
                          {suggested.family_links.length ? (
                            <ul>
                              {suggested.family_links.map((f) => (
                                <li key={f.family_key}>
                                  {familyNames[f.family_key] ?? f.family_key} ·{" "}
                                  {f.modality_key} ·{" "}
                                  {f.match === "primary"
                                    ? "elsődleges"
                                    : "másodlagos"}{" "}
                                  képességkapcsolat
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p>Még nincs hozzá kapcsolt edzéscsalád.</p>
                          )}
                          <p className="mt-2 text-zinc-400">
                            A családkapcsolat lefedettséget jelez. Sportág-,
                            állapot-, eszköz- és időbeli alkalmasságát még nem
                            értékeltük; nincs kiválasztott edzés vagy dózis.
                          </p>
                        </details>
                      )}

                      <Select
                        label="Szerep a makrociklusban"
                        name={`${key}.role`}
                        defaultValue={goal?.role ?? ""}
                        required
                      >
                        <option value="">Válassz szerepet</option>
                        {catalog.goal_roles.map((role) => (
                          <option key={role} value={role}>
                            {roleLabels[role]}
                          </option>
                        ))}
                      </Select>
                      <Area
                        label="Makrociklusszerep indoklása"
                        name={`${key}.rationale`}
                        defaultValue={goal?.rationale}
                        required
                      />
                      <button
                        type="button"
                        className="rounded border border-zinc-600 px-3 py-2 text-sm"
                        onClick={(event) => {
                          const form = event.currentTarget.form;
                          const source = form?.elements.namedItem(
                            `${key}.role`,
                          ) as HTMLSelectElement | null;
                          if (!form || !source?.value) {
                            invalid("Előbb válassz makrociklusszerepet.");
                            return;
                          }
                          for (const child of children) {
                            const target = form.elements.namedItem(
                              `${child.id}.${key}.role`,
                            ) as HTMLSelectElement | null;
                            if (target && !target.value)
                              target.value = source.value;
                          }
                        }}
                      >
                        A választott szerep az üres mezociklusmezőkbe
                      </button>
                      {children.map((child) => {
                        const directive =
                          suggested?.mesocycle_directives.find(
                            (d) => d.mesocycle_period_id === child.id,
                          ) ??
                          base?.artifact.proposal.mesocycle_directives.find(
                            (d) =>
                              d.mesocycle_period_id === child.id &&
                              d.capability_key === key,
                          );
                        return (
                          <fieldset
                            key={child.id}
                            className="space-y-3 border-l-2 border-zinc-600 pl-4"
                          >
                            <legend className="mb-2 text-sm font-semibold">
                              {child.title} · {child.start_date} –{" "}
                              {child.end_date}
                            </legend>
                            <Select
                              label={`Szerep: ${child.title}`}
                              name={`${child.id}.${key}.role`}
                              defaultValue={directive?.role ?? ""}
                              required
                            >
                              <option value="">Válassz szerepet</option>
                              {catalog.goal_roles.map((role) => (
                                <option key={role} value={role}>
                                  {roleLabels[role]}
                                </option>
                              ))}
                            </Select>
                            <Area
                              label={`Mezociklusszerep indoklása: ${child.title}`}
                              name={`${child.id}.${key}.rationale`}
                              defaultValue={directive?.rationale}
                              required
                            />
                          </fieldset>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
            <Area
              label="A teljes felosztás indoklása"
              name="rationale"
              defaultValue={
                base?.artifact.proposal.rationale ??
                (suggestion
                  ? `Felülvizsgált képességszerepek. Javaslatszabály: ${strategy?.rules_version ?? "declared-goal-review-v0.1"}. Tervezési bemenet SHA-256: ${captureHash}.`
                  : undefined)
              }
              required
            />
            {suggestion && (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" name="reviewed" required />
                Átnéztem a makro- és mezociklusszerepeket, valamint az
                indoklásokat.
              </label>
            )}
            <p className="text-sm text-zinc-400">
              A mentés új, utólag nem módosítható verziót hoz létre. A korábbi
              verzió megmarad.
            </p>
            <button
              className={buttonClass}
              type="submit"
              disabled={!selected.size}
            >
              Makrocikluscélok mentése
            </button>
          </fieldset>
        </form>
      )}
    </Card>
  );
}
