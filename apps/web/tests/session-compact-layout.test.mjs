import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const data = JSON.parse(
  readFileSync(new URL("./fixtures/phase-assessment.json", import.meta.url)),
);
function explorer(patch = {}) {
  return renderToStaticMarkup(
    React.createElement(
      load("src/components/session-analysis/explorer.tsx").SessionExplorer,
      {
        data,
        exercise: 0,
        speedUnit: "km/h",
        onSpeedUnitChange: () => {},
        ...patch,
      },
    ),
  );
}
test("left sidebar owns the general controls and left metric; right sidebar owns its metric", () => {
  const html = explorer(),
    left = html.slice(
      html.indexOf("pt-chart-side-left"),
      html.indexOf("pt-chart-side-right"),
    ),
    right = html.slice(
      html.indexOf("pt-chart-side-right"),
      html.indexOf("pt-combined-svg"),
    );
  for (const label of [
    "Bal tengely adatsora",
    "Bal tengely aktuális értéke",
    "Vízszintes tengely",
    "Célsáv",
    "Megjelenítés",
    "Sebesség egysége",
    "Teljes edzésrész",
  ])
    assert.ok(left.includes(label), label);
  assert.ok(right.includes("Jobb tengely adatsora"));
  assert.ok(right.includes("Jobb tengely aktuális értéke"));
  assert.ok(!right.includes("Vízszintes tengely"));
  assert.ok(html.indexOf("pt-phase-ribbon") > html.indexOf("pt-combined-svg"));
  assert.ok(html.indexOf("pt-linked-cursor") > html.indexOf("pt-phase-ribbon"));
});
test("standalone cursor readout contains only time and distance and precedes the chart block", () => {
  const html = explorer();
  const readout = html.slice(
    html.indexOf("pt-position-readout"),
    html.indexOf("pt-combined-chart"),
  );
  assert.match(readout, /Idő · 0:00/);
  assert.match(readout, /Táv/);
  assert.doesNotMatch(readout, /minta|Warmup/);
});
test("session overview reserves a name row for the full workout and a separate cursor slot after the metrics", () => {
  const input = structuredClone(data);
  input.plan.title = "<Full workout>";
  const html = renderToStaticMarkup(
    React.createElement(
      load("src/components/session-analysis/workspace.tsx").SessionDetails,
      { data: input },
    ),
  );
  assert.match(html, /pt-summary-name/);
  assert.match(html, /&lt;Full workout&gt;/);
  assert.doesNotMatch(html, /<Full workout>/);
  assert.ok(
    html.indexOf("pt-position-slot") > html.indexOf("pt-analysis-metrics"),
  );
  assert.ok(
    html.indexOf("pt-position-slot") > html.indexOf("pt-analysis-overview-map"),
  );
  assert.ok(
    html.indexOf("pt-map-credit-slot") > html.indexOf("pt-position-slot"),
  );
  assert.ok(
    html.indexOf("pt-map-credit-slot") < html.indexOf("pt-combined-chart"),
  );
});
test("route is drawn with a dark halo and a vivid line while map controls and attribution remain accessible", () => {
  const route = {
    exercise_index: 0,
    source_path: "test",
    issues: [],
    points: [
      { index: 0, ms: 0, lat: 47, lon: 19 },
      { index: 1, ms: 1000, lat: 47.01, lon: 19.01 },
    ],
  };
  const html = renderToStaticMarkup(
    React.createElement(
      load("src/components/session-analysis/route-map.tsx").RouteMap,
      {
        route,
        cursor: 0,
        onCursor: () => {},
        syncAllowed: true,
        selected: { from: 0, to: 1000 },
        square: true,
      },
    ),
  );
  for (const text of [
    "is-overview-map",
    "pt-route-toolbar",
    "pt-route-credit",
    "OpenStreetMap",
    "OpenTopoMap",
    "Térkép nagyítása",
    'stroke="#152034"',
    'stroke="#ff3fa4"',
    'stroke="#ffe66d"',
  ])
    assert.ok(html.includes(text), text);
  assert.match(html, /viewBox="0 0 1000 300"/);
});
test("missing route and unresolved clock keep their explicit messages with overlay layout", () => {
  const Component = load(
    "src/components/session-analysis/route-map.tsx",
  ).RouteMap;
  const html = renderToStaticMarkup(
    React.createElement(Component, {
      route: null,
      cursor: 0,
      onCursor: () => {},
      syncAllowed: false,
      selected: null,
      square: true,
    }),
  );
  assert.match(html, /nincs megjeleníthető tárolt GPS-útvonal/);
  assert.ok(!html.includes("<polyline"));
});
