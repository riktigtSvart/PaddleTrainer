import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/sport-goals.json", import.meta.url)));
const cycles = load("src/lib/planning-cycles/contracts.ts");
const athlete = load("src/lib/athlete-setup/contracts.ts");
const history = load("src/lib/athlete-setup/sport-history.ts");
const goals = load("src/lib/planning-data/sport-goals.ts");
const SportContext = load("src/components/athlete-setup/sport-context.tsx").default;
const pending = { schema_version: "cycle-pending-v0.1", operation: "programs", body: JSON.stringify(fixture.replacement_request) };

test("real owned sport profile and goal replacement verify without altering old receipts", async () => {
  const before = cycles.canonical(fixture);
  await athlete.readReceipt(fixture.profile);
  await cycles.readReceipt(fixture.first);
  await cycles.readReceipt(fixture.replacement, pending);
  assert.equal(cycles.canonical(fixture), before);
  const data = fixture.profile.artifact.proposal.data;
  const normalized = athlete.normalizeProfile(data, fixture.context.local_today);
  assert.deepEqual(normalized, data);
  assert.equal(data.sport_history[0].performances[0].time, "1:42.500");
  assert.equal(data.sport_history[1].role, "secondary");
  assert.equal(data.sport_history[1].level, "unknown");
});

test("performance times retain fractional precision and unknown historical dates", () => {
  const row = fixture.profile.artifact.proposal.data.sport_history[0].performances[0];
  const normalized = history.normalizePerformance({ ...row, time: " 1:42,500 ", distance_m: "500,000", recorded_on: null, year: null }, fixture.context.local_today);
  assert.equal(normalized.time, "1:42.500");
  assert.equal(normalized.distance_m, "500.000");
  assert.equal(normalized.recorded_on, null);
  assert.equal(normalized.year, null);
  assert.equal(history.performanceSeconds(normalized.time), 102.5);
  assert.equal(history.performanceSeconds("1:20:00.125"), 4800.125);
});

for (const value of ["1:60", "0:00", "1:99:00", "-1:00", "1:42.0001", "170:00:00", "23", "NaN"]) test(`historical performance refuses ambiguous time ${value}`, () => {
  assert.throws(() => history.performanceSeconds(value));
});

test("a former best cannot acquire a fabricated current date or a future year", () => {
  const row = fixture.profile.artifact.proposal.data.sport_history[0].performances[0];
  assert.throws(() => history.normalizePerformance({ ...row, year: 2100 }, fixture.context.local_today));
  assert.throws(() => history.normalizePerformance({ ...row, recorded_on: "2001-01-01", year: 2001 }, fixture.context.local_today));
  assert.throws(() => history.normalizePerformance({ ...row, recorded_on: "2100-01-01", year: null }, fixture.context.local_today));
});

test("supplementary and leisure sports use purpose and proficiency independently of competitive level", () => {
  const sport = fixture.profile.artifact.proposal.data.sport_history[1];
  const render = (value) => renderToStaticMarkup(React.createElement(SportContext, { value, change() {}, primarySports: ["Kajak"], today: fixture.context.local_today }));
  const support = render(sport), leisure = render({ ...sport, role: "recreation" });
  assert.match(support, /Szerepe a felkészülésben/);
  assert.match(support, /Állóképességi munka helyettesítése/);
  assert.match(support, /Gyakorlati jártasság/);
  assert.match(support, /Kajak/);
  assert.doesNotMatch(support, /Hivatásos \/ élversenyző/);
  assert.doesNotMatch(leisure, /Szerepe a felkészülésben/);
  assert.match(leisure, /Kedvelt, szabadidős mozgás/);
  assert.equal(sport.level, "unknown");
});

for (const mode of ["olympic", "season", "race", "recreation"]) test(`new ${mode} goal has complete hidden-cycle data while retaining its own mode`, () => {
  const { program, end } = goals.newSportGoal(mode, fixture.catalog, "Kajak");
  assert.equal(program.mode, mode);
  assert.equal(program.sport, "Kajak");
  assert.equal(program.macrocycles[0].start_date, program.start_date);
  assert.equal(program.macrocycles.at(-1).end_date, end);
  for (const macro of program.macrocycles) {
    assert.equal(macro.mesocycles[0].start_date, macro.start_date);
    assert.equal(macro.mesocycles.at(-1).end_date, macro.end_date);
    for (let i = 1; i < macro.mesocycles.length; i++) assert.equal(cycles.addDays(macro.mesocycles[i - 1].end_date, 1), macro.mesocycles[i].start_date);
  }
  assert.equal(program.end_date, mode === "recreation" ? null : end);
});

test("goal edits pin the exact program, competition and boundary sources and leave originals intact", () => {
  const detail = structuredClone(fixture.detail), original = cycles.canonical(detail);
  const program = goals.effectiveProgram(detail);
  program.title = "A következő átnézett cél";
  const changed = goals.replacementProgram(program, detail, program.athlete_context);
  assert.notEqual(changed.program_id, program.program_id);
  assert.equal(changed.replacement.revision, 2);
  assert.deepEqual(changed.replacement.program_reference, cycles.reference(detail.program.artifact));
  assert.deepEqual(changed.replacement.competition_reference, cycles.reference(detail.program.artifact));
  assert.equal(changed.replacement.boundary_reference, null);
  assert.equal(cycles.canonical(detail), original);
  const framed = goals.goalFrame({ ...program, start_date: "2030-01-03" }, "2030-04-02");
  assert.equal(framed.macrocycles[0].start_date, "2030-01-03");
  assert.equal(framed.macrocycles.at(-1).end_date, "2030-04-02");
});

test("the goal list shows the current version and retains unrelated objectives", () => {
  assert.deepEqual(goals.currentGoalPrograms([fixture.replacement, fixture.first]), [fixture.replacement]);
  const other = structuredClone(fixture.first); other.artifact.artifact_id = "pt-cycle:" + "a".repeat(64);
  assert.deepEqual(goals.currentGoalPrograms([fixture.replacement, fixture.first, other]), [fixture.replacement, other]);
});

for (const field of ["program_reference", "competition_reference"]) test(`a rehashed receipt cannot replace its retained ${field}`, async () => {
  const changed = structuredClone(fixture.replacement);
  changed.artifact.proposal.replacement[field].content_hash = "f".repeat(64);
  delete changed.artifact.content_hash; changed.artifact.content_hash = await cycles.sha(changed.artifact);
  await assert.rejects(cycles.readReceipt(changed, pending));
});

test("unsupported replacement metadata is rejected even with a fresh outer hash", async () => {
  const changed = structuredClone(fixture.replacement);
  changed.artifact.proposal.replacement.version = "future-version";
  delete changed.artifact.content_hash; changed.artifact.content_hash = await cycles.sha(changed.artifact);
  await assert.rejects(cycles.readReceipt(changed));
});

test("following current goal versions uses exact parent references rather than a shared recreation family", async () => {
  const { loadCurrentDetail } = load("src/lib/planning-cycles/client.ts"), before = globalThis.fetch;
  const first = { program: fixture.first, competition_revisions: [], boundary_revisions: [], replaced_by: cycles.reference(fixture.replacement.artifact) };
  globalThis.fetch = async (url) => Response.json(decodeURIComponent(String(url)).endsWith(fixture.first.artifact.artifact_id) ? first : { ...fixture.detail, replaced_by: null });
  try {
    assert.equal((await loadCurrentDetail(fixture.first.artifact.artifact_id)).program.artifact.artifact_id, fixture.replacement.artifact.artifact_id);
    const wrong = structuredClone(fixture.detail);
    wrong.program.artifact.proposal.replacement.program_reference.content_hash = "f".repeat(64);
    delete wrong.program.artifact.content_hash; wrong.program.artifact.content_hash = await cycles.sha(wrong.program.artifact);
    first.replaced_by = cycles.reference(wrong.program.artifact);
    globalThis.fetch = async (url) => Response.json(decodeURIComponent(String(url)).endsWith(fixture.first.artifact.artifact_id) ? first : { ...wrong, replaced_by: null });
    await assert.rejects(loadCurrentDetail(fixture.first.artifact.artifact_id));
  } finally { globalThis.fetch = before; }
});
