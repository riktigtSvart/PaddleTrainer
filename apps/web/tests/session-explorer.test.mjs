import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const c = load("src/lib/session-analysis/contracts.ts"),
  x = load("src/lib/session-analysis/explorer.ts");
const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/session-analysis.json", import.meta.url)),
);
const series = (key, values, dt = 1000) => ({
  id: key,
  exercise_index: 0,
  metric_key: key,
  source_type: "TEST",
  source_path: "test",
  unit: "test",
  interval_ms: dt,
  values,
  slot_count: values.length,
  valid_sample_count: values.filter((v) => v !== null).length,
  missing_sample_count: values.filter((v) => v === null).length,
  issues: [],
});
test("distance is relative to a measured initial offset without losing zero", () => {
  const d = x.distanceSource([series("distance_m", [150, 153, 156])]);
  assert.equal(x.distanceAt(d, 0), 0);
  assert.equal(x.distanceAt(d, 2000), 6);
  assert.equal(x.distanceAt(d, 500), null);
  assert.equal(x.timeAtDistance(d, 5), 2000);
});
for (const values of [
  [null, 2, 3],
  [3, 2, 4],
  [1, 1, 1],
])
  test(
    "unusable distance disables the distance axis: " + JSON.stringify(values),
    () => assert.equal(x.distanceSource([series("distance_m", values)]), null),
  );
test("ambiguous distance and ambiguous metrics are never chosen arbitrarily", () => {
  const s = series("distance_m", [0, 3, 6]);
  assert.equal(x.distanceSource([s, { ...s, id: "other" }]), null);
});
test("distance gaps split curves before visual reduction", () => {
  const d = series("distance_m", [0, 1, null, 3, 4]),
    speed = series("speed_kmh", [10, 10, 10, 10, 10]);
  assert.deepEqual(
    x
      .plotRuns(speed, 0, 4000, "distance", d, "km/h")
      .map((run) => run.map((p) => p.ms)),
    [
      [0, 1000],
      [3000, 4000],
    ],
  );
});
test("unit conversion leaves measured source values intact", () => {
  const s = series("speed_kmh", [18.52, 0]),
    before = structuredClone(s);
  assert.equal(x.plotRuns(s, 0, 1000, "time", null, "knots")[0][0].y, 10);
  assert.deepEqual(s, before);
});
test("GPS nearest point has an explicit five-second maximum, without filling missing coordinates", () => {
  const points = [
    { index: 0, ms: 0, lat: 0, lon: 0 },
    { index: 1, ms: 3000, lat: null, lon: null },
  ];
  assert.equal(x.nearestRoute(points, 0), points[0]);
  assert.equal(x.nearestRoute(points, 6000), null);
});
test("GPS gaps and antimeridian jumps split map lines", () => {
  const points = [
    { index: 0, ms: 0, lat: 1, lon: 179 },
    { index: 1, ms: 1000, lat: 1, lon: -179 },
    { index: 2, ms: 2000, lat: null, lon: null },
    { index: 3, ms: 3000, lat: 1, lon: 10 },
  ];
  assert.equal(x.routeRuns(points).length, 3);
});
test("saved graph choices are owner scoped, reject unknown metrics, and prevent duplicate axes", () => {
  const raw = { ...x.defaultChoices, left: "power_w", right: "power_w" };
  assert.equal(x.readChoices(JSON.stringify(raw)).right, "none");
  assert.notEqual(x.explorerKey("a"), x.explorerKey("b"));
  assert.throws(() =>
    x.readChoices(JSON.stringify({ ...raw, left: "invented" })),
  );
});
test("GPS contract accepts valid zero coordinates but rejects invented clock, exercise and count", () => {
  const data = structuredClone(fixture),
    exercise = data.samples.exercises[0];
  data.samples.routes = [
    {
      exercise_index: exercise.index,
      source_path: exercise.source_path + ".routes.route",
      points: [{ index: 0, ms: 0, lat: 0, lon: 0 }],
      issues: [],
    },
  ];
  assert.equal(c.readAnalysis(data, data.session.id), data);
  for (const change of [
    (r) => (r.exercise_index = 999),
    (r) => (r.points[0].lat = 91),
    (r) => (r.points[0].ms = true),
    (r) => (r.points[0].index = 9),
  ]) {
    const bad = structuredClone(data);
    change(bad.samples.routes[0]);
    assert.throws(() => c.readAnalysis(bad, bad.session.id));
  }
});
test("default details put the summary and map slot above the common chart, with section tables below", () => {
  const Component = load(
    "src/components/session-analysis/workspace.tsx",
  ).SessionDetails;
  const html = renderToStaticMarkup(
    React.createElement(Component, { data: fixture }),
  );
  assert.ok(
    html.indexOf("GPS útvonal helye") < html.indexOf("Közös edzésgrafikon"),
  );
  assert.ok(
    html.indexOf("GPS útvonal") < html.indexOf("Szakaszok és részidők"),
  );
  assert.match(html, /Saját visszajelzés/);
  assert.doesNotMatch(html, /Megfigyelés időpontja · UTC/);
  assert.match(html, /Előírt célsávok/);
  assert.match(html, /Edzési zónák/);
});
