import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";
import { load } from "./load-goal-modules.mjs";
const c = load("src/lib/planning-cycles/contracts.ts");
const { forwardGoals } = load("src/lib/planning-goals/proxy.ts");
const require = createRequire(import.meta.url),
  React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { ProgramSummary } = load(
  "src/components/planning-cycles/program-details.tsx",
);
const id = "pt-cycle:" + "a".repeat(64);
function draft() {
  return {
    program_id: "00000000-0000-4000-8000-000000000001",
    mode: "season",
    title: "2027 Kajakos szezon",
    sport: "Kajak",
    start_date: "2026-10-23",
    end_date: "2027-10-22",
    olympic_key: null,
    seasons: [],
    macrocycles: [],
    competitions: [],
    goals: [
      {
        key: "weight_loss",
        target_description: "",
        body_mass: { current_kg: "92,500", target_kg: "85,0" },
      },
    ],
    continued_from: null,
    planning_basis: {
      version: "cycle-planning-basis-v0.1",
      mesocycle_dates: "provisional",
      initial_mesocycle_days: 28,
    },
  };
}
function event(key, day) {
  return {
    key,
    title: "K1 500m",
    start_date: day,
    end_date: day,
    precision: "exact",
    priority: "main",
    status: "planned",
    profile: {
      ...c.emptyProfile("Síkvízi kajak K1"),
      event_type: "sprint",
      distance_value: "500",
    },
  };
}
function season() {
  const p = c.defaultStructure(draft(), "2027-10-22");
  p.competitions = [
    event("summer", "2027-07-14"),
    event("autumn", "2027-09-15"),
  ];
  return p;
}
function pending(p) {
  return {
    schema_version: "cycle-pending-v0.1",
    operation: "programs",
    body: JSON.stringify(p),
  };
}
async function receipt(p, options = {}) {
  const a = {
    artifact_id: id,
    schema_version: "cycle-program-registration-v0.2",
    rules_version: "cycle-creation-rules-v0.2",
    athlete_id: "11111111-1111-4111-8111-111111111111",
    timezone_name: "Europe/Budapest",
    proposal: p,
    periods: [],
    calendar_snapshot: null,
    program_family_id: p.program_id ?? "family",
    created_at: "2026-10-23T08:00:00Z",
    planning_authorized: false,
    workouts_created: false,
    capability_goals_preregistered: false,
    ...options,
  };
  a.content_hash = await c.sha(a);
  return {
    identity_scope: "APPLICATION_DEMO_USER",
    artifact: a,
    durable_available_at: "2026-10-23T08:00:01Z",
    committed: true,
    reused: false,
    planning_authorized: false,
    workouts_created: false,
  };
}

test("two main races and a weight goal reach a complete valid review without a text weight target", () => {
  const p = season();
  assert.deepEqual(c.draftIssues(p, p.end_date), []);
  const normalized = c.normalizeProgram(p);
  assert.deepEqual(normalized.goals[0].body_mass, {
    current_kg: "92.500",
    target_kg: "85.0",
  });
  assert.match(normalized.goals[0].target_description, /92.500 kg/);
  assert.equal(normalized.competitions.length, 2);
});
test("the exact inverted event, macro and mesocycle are identified instead of a generic date error", () => {
  const p = season();
  p.competitions[1].end_date = "2027-09-01";
  assert(
    c
      .draftIssues(p, p.end_date)
      .some(
        (e) =>
          e.step === 2 &&
          e.name === "event.1.start" &&
          e.message.includes("korábbi"),
      ),
  );
  p.competitions[1].end_date = "2027-09-15";
  p.macrocycles[0].mesocycles[2].end_date = "2026-01-01";
  assert(
    c
      .draftIssues(p, p.end_date)
      .some(
        (e) =>
          e.step === 3 &&
          e.name === "meso.0.2.end" &&
          e.message.includes("korábbi"),
      ),
  );
});
test("a start/end inversion is caught before proceeding from the first step", () => {
  const p = draft();
  const e = c.draftIssues(p, "2026-10-01", 1)[0];
  assert.equal(e.step, 1);
  assert.equal(e.name, "end_date");
  assert.match(e.message, /2026-10-01/);
});
for (const days of [14, 21, 35, 42])
  test(`initial mesocycle length ${days} is a provisional suggestion with full coverage`, () => {
    const p = draft();
    p.planning_basis.initial_mesocycle_days = days;
    const result = c.defaultStructure(p, p.end_date);
    assert.equal(
      result.macrocycles[0].mesocycles[0].end_date,
      c.addDays(p.start_date, days - 1),
    );
    assert.equal(result.macrocycles[0].mesocycles.at(-1).end_date, p.end_date);
  });
for (const length of [0, -1, 1.5, Infinity, 367])
  test(`invalid initial length ${length} cannot create an invalid or infinite partition`, () =>
    assert.throws(() => c.mesocycles("2026-10-23", "2027-01-01", "m", length)));
test("shortening or extending a draft boundary couples the neighbour and keeps both race anchors", () => {
  const p = season(),
    snapshot = JSON.stringify(p);
  const short = c.moveDraftBoundary(p, 0, 0, "2026-11-08");
  assert.equal(short.macrocycles[0].mesocycles[1].start_date, "2026-11-09");
  assert.deepEqual(c.draftIssues(short, p.end_date), []);
  const long = c.moveDraftBoundary(short, 0, 0, "2026-11-25");
  assert.equal(long.macrocycles[0].mesocycles[1].start_date, "2026-11-26");
  assert.deepEqual(c.draftIssues(long, p.end_date), []);
  assert.deepEqual(long.competitions, p.competitions);
  assert.equal(long.macrocycles[0].end_date, p.macrocycles[0].end_date);
  assert.equal(JSON.stringify(p), snapshot);
  assert.throws(() =>
    c.moveDraftBoundary(p, 0, 0, p.macrocycles[0].mesocycles[1].end_date),
  );
});
test("weight loss must have both decimal values and a lower target", () => {
  const p = season();
  p.goals[0].body_mass.target_kg = "93";
  assert(
    c.draftIssues(p, p.end_date, 1).some((e) => e.message.includes("kisebb")),
  );
  p.goals[0].body_mass.target_kg = "";
  assert.throws(() => c.normalizeProgram(p));
});
test("missing event requirements are located before preview", () => {
  const p = season();
  delete p.competitions[1].profile;
  assert(
    c.draftIssues(p, p.end_date).some((e) => e.name === "event.1.discipline"),
  );
});
test("an explicitly unknown distance does not become zero", () => {
  const p = event("x", "2027-01-01").profile;
  p.distance_status = "unknown";
  p.distance_value = null;
  p.distance_unit = null;
  assert.equal(c.normalizeProfile(p).distance_value, null);
  assert.equal(c.sprintKeys(p), null);
});
test("qualitative sprint mapping distinguishes 200m from 500/1000m and rejects unsupported events", () => {
  const p = event("x", "2027-01-01").profile;
  const middle = c.sprintKeys(p);
  assert(middle.includes("MUSCULAR_ENDURANCE"));
  assert.deepEqual(
    c.sprintKeys({ ...p, distance_value: "0,5", distance_unit: "km" }),
    middle,
  );
  const short = c.sprintKeys({ ...p, distance_value: "200" });
  assert(!short.includes("MUSCULAR_ENDURANCE"));
  assert(short.includes("VO2_CAPACITY"));
  assert.equal(c.sprintKeys({ ...p, distance_value: "5000" }), null);
  assert.equal(c.sprintKeys({ ...p, discipline: "Kajak szlalom" }), null);
  assert.equal(c.sprintKeys({ ...p, discipline: "Futás" }), null);
  assert.equal(c.sprintKeys({ ...p, event_type: "technical" }), null);
});
test("v0.2 structured receipt and stable pending body are verified with exact values", async () => {
  const p = c.normalizeProgram(season()),
    q = pending(p),
    r = await receipt(p);
  assert.equal(
    (await c.readReceipt(r, q)).artifact.proposal.goals[0].body_mass.current_kg,
    "92.500",
  );
  assert.deepEqual(c.readPending(JSON.stringify(q)), q);
  r.artifact.proposal.goals[0].body_mass.current_kg = "92.5";
  await assert.rejects(() => c.readReceipt(r, q));
});
test("a valid receipt from another operation cannot resolve a pending creation", async () => {
  const p = c.normalizeProgram(season()),
    q = pending(p),
    r = await receipt(p, {
      schema_version: "cycle-competition-revision-v0.2",
      period_dates_changed: false,
    });
  await assert.rejects(() => c.readReceipt(r, q));
});
test("boundary receipts retain exact pending identity and reject an unauthorized workload claim", async () => {
  const p = {
    program_reference: { artifact_id: id, content_hash: "a".repeat(64) },
    revision: 1,
    previous_reference: null,
    competition_reference: { artifact_id: id, content_hash: "a".repeat(64) },
    left_period_id: "left",
    right_period_id: "right",
    new_end_date: "2027-01-03",
    reason: "fatigue",
    observations: "Fáradtság",
    rationale: "Felülvizsgálat",
    review_training_load: true,
  };
  const q = {
    schema_version: "cycle-pending-v0.1",
    operation: "boundary-revisions",
    body: JSON.stringify(p),
  };
  const r = await receipt(p, {
    schema_version: "cycle-mesocycle-boundary-revision-v0.1",
    period_dates_changed: true,
    training_load_replanned: false,
    goal_protocols_rewritten: false,
  });
  assert.deepEqual(c.readPending(JSON.stringify(q)), q);
  await c.readReceipt(r, q);
  r.artifact.training_load_replanned = true;
  r.artifact.content_hash = await c.sha(
    Object.fromEntries(
      Object.entries(r.artifact).filter(([k]) => k !== "content_hash"),
    ),
  );
  await assert.rejects(() => c.readReceipt(r, q));
});
test("closed proxy forwards boundary approvals only through POST with identical bytes", async () => {
  const raw = '{ "new_end_date": "2027-01-03" }';
  let captured;
  const response = await forwardGoals(
    new Request(
      "http://localhost:3000/api/goal-workflow/cycles/boundary-revisions",
      {
        method: "POST",
        headers: {
          Origin: "http://localhost:3000",
          "Content-Type": "application/json",
        },
        body: raw,
      },
    ),
    ["cycles", "boundary-revisions"],
    "http://127.0.0.1:8000",
    async (url, options) => {
      captured = { url: String(url), options };
      return Response.json({ ok: true });
    },
  );
  assert.equal(response.status, 200);
  assert.equal(captured.options.body, raw);
  assert.match(
    captured.url,
    /\/api\/v1\/planning\/cycles\/boundary-revisions$/,
  );
  const denied = await forwardGoals(
    new Request(
      "http://localhost:3000/api/goal-workflow/cycles/boundary-revisions",
    ),
    ["cycles", "boundary-revisions"],
    "http://127.0.0.1:8000",
  );
  assert.equal(denied.status, 405);
});
test("summary renders numerical weight and distance separately and escapes declared text", () => {
  const p = c.normalizeProgram(season());
  p.competitions[0].profile.course_description = '<script>alert("x")</script>';
  const html = renderToStaticMarkup(
    React.createElement(ProgramSummary, {
      value: p,
      labels: { weight_loss: "Testsúlycsökkentés" },
    }),
  );
  assert.match(html, /92.500 kg/);
  assert.match(html, /500 m/);
  assert.match(html, /&lt;script&gt;/);
  assert(!html.includes("<script>"));
  assert.match(html, /iránymutatók/);
});
