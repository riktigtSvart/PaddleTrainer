import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const data = JSON.parse(
    readFileSync(new URL("./fixtures/planning-inputs.json", import.meta.url)),
  ),
  { readPlanningInputs } = load("src/lib/planning-cycles/inputs.ts"),
  { sha } = load("src/lib/planning-cycles/contracts.ts");
const expected = {
  owner: data.athlete_id,
  reference: data.program_reference,
  zone: data.timezone_name,
  first: data.start_date,
  last: data.end_date,
};
const signed = async (v) => {
  const body = { ...v };
  delete body.content_hash;
  return { ...body, content_hash: await sha(body) };
};
test("real Python HTTP fixture verifies its hash, per-day roles and source constraints", async () => {
  const result = await readPlanningInputs(data, expected);
  assert.equal(result.days.length, 7);
  assert.equal(result.days[0].capability_roles[0].role, "maintenance");
  assert.deepEqual(result.days[0].opportunities[0].constraints.sports, [
    "Futás",
  ]);
  assert.equal(result.days[0].opportunities[0].constraints.effort_cap, "easy");
  assert.equal(result.days[0].daily_max_minutes, 90);
});
for (const [name, change] of [
  [
    "foreign owner",
    (v) => (v.athlete_id = "00000000-0000-0000-0000-000000000001"),
  ],
  ["wrong program", (v) => (v.program_reference.content_hash = "f".repeat(64))],
  ["wrong timezone", (v) => (v.timezone_name = "UTC")],
  ["missing last day", (v) => v.days.pop()],
  ["duplicate date", (v) => (v.days[1].date = v.days[0].date)],
  [
    "invented goal role",
    (v) => (v.days[0].capability_roles[0].role = "unspecified"),
  ],
  ["authority escalation", (v) => (v.planning_authorized = true)],
  ["unexpected plan creation", (v) => (v.workouts_created = true)],
  ["unverified durable claim", (v) => (v.durable = true)],
  ["truncated result", (v) => (v.has_more = true)],
  [
    "unexpected personal model",
    (v) => (v.planner_connection.personal_model_applied = true),
  ],
  [
    "unannounced generator",
    (v) => (v.planner_connection.workout_generator_connected = true),
  ],
])
  test(
    "reject " + name + " even with an internally recomputed hash",
    async () => {
      const changed = structuredClone(data);
      change(changed);
      await assert.rejects(readPlanningInputs(await signed(changed), expected));
    },
  );
test("reject modified data when the original response hash is retained", async () => {
  const changed = structuredClone(data);
  changed.days[0].opportunities[0].max_minutes = 999;
  await assert.rejects(
    readPlanningInputs(changed, expected),
    /tartalomlenyomata/,
  );
});
test("input preview stays collapsed and does not promise a workout plan", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      load("src/components/planning-cycles/planning-inputs.tsx")
        .PlanningInputPanel,
      {
        owner: expected.owner,
        reference: expected.reference,
        zone: expected.zone,
        today: expected.first,
      },
    ),
  );
  assert.match(html, /Edzéstervezés · bemeneti adatok/);
  assert.match(html, /még nem készít edzéstervet/);
  assert.ok(!html.includes("<details open"));
  assert.ok(html.includes('type="date"'));
});
test("proxy forwards only the owned, read-only program input endpoint and date query", async () => {
  const { forwardGoals } = load("src/lib/planning-goals/proxy.ts");
  let called;
  const path = [
    "cycles",
    "programs",
    expected.reference.artifact_id,
    "planning-inputs",
  ];
  const response = await forwardGoals(
    new Request(
      "http://localhost:3000/api/goal-workflow/" +
        path.join("/") +
        "?start_date=2026-10-23&end_date=2026-10-29",
    ),
    path,
    "http://api.invalid",
    async (url, init) => {
      called = { url: String(url), init };
      return Response.json(data);
    },
  );
  assert.equal(response.status, 200);
  assert.match(called.url, /api\/v1\/planning\/cycles\/programs\/pt-cycle/);
  assert.equal(called.init.method, "GET");
  assert.equal(called.init.headers.Authorization, undefined);
  for (const [suffix, method, status] of [
    ["?start_date=x&start_date=y", "GET", 422],
    ["?owner=foreign", "GET", 422],
    ["", "POST", 405],
  ]) {
    let touched = false;
    const result = await forwardGoals(
      new Request("http://localhost:3000/api/goal-workflow/x" + suffix, {
        method,
      }),
      path,
      "http://api.invalid",
      async () => {
        touched = true;
        throw Error("must not call");
      },
    );
    assert.equal(result.status, status);
    assert.equal(touched, false);
  }
});
