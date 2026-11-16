import { addDays, anniversary, defaultStructure, reference } from "@/lib/planning-cycles/contracts";
import type { AthleteContext, Catalog, Detail, Mode, Program, Receipt } from "@/lib/planning-cycles/contracts";

export const sportGoalModes: Record<Mode, string> = { olympic: "Olimpiai ciklus", season: "Szezon", race: "Versenycél", recreation: "Rekreáció" };
export function newSportGoal(mode: Mode, catalog: Catalog, sport: string): { program: Program; end: string } {
  const start = catalog.local_today, edition = catalog.olympics.find((v) => v.kind === "summer" && v.end_date >= start);
  const end = mode === "olympic" ? edition?.end_date ?? "" : mode === "season" ? addDays(anniversary(start), -1) : addDays(start, 83);
  const program: Program = {
    program_id: crypto.randomUUID(), mode, title: mode === "season" ? `${start.slice(0, 4)} szezon` : sportGoalModes[mode], sport,
    start_date: start, end_date: mode === "recreation" ? null : end, olympic_key: mode === "olympic" ? edition?.key ?? null : null,
    seasons: [], macrocycles: [], competitions: [], goals: [], continued_from: null,
    planning_basis: { version: "cycle-planning-basis-v0.1", mesocycle_dates: "provisional", initial_mesocycle_days: 28 },
  };
  return { program: defaultStructure(program, end), end };
}
export function effectiveProgram(detail: Detail): Program {
  const program = structuredClone(detail.program.artifact.proposal), periods = detail.boundary_revisions.at(-1)?.artifact.periods ?? detail.program.artifact.periods;
  const update = <T extends { key: string; start_date: string; end_date: string }>(p: T): T => {
    const current = periods.find((v) => v.key === p.key);
    return current ? { ...p, start_date: current.start_date, end_date: current.end_date } : p;
  };
  program.seasons = program.seasons.map(update);
  program.macrocycles = program.macrocycles.map((m) => ({ ...update(m), mesocycles: m.mesocycles.map(update) }));
  program.competitions = structuredClone(detail.competition_revisions.at(-1)?.artifact.proposal.competitions ?? program.competitions);
  return program;
}
export function goalFrame(program: Program, end: string): Program {
  const begin = program.macrocycles.map((v) => v.start_date).sort()[0], finish = program.macrocycles.map((v) => v.end_date).sort().at(-1);
  const next = { ...program, end_date: program.mode === "recreation" ? null : end };
  return begin === program.start_date && finish === end ? next : defaultStructure(next, end);
}
export function replacementProgram(program: Program, source: Detail | null, context: AthleteContext): Program {
  return { ...structuredClone(program), athlete_context: context,
    ...(source ? { program_id: crypto.randomUUID(), replacement: {
      version: "cycle-program-replacement-v0.1" as const, revision: (source.program.artifact.proposal.replacement?.revision ?? 0) + 1,
      program_reference: reference(source.program.artifact), competition_reference: reference(source.competition_revisions.at(-1)?.artifact ?? source.program.artifact),
      boundary_reference: source.boundary_revisions.length ? reference(source.boundary_revisions.at(-1)!.artifact) : null,
    } } : {}),
  };
}
export function currentGoalPrograms(items: Receipt[]): Receipt[] {
  const replaced = new Set(items.flatMap((v) => v.artifact.proposal.replacement ? [v.artifact.proposal.replacement.program_reference.artifact_id] : []));
  return items.filter((v) => !replaced.has(v.artifact.artifact_id));
}
