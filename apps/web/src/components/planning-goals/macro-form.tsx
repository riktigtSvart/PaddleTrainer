"use client";
import { useState } from "react";
import { macroProposal } from "@/lib/planning-goals/forms";
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
};
export default function MacroForm({
  catalog,
  period,
  periods,
  base,
  locked,
  submit,
  invalid,
}: Props) {
  const [selected, setSelected] = useState(
    () =>
      new Set(base?.artifact.proposal.goals.map((g) => g.capability_key) ?? []),
  );
  const children = periods.filter(
    (p) => p.parent_id === period.id && p.period_type === "MESOCYCLE",
  );
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
      {!children.length ? (
        <p className="text-amber-200">
          Előbb hozz létre legalább egy közvetlen mezociklust ehhez a
          makrociklushoz.
        </p>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            try {
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
          <fieldset disabled={locked} className="space-y-6">
            {catalog.capabilities.map((key) => {
              const goal = base?.artifact.proposal.goals.find(
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
                      {children.map((child) => {
                        const directive =
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
              defaultValue={base?.artifact.proposal.rationale}
              required
            />
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
