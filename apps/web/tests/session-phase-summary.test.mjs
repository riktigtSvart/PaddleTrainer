import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const { currentPhase } = load("src/lib/session-analysis/phase-summary.ts");
const { phaseResults } = load("src/lib/session-analysis/phase-statistics.ts");
const data = JSON.parse(
  readFileSync(new URL("./fixtures/phase-assessment.json", import.meta.url)),
);
const part = data.plan_timeline.parts[0];
const results = phaseResults(part, [], data.samples.series, data.plan, {
  heart_rate: null,
  speed: null,
  power: null,
});
test("hover selects exactly one half-open phase, including the last endpoint", () => {
  const rows = [
    { from_ms: 0, to_ms: 1000 },
    { from_ms: 1000, to_ms: 2000 },
  ];
  assert.equal(currentPhase(rows, 999), rows[0]);
  assert.equal(currentPhase(rows, 1000), rows[1]);
  assert.equal(currentPhase(rows, 2000), rows[1]);
  assert.equal(currentPhase(rows, 2001), null);
});
test("unknown, overlapping, empty and out-of-window phases do not inherit session totals", () => {
  for (const rows of [
    [],
    [{ from_ms: null, to_ms: null }],
    [
      { from_ms: 0, to_ms: 1000 },
      { from_ms: 0, to_ms: 2000 },
    ],
    [{ from_ms: 0, to_ms: 0 }],
  ])
    assert.equal(currentPhase(rows, 0), null);
  assert.equal(currentPhase(results, NaN), null);
});
test("waits and unassigned intervals remain their own summary windows", () => {
  const wait = { from_ms: 1000, to_ms: 2000, kind: "wait" };
  assert.equal(currentPhase([wait], 1500), wait);
});
test("phase cards use source-window means and never allocate whole-session calories", () => {
  const first = currentPhase(results, 0);
  assert.equal(first.distance_m, 30);
  assert.equal(first.observed_ms, 10000);
  assert.equal(first.heart_rate.value, 104.5);
  const combined = phaseResults(
    part,
    [],
    load("src/lib/session-analysis/chart-data.ts").withPace(
      data.samples.series,
    ),
    data.plan,
    { heart_rate: null, speed: null, power: null },
  );
  assert.ok(Math.abs(currentPhase(combined, 0).power.value - 110) < 1e-10);
  const Component = load(
    "src/components/session-analysis/phase-summary.tsx",
  ).PhaseSummary;
  const html = renderToStaticMarkup(
    React.createElement(Component, {
      results,
      cursor: 0,
      speedUnit: "knots",
      sourceLabel: "Számított tervhatárok",
    }),
  );
  assert.match(html, /Szakasz távja/);
  assert.match(html, /Szakasz időtartama/);
  assert.match(html, /Szakasz energiája/);
  assert.match(html, /Nincs adat/);
  assert.match(html, /knots/);
  assert.match(html, /Számított tervhatárok/);
  const empty = renderToStaticMarkup(
    React.createElement(Component, {
      results: [],
      cursor: 0,
      speedUnit: "m\/s",
      sourceLabel: "",
    }),
  );
  assert.match(empty, /nincs egyértelműen illesztett szakasz/);
});
