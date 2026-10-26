import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";
import { load } from "./load-goal-modules.mjs";
const c = load("src/lib/athlete-setup/contracts.ts"),
  cycles = load("src/lib/planning-cycles/contracts.ts");
const client = load("src/lib/athlete-setup/client.ts"),
  { forwardGoals } = load("src/lib/planning-goals/proxy.ts");
const { newGoal, default: GoalEditor } = load(
  "src/components/planning-cycles/goal-editor.tsx",
);
const require = createRequire(import.meta.url),
  React = require("react"),
  { renderToStaticMarkup } = require("react-dom/server");
const owner = "11111111-1111-4111-8111-111111111111";
function program(goal) {
  return {
    program_id: owner,
    mode: "recreation",
    title: "Mozgás",
    sport: "Futás",
    start_date: "2026-10-23",
    end_date: null,
    olympic_key: null,
    seasons: [],
    macrocycles: [],
    competitions: [],
    goals: [goal],
    continued_from: null,
    planning_basis: {
      version: "cycle-planning-basis-v0.1",
      mesocycle_dates: "provisional",
      initial_mesocycle_days: 28,
    },
  };
}
function pending(operation = "profiles") {
  return {
    schema_version: "athlete-pending-v0.1",
    operation,
    body: JSON.stringify({
      request_id: owner,
      previous_reference: null,
      data: c.emptyProfile(),
    }),
  };
}
async function receipt(p = pending(), extra = {}) {
  const artifact = {
    schema_version: "athlete-setup-v0.1",
    artifact_id: "pt-athlete:" + "a".repeat(64),
    athlete_id: owner,
    kind:
      p.operation === "profiles"
        ? "profile"
        : p.operation === "availability"
          ? "availability"
          : "polar_import",
    proposal: JSON.parse(p.body),
    created_at: "2026-10-23T10:00:00Z",
    planning_authorized: false,
    workouts_created: false,
    ...extra,
  };
  artifact.content_hash = await cycles.sha(artifact);
  return {
    identity_scope: "APPLICATION_DEMO_USER",
    artifact,
    durable_available_at: "2026-10-23T10:00:01Z",
    committed: true,
    reused: false,
    planning_authorized: false,
    workouts_created: false,
  };
}

test("maintenance needs only current weight, keeps decimal digits and no target input", () => {
  const g = newGoal("weight_maintenance");
  g.body_mass.current_kg = "72,500";
  const p = program(g),
    normalized = cycles.normalizeProgram(p);
  assert.deepEqual(normalized.goals[0].body_mass, { current_kg: "72.500" });
  assert(!cycles.draftIssues(p, "2027-01-14", 1).length);
  const html = renderToStaticMarkup(
    React.createElement(GoalEditor, { value: g, onChange() {} }),
  );
  assert.match(html, /Jelenlegi testsúly/);
  assert(!html.includes("Céltestsúly (kg)"));
});
test("weight loss still needs a lower target and cannot be combined with maintenance", () => {
  const g = newGoal("weight_loss");
  g.body_mass.current_kg = "80";
  g.body_mass.target_kg = "85";
  const p = program(g);
  assert(
    cycles
      .draftIssues(p, "2027-01-14", 1)
      .some((i) => i.message.includes("kisebb")),
  );
  p.goals.push(newGoal("weight_maintenance"));
  assert(
    cycles
      .draftIssues(p, "2027-01-14", 1)
      .some((i) => i.message.includes("egymást követő")),
  );
});
for (const key of [
  "performance",
  "aerobic_fitness",
  "strength",
  "regular_activity",
  "wellbeing",
  "mobility",
])
  test(`structured goal requires no prose: ${key}`, () => {
    const p = program(newGoal(key));
    assert(!cycles.draftIssues(p, "2027-01-14", 1).length);
    assert(cycles.normalizeProgram(p).goals[0].target_description.length);
  });
test("performance defaults to main races and keeps an explicit narrower choice", () => {
  const p = program(newGoal("performance"));
  p.competitions = [
    { key: "main", title: "Főverseny", priority: "main", status: "planned" },
    {
      key: "support",
      title: "Köztes",
      priority: "supporting",
      status: "planned",
    },
  ];
  assert.deepEqual(cycles.normalizeProgram(p).goals[0].details.event_keys, [
    "main",
  ]);
  p.goals[0].details.event_keys = ["support"];
  assert.deepEqual(cycles.normalizeProgram(p).goals[0].details.event_keys, [
    "support",
  ]);
});
test("unknown intake values remain unknown while manual zero remains zero", () => {
  const p = c.emptyProfile();
  assert.equal(p.typical_days_per_week, null);
  assert.equal(p.constraint_status, "unknown");
  assert.equal(p.sport_history_status, "unknown");
  p.manual_observations = [
    {
      observation_id: owner,
      metric: "daily_steps",
      value: "0",
      start_date: "2026-10-22",
      end_date: "2026-10-22",
      method: "self_report",
      sport: "",
      protocol: "",
      conditions: "",
      supersedes_candidate_id: null,
    },
  ];
  assert.equal(
    c.normalizeProfile(p, "2026-10-23").manual_observations[0].value,
    "0",
  );
});
test("calendar preserves actual dates across DST, filled overlap and unknown extensions", () => {
  let a = c.resizeCalendar(null, "2026-10-23", "2026-11-05", "Europe/Budapest");
  assert.equal(a.days.length, 14);
  assert(a.days.every((d) => d.status === "unknown"));
  a.days[0] = {
    ...a.days[0],
    status: "available",
    windows: [
      {
        ...c.newWindow(),
        start_time: "06:00",
        end_time: "07:00",
        max_minutes: 45,
      },
      {
        ...c.newWindow(),
        start_time: "18:00",
        end_time: "19:00",
        max_minutes: 60,
      },
    ],
  };
  const b = c.resizeCalendar(a, "2026-10-23", "2026-11-19", a.timezone_name);
  assert.equal(b.days[0].windows.length, 2);
  assert.equal(b.days[27].status, "unknown");
  c.validateCalendar(b);
});
test("copying a specific day changes only selected dates and never mutates the original", () => {
  const a = c.resizeCalendar(
    null,
    "2026-10-23",
    "2026-10-26",
    "Europe/Budapest",
  );
  a.days[0].status = "unavailable";
  const before = JSON.stringify(a),
    b = c.copyDay(a, "2026-10-23", ["2026-10-25"]);
  assert.equal(b.days[2].status, "unavailable");
  assert.equal(b.days[1].status, "unknown");
  assert.equal(JSON.stringify(a), before);
});
for (const [first, last] of [
  ["2026-02-30", "2026-03-01"],
  ["2026-10-24", "2026-10-23"],
  ["2026-01-01", "2027-01-02"],
])
  test(`invalid calendar range: ${first}..${last}`, () =>
    assert.throws(() => c.dates(first, last)));
test("a full mesocycle can be chosen without changing its dates", () => {
  const a = c.resizeCalendar(
    null,
    "2026-10-23",
    "2026-12-03",
    "Europe/Budapest",
    owner,
  );
  assert.equal(a.days.length, 42);
  assert.equal(a.mesocycle_id, owner);
});
test("an available day with no session window and a window without a duration are rejected", () => {
  const a = c.resizeCalendar(
    null,
    "2026-10-23",
    "2026-10-23",
    "Europe/Budapest",
  );
  a.days[0].status = "available";
  assert.throws(() => c.validateCalendar(a));
  a.days[0].windows = [c.newWindow()];
  assert.throws(() => c.validateCalendar(a));
});
test("pending profile and import queue survive remount byte for byte and retain owner", () => {
  const q = {
    schema_version: "athlete-queue-v0.1",
    athlete_id: owner,
    items: [
      pending(),
      {
        schema_version: "athlete-pending-v0.1",
        operation: "polar-imports",
        body: JSON.stringify({
          request_id: owner,
          day: "2026-10-20",
          domain: "activity",
        }),
      },
    ],
  };
  assert.deepEqual(c.readQueue(JSON.stringify(q)), q);
  assert.equal(c.readQueue(JSON.stringify(q)).items[0].body, q.items[0].body);
});
test("only the exact committed matching supported receipt resolves a pending write", async () => {
  const p = pending(),
    r = await receipt(p);
  await c.readReceipt(r, p);
  for (const change of [
    { committed: false },
    { planning_authorized: true },
    { workouts_created: true },
    { durable_available_at: "invalid" },
  ])
    await assert.rejects(() => c.readReceipt({ ...r, ...change }, p));
  await assert.rejects(() =>
    c.readReceipt(
      { ...r, artifact: { ...r.artifact, schema_version: "future" } },
      p,
    ),
  );
  await assert.rejects(async () =>
    c.readReceipt(
      await receipt(p, {
        proposal: { ...JSON.parse(p.body), request_id: "different" },
      }),
      p,
    ),
  );
});
test("nested source hashes and actual values are covered by the receipt hash", async () => {
  const r = await receipt(pending(), {
    imported_observations: [{ content_hash: "nested", value: "3" }],
  });
  r.artifact.imported_observations[0].value = "5";
  await assert.rejects(() => c.readReceipt(r));
});
test("POST retry uses identical stored bytes and a malformed receipt stays unresolved", async () => {
  const old = globalThis.fetch,
    p = pending(),
    seen = [];
  try {
    globalThis.fetch = async (_url, init) => {
      seen.push(init.body);
      return Response.json(await receipt(p));
    };
    await client.send(p);
    await client.send(c.readPending(JSON.stringify(p)));
    assert.deepEqual(seen, [p.body, p.body]);
    globalThis.fetch = async () => Response.json({ committed: true });
    await assert.rejects(() => client.send(p));
  } finally {
    globalThis.fetch = old;
  }
});
for (const [method, path] of [
  ["GET", "context"],
  ["GET", "history"],
  ["POST", "profiles"],
  ["POST", "availability"],
  ["POST", "availability/preview"],
  ["POST", "polar-imports"],
  ["GET", "profiles/pt-athlete:" + "a".repeat(64)],
])
  test(`closed proxy allows athlete route ${method} ${path}`, async () => {
    let seen;
    const body = method === "POST" ? '{"exact":"bytes"}' : undefined;
    const req = new Request(
      "http://localhost:3000/api/goal-workflow/athlete/" + path,
      {
        method,
        body,
        headers: {
          Origin: "http://localhost:3000",
          "Content-Type": "application/json",
          Cookie: "never-forward",
        },
      },
    );
    const response = await forwardGoals(
      req,
      ["athlete", ...path.split("/")],
      "http://127.0.0.1:8000",
      async (url, init) => {
        seen = { url: String(url), init };
        return Response.json({ ok: true });
      },
    );
    assert.equal(response.status, 200);
    assert.equal(
      seen.url,
      "http://127.0.0.1:8000/api/v1/planning/athlete/" +
        path.split("/").map(encodeURIComponent).join("/"),
    );
    assert.equal(seen.init.body, body);
    assert(!seen.init.headers.Cookie);
  });
for (const [method, path, status] of [
  ["GET", "profiles", 405],
  ["GET", "polar-imports", 405],
  ["POST", "context", 405],
  ["POST", "history", 405],
  ["GET", "availability/preview", 405],
  ["GET", "../polar", 404],
  ["GET", "profiles/evil", 404],
  ["DELETE", "availability", 405],
])
  test(`closed proxy refuses athlete route ${method} ${path}`, async () => {
    const response = await forwardGoals(
      new Request("http://localhost:3000/api/goal-workflow/athlete/x", {
        method,
        headers: { Origin: "http://localhost:3000" },
      }),
      ["athlete", ...path.split("/")],
      "http://backend",
      async () => {
        throw Error("must not forward");
      },
    );
    assert.equal(response.status, status);
  });
test("athlete history proxy forwards only unique date range query fields", async () => {
  for (const query of [
    "start_date=2026-10-01&start_date=2026-10-02",
    "url=http://evil.invalid",
  ]) {
    const response = await forwardGoals(
      new Request(
        "http://localhost:3000/api/goal-workflow/athlete/history?" + query,
      ),
      ["athlete", "history"],
      "http://backend",
      async () => {
        throw Error("must not forward");
      },
    );
    assert.equal(response.status, 422);
  }
});

// Frozen receipt produced by the Python domain, including an actual step coverage value.
const pythonReceipt = {
  identity_scope: "APPLICATION_DEMO_USER",
  artifact: {
    schema_version: "athlete-setup-v0.1",
    artifact_id:
      "pt-athlete:93e6609873104f34db0b81fb6352ed7fd16bfc0811f2f989735edb1159c26f53",
    athlete_id: "11111111-1111-4111-8111-111111111111",
    kind: "profile",
    revision: 1,
    created_at: "2026-10-23T10:00:01+00:00",
    timezone_name: "Europe/Budapest",
    proposal: {
      request_id: "11111111-1111-4111-8111-111111111111",
      previous_reference: null,
      data: {
        birth_date: "1982-05-30",
        sex_reference: "unknown",
        competition_category: "",
        target_sport: "Futás",
        sport_history_status: "none",
        sport_history: [],
        constraint_status: "none_known",
        constraints: [],
        participation: "unrestricted",
        interruption: "unknown",
        last_training_date: null,
        typical_days_per_week: null,
        typical_minutes_per_week: null,
        resources: [],
        accessibility_needs: "",
        recovery_notes: "",
        manual_observations: [],
        source_window: { start_date: "2026-10-20", end_date: "2026-10-20" },
        source_selections: [
          {
            artifact_id:
              "pt-source:1efdb0900f167dfa2d6cbd3b1ebd0f9632f06b48a2426904ecdb3a83203d4e06",
            content_hash:
              "c0dbfb703177bbf522fcd20f3977a86125e7a0a44a38d2a374fce1b6ab9f5af5",
          },
        ],
      },
    },
    planning_authorized: false,
    workouts_created: false,
    review: {
      policy_version: "athlete-intake-review-policy-v0.1",
      evaluated_on: "2026-10-23",
      age_years: 44,
      age_path: "adult",
      global_entry_gate: "OPEN",
      participation_status: "READY",
      entry_mode: "NORMAL_START",
      reasons: [],
      clinical_clearance: false,
      weight_change_requires_review: false,
      constraints: [],
      accessibility_needs: "",
    },
    imported_observations: [
      {
        normalizer_version: "athlete-history-candidates-v0.1",
        aggregation: "total",
        metric: "daily_steps",
        value: "3",
        unit: "count",
        start_date: "2026-10-20",
        end_date: "2026-10-20",
        provider: "POLAR",
        source_id: "synthetic-raw:one",
        source_content_hash:
          "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        received_at: "2026-10-23T10:00:00+00:00",
        method: "device_estimate",
        logical_key: "POLAR:activity:2026-10-20:watch:daily_steps",
        sport: "",
        protocol: "",
        coverage: {
          completeness: "sampled",
          observed_minutes: "3",
          devices_must_not_be_summed: true,
        },
        artifact_id:
          "pt-source:1efdb0900f167dfa2d6cbd3b1ebd0f9632f06b48a2426904ecdb3a83203d4e06",
        content_hash:
          "c0dbfb703177bbf522fcd20f3977a86125e7a0a44a38d2a374fce1b6ab9f5af5",
      },
    ],
    content_hash:
      "9cfe3bc5b086bebd9f7866a717fbaba4745f25cd44670dd9a98c0dfc7153a179",
  },
  durable_available_at: "2026-10-23T10:00:02+00:00",
  committed: true,
  reused: false,
  planning_authorized: false,
  workouts_created: false,
};
test("a Python-produced profile receipt with imported step coverage has the same browser hash", async () => {
  await c.readReceipt(pythonReceipt, {
    schema_version: "athlete-pending-v0.1",
    operation: "profiles",
    body: JSON.stringify(pythonReceipt.artifact.proposal),
  });
  const source = pythonReceipt.artifact.imported_observations[0];
  const { content_hash, ...body } = source;
  assert.equal(await cycles.sha(body), content_hash);
  assert.equal(source.coverage.observed_minutes, "3");
});

test("a cancelled target remains visible as historical intent with an explicit review reason", () => {
  const { ProgramSummary } = load(
    "src/components/planning-cycles/program-details.tsx",
  );
  const g = newGoal("performance");
  g.details.event_keys = ["race"];
  const p = program(g);
  p.competitions = [
    {
      key: "race",
      title: "Elmaradt verseny",
      status: "cancelled",
      priority: "main",
      start_date: "2027-01-01",
      end_date: "2027-01-01",
      precision: "exact",
    },
  ];
  const html = renderToStaticMarkup(
    React.createElement(ProgramSummary, {
      value: p,
      labels: { performance: "Versenyteljesítmény" },
    }),
  );
  assert.match(html, /célfelülvizsgálat szükséges/);
  assert.match(html, /Elmaradt verseny/);
});
