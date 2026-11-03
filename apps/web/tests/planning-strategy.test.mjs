import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const data = JSON.parse(
  readFileSync(new URL("./fixtures/planning-strategy.json", import.meta.url)),
);
const { checkedSuggestion } = load(
  "src/lib/planning-cycles/goal-suggestions.ts",
);
const { readPlanningInputs } = load("src/lib/planning-cycles/inputs.ts");
const { StrategySummary } = load(
  "src/components/planning-goals/strategy-summary.tsx",
);
const m = data.goal_suggestions.macrocycles[0],
  period = data.periods.find((p) => p.id === m.macrocycle_period_id),
  children = data.periods.filter((p) => p.parent_id === period.id);
const base = { reference: m.base_reference, revision: m.base_revision };
const check = (v) =>
  checkedSuggestion(v, period, children, ["VO2_CAPACITY"], base);
test("owned Python HTTP strategic capture verifies complete dates, roles, base and hash", async () => {
  await readPlanningInputs(data, {
    owner: data.athlete_id,
    reference: data.program_reference,
    zone: data.timezone_name,
    first: data.start_date,
    last: data.end_date,
  });
  assert.equal(check(data).strategy_periods.length, children.length);
  assert.ok(
    m.rows.every((r) => r.role && r.mesocycle_directives.every((d) => d.role)),
  );
});
for (const [name, mutate] of [
  [
    "unassigned role",
    (v) =>
      (v.goal_suggestions.macrocycles[0].rows[0].mesocycle_directives[0].role =
        null),
  ],
  [
    "missing mesocycle strategy",
    (v) => v.goal_suggestions.macrocycles[0].strategy_periods.pop(),
  ],
  [
    "missing segment start",
    (v) =>
      (v.goal_suggestions.macrocycles[0].strategy_periods[0].segments[0].start_date =
        "2026-10-24"),
  ],
  [
    "changed race dates",
    (v) => (v.goal_suggestions.strategy.race_dates_changed = true),
  ],
  [
    "unannounced personal model",
    (v) => (v.goal_suggestions.strategy.personal_response_model.applied = true),
  ],
  [
    "dose prescription",
    (v) => (v.goal_suggestions.strategy.dose_selected = true),
  ],
  [
    "unknown strategic schema",
    (v) => (v.goal_suggestions.rules_version = "strategy-unknown"),
  ],
])
  test("strategic boundary rejects " + name, () => {
    const v = structuredClone(data);
    mutate(v);
    assert.throws(() => check(v));
  });
test("compact summary renders all mesocycles, roles, sources and model limitation", () => {
  const html = renderToStaticMarkup(
    React.createElement(StrategySummary, {
      suggestion: m,
      strategy: data.goal_suggestions,
    }),
  );
  assert.match(html, /Javasolt mezociklus-stratégia/);
  assert.equal(
    (html.match(/<tbody>[\s\S]*?<\/tbody>/) || [""])[0].split("<tr").length - 1,
    children.length,
  );
  assert.match(html, /személyes fejlődés–terhelés modell még nincs alkalmazva/);
  assert.match(html, /termékszabályok/);
  assert.match(html, /pubmed.ncbi.nlm.nih.gov\/20414669/);
});
test("event names and rationales render as text", () => {
  const v = structuredClone(m);
  v.strategy_periods[0].title = "<script>attack</script>";
  const html = renderToStaticMarkup(
    React.createElement(StrategySummary, {
      suggestion: v,
      strategy: data.goal_suggestions,
    }),
  );
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>attack/);
});
