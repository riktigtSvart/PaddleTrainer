import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/session-analysis.json", import.meta.url)),
);
test("overview groups the title and six source metrics before the separate upper map slot", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      load("src/components/session-analysis/workspace.tsx").SessionDetails,
      { data: fixture },
    ),
  );
  const summary = html.indexOf("pt-analysis-overview-summary"),
    metrics = html.indexOf("pt-analysis-metrics"),
    map = html.indexOf("pt-analysis-overview-map"),
    chart = html.indexOf("pt-combined-chart");
  assert.ok(summary >= 0 && summary < metrics && metrics < map && map < chart);
  const block = html.slice(metrics, map);
  for (const label of [
    "Mért táv",
    "Forrás szerinti idő",
    "Energia",
    "Átlagpulzus",
    "Átlagsebesség",
    "Átlagteljesítmény",
  ])
    assert.ok(block.includes(label));
});
test("square route layout changes viewport geometry while retaining the source route and accessible controls", () => {
  const route = {
    exercise_index: 0,
    source_path: "exerciseSamples[0].routes.route",
    issues: [],
    points: [
      { index: 0, ms: 0, lat: 47, lon: 19 },
      { index: 1, ms: 1000, lat: 47.01, lon: 19.01 },
    ],
  };
  const Component = load(
    "src/components/session-analysis/route-map.tsx",
  ).RouteMap;
  const common = {
    route,
    cursor: 0,
    onCursor: () => {},
    syncAllowed: true,
    selected: null,
  };
  const square = renderToStaticMarkup(
      React.createElement(Component, { ...common, square: true }),
    ),
    wide = renderToStaticMarkup(React.createElement(Component, common));
  assert.match(square, /viewBox="0 0 1000 300"/);
  assert.match(square, /height:100%/);
  assert.match(wide, /viewBox="0 0 1000 190"/);
  assert.match(square, /Tárolt GPS-útvonal/);
  assert.match(square, /Térkép nagyítása/);
});
test("server render reserves a single upper map region without duplicating route graphics below the chart", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      load("src/components/session-analysis/workspace.tsx").SessionDetails,
      { data: fixture },
    ),
  );
  assert.equal((html.match(/pt-analysis-overview-map/g) || []).length, 1);
  assert.equal((html.match(/pt-route-panel/g) || []).length, 0);
  assert.ok(
    html.indexOf("pt-analysis-overview-map") < html.indexOf("Edzés szakaszai"),
  );
});
