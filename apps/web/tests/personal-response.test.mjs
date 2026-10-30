import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const c = load("src/lib/personal-response/contracts.ts"),
  p = load("src/lib/personal-response/presentation.ts");
const { ScoreChart } = load("src/components/personal-response/charts.tsx"),
  { PersonalResponseData } = load(
    "src/components/personal-response/workspace.tsx",
  );
const { forwardCalendar } = load("src/lib/calendar/proxy.ts");
const sample = JSON.parse(
  readFileSync(
    new URL("./fixtures/personal-response.json", import.meta.url),
    "utf8",
  ),
);
const clone = (x) => structuredClone(x);
test("real Python empty and connected C14 responses pass the frontend contract", () => {
  for (const x of Object.values(sample))
    assert.equal(c.readPersonalInputs(x).athlete_id, x.athlete_id);
});
test("counts distinguish five answers from one workout and one occasion, preserving zero and unknown", () => {
  const x = c.readPersonalInputs(sample.connected);
  assert.deepEqual(p.census(x), {
    sessions: 1,
    occasions: 1,
    known: 3,
    missing: 2,
  });
  assert.ok(x.assembly.response_observations.some((o) => o.value === 0));
});
for (const [label, mutate] of [
  [
    "owner mismatch",
    (x) =>
      (x.assembly.response_observations[0].athlete_id = crypto.randomUUID()),
  ],
  [
    "response after cutoff",
    (x) =>
      (x.assembly.response_observations[0].response_available_at =
        "2099-01-01T00:00:00Z"),
  ],
  ["unknown timezone", (x) => (x.timezone_name = "Invalid/Zone")],
  ["numeric planning authority", (x) => (x.planning_authorized = 0)],
  [
    "assembly causal authority",
    (x) => (x.assembly.causal_attribution_established = true),
  ],
  [
    "observational readiness",
    (x) =>
      (x.assembly.response_observations[0].readiness_inference_authorized = true),
  ],
  [
    "dataset inference",
    (x) => (x.assembly.datasets[0].association_supported = true),
  ],
  [
    "pair inference",
    (x) => (x.assembly.datasets[0].pairs[0].effect_inference_authorized = true),
  ],
  [
    "lying pair count",
    (x) => (x.assembly.datasets[0].eligible_numeric_pair_count = 99),
  ],
  [
    "orphan pair",
    (x) => (x.assembly.datasets[0].pairs[0].response_observation_id = "other"),
  ],
  [
    "pair hash mismatch",
    (x) =>
      (x.assembly.datasets[0].pairs[0].response_observation_content_hash =
        "f".repeat(64)),
  ],
  [
    "mixed context",
    (x) =>
      (x.assembly.datasets[0].pairs[0].response_key.response_timing =
        "next_morning"),
  ],
  [
    "wrong unit",
    (x) => (x.assembly.datasets[0].pairs[0].predictor_observed_unit = "min"),
  ],
  ["boolean score", (x) => (x.assembly.response_observations[0].value = true)],
  [
    "out-of-scale score",
    (x) => (x.assembly.response_observations[0].value = 11),
  ],
  [
    "unknown changed to zero",
    (x) => {
      const o = x.assembly.response_observations.find(
        (o) => o.knowledge_status === "unknown",
      );
      o.value = 0;
    },
  ],
  [
    "duplicate observation",
    (x) =>
      x.assembly.response_observations.push(
        clone(x.assembly.response_observations[0]),
      ),
  ],
  [
    "duplicate dataset",
    (x) => x.assembly.datasets.push(clone(x.assembly.datasets[0])),
  ],
  [
    "wrong history",
    (x) =>
      (x.assembly.datasets[0].source_history_content_hash = "e".repeat(64)),
  ],
  [
    "past cutoff masquerades as current",
    (x) => (x.as_of = "2026-10-24T00:00:00Z"),
  ],
])
  test("contract rejects " + label, () => {
    const x = clone(sample.connected);
    mutate(x);
    assert.throws(() => c.readPersonalInputs(x));
  });
test("all exact context dimensions remain separated", () => {
  const x = clone(sample.connected),
    a = x.assembly.response_observations[0];
  x.assembly.response_observations.push(
    { ...a, observation_id: "another", response_timing: "next_morning" },
    { ...a, observation_id: "third", stimulus_modality_key: "RUN" },
  );
  assert.equal(p.contexts(x).length, 7);
  const original = c.contextId(a);
  assert.equal(p.selectedObservations(x, original).length, 1);
});
test("the chart shows a known zero, never plots an unknown value and never invents connecting lines", () => {
  const obs = sample.connected.assembly.response_observations,
    zero = obs.find((o) => o.value === 0),
    missing = obs.find((o) => o.value === null);
  const html = renderToStaticMarkup(
    React.createElement(ScoreChart, {
      observations: [zero, missing],
      zone: "Europe/Budapest",
    }),
  );
  assert.equal((html.match(/<circle/g) || []).length, 1);
  assert.match(html, /cy="210"/);
  assert.doesNotMatch(html, /<polyline|<path/);
  assert.match(html, new RegExp("/sessions/" + zero.workout_session_id));
});
test("one-point scatter is visible in minutes without correlation or a regression line", () => {
  const d = sample.connected.assembly.datasets.find(
      (d) => d.eligible_numeric_pair_count === 1,
    ),
    obs = p.selectedObservations(sample.connected, c.contextId(d.response_key));
  const html = renderToStaticMarkup(
    React.createElement(ScoreChart, {
      observations: obs,
      dataset: d,
      zone: "Europe/Budapest",
      scatter: true,
    }),
  );
  assert.match(html, /45 perc/);
  assert.match(html, /<circle/);
  assert.doesNotMatch(html, /<polyline/);
});
test("empty screen is actionable and does not claim there are no measured workouts", () => {
  const html = renderToStaticMarkup(
    React.createElement(PersonalResponseData, { data: sample.empty }),
  );
  assert.match(html, /Tanulási kapcsolat/);
  assert.match(html, /Edzés keresése/);
  assert.doesNotMatch(html, /<circle/);
});
test("unknown limitation codes and source modality are visible as escaped text", () => {
  const x = clone(sample.connected);
  x.assembly.data_sufficiency.limitation_codes.push(
    "<script>alert(1)</script>",
  );
  const html = renderToStaticMarkup(
    React.createElement(PersonalResponseData, { data: x }),
  );
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});
test("large contexts do not silently truncate charts or table totals", () => {
  const o = sample.connected.assembly.response_observations.find(p.knownScore),
    obs = Array.from({ length: 501 }, (_, i) => ({
      ...o,
      observation_id: String(i),
    }));
  const html = renderToStaticMarkup(
    React.createElement(ScoreChart, {
      observations: obs,
      zone: "Europe/Budapest",
    }),
  );
  assert.match(html, /500 pont/);
  assert.match(html, /összes adat/);
  assert.doesNotMatch(html, /<circle/);
});
test("calendar dates reject rollover, reverse and overlong ranges without using browser timezone", () => {
  for (const [a, b] of [
    ["2026-02-30", "2026-03-01"],
    ["2026-10-25", "2026-10-23"],
    ["2024-01-01", "2025-01-01"],
    ["", "2026-10-01"],
  ])
    assert.throws(() => c.checkedRange(a, b));
  assert.deepEqual(c.checkedRange("2026-01-01", "2027-01-01"), {
    start: "2026-01-01",
    end: "2027-01-01",
  });
});
test("source times use the profile timezone, independently of the browser zone", () => {
  assert.match(
    p.formatInstant("2026-10-24T00:30:00Z", "America/New_York"),
    /23/,
  );
  assert.match(
    p.formatInstant("2026-10-24T00:30:00Z", "Europe/Budapest"),
    /24/,
  );
});
test("read transport sends only a bounded GET, does not freeze sources or sync providers", async () => {
  const old = globalThis.fetch,
    calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    return Response.json(sample.connected);
  };
  try {
    await c.loadPersonalInputs(null);
    await c.loadPersonalInputs({ start: "2026-10-01", end: "2026-10-28" });
    assert.equal(calls[0][0], "/api/calendar/learning-inputs");
    assert.ok(
      calls[1][0].endsWith("?start_date=2026-10-01&end_date=2026-10-28"),
    );
    assert.ok(
      calls.every(
        (x) => x[1].method === "GET" && !x[1].body && x[1].cache === "no-store",
      ),
    );
  } finally {
    globalThis.fetch = old;
  }
});
test("read errors are errors, never empty success", async () => {
  const old = globalThis.fetch;
  globalThis.fetch = async () =>
    Response.json({ detail: "unavailable" }, { status: 503 });
  try {
    await assert.rejects(c.loadPersonalInputs(null));
  } finally {
    globalThis.fetch = old;
  }
});
test("existing closed proxy forwards personal inputs GET without credentials and rejects writes or owner injection", async () => {
  let calls = 0;
  const send = async (url, options) => {
    calls++;
    assert.equal(options.method, "GET");
    assert.equal(options.headers.Authorization, undefined);
    return Response.json(sample.connected);
  };
  assert.equal(
    (
      await forwardCalendar(
        new Request(
          "http://localhost:3000/api/calendar/learning-inputs?start_date=2026-10-01&end_date=2026-10-28",
        ),
        ["learning-inputs"],
        "http://api",
        send,
      )
    ).status,
    200,
  );
  assert.equal(
    (
      await forwardCalendar(
        new Request("http://localhost:3000/api/calendar/learning-inputs", {
          method: "POST",
        }),
        ["learning-inputs"],
        "http://api",
        send,
      )
    ).status,
    405,
  );
  assert.equal(
    (
      await forwardCalendar(
        new Request(
          "http://localhost:3000/api/calendar/learning-inputs?athlete_id=other",
        ),
        ["learning-inputs"],
        "http://api",
        send,
      )
    ).status,
    422,
  );
  assert.equal(calls, 1);
});
