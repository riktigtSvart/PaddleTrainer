import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const c = load("src/lib/calendar/contracts.ts");
const { forwardCalendar } = load("src/lib/calendar/proxy.ts");
const theme = load("src/lib/ui/theme.ts");
const { default: TimeGrid } = load("src/components/calendar/time-grid.tsx");
const { stateRows } = load("src/lib/calendar/state.ts");
const OWNER = "11111111-1111-4111-8111-111111111111";
const ID = "22222222-2222-4222-8222-222222222222";
function feed() {
  return {
    schema_version: "calendar-workspace-v0.1",
    athlete_id: OWNER,
    timezone_name: "Europe/Budapest",
    local_today: "2026-10-23",
    start_date: "2026-10-23",
    end_date: "2026-10-23",
    retrieved_at: "2026-10-23T08:00:00+00:00",
    planned: [],
    sessions: [],
    periods: [],
    availability: {
      reference: null,
      days: [],
      carry_windows: [],
      absence_means_unavailable: false,
    },
    has_more: false,
    planning_authorized: false,
    workouts_changed: false,
  };
}
function planned() {
  return {
    id: ID,
    date: "2026-10-23",
    title: "VO2max in name is not a goal",
    sport: "RUNNING",
    status: "PLANNED",
    duration_sec: 2700,
    distance_m: null,
    description: null,
    training_period_id: null,
    planned_start_time: null,
    goal_tag: null,
  };
}
function event(overrides = {}) {
  return {
    key: "planned:" + ID,
    entityId: ID,
    kind: "planned",
    title: "Synthetic",
    sport: "KAYAK",
    date: "2026-10-23",
    start: "2026-10-23T15:30:00Z",
    end: "2026-10-23T16:15:00Z",
    duration: 2700,
    goal: "VO2_CAPACITY",
    goalTag: null,
    ...overrides,
  };
}
test("view ranges retain civil dates across DST and span exactly 1, 7, 28 and 144 days", () => {
  for (const n of [1, 7, 28, 144]) {
    const r = c.viewRange("2026-10-25", n);
    assert.equal(c.dayList(r.start, r.end).length, n);
  }
  assert.equal(c.viewRange("2026-10-25", 7).start, "2026-10-19");
  assert.throws(() => c.viewRange("2026-02-30", 7));
  assert.throws(() => c.dayList("2026-10-24", "2026-10-23"));
});
test("equal wall-clock times align; 90 minutes is exactly twice 45 minutes", () => {
  const a = event(),
    b = event({
      key: "second",
      start: "2026-10-24T15:30:00Z",
      end: "2026-10-24T17:00:00Z",
    });
  const rows = c.segments(
    [a, b],
    "2026-10-23",
    "2026-10-24",
    "Europe/Budapest",
  );
  assert.equal(rows[0].top, 1050);
  assert.equal(rows[1].top, 1050);
  assert.equal(
    rows[1].bottom - rows[1].top,
    2 * (rows[0].bottom - rows[0].top),
  );
});
test("unknown start or duration remains unknown and zero is preserved", () => {
  const x = feed();
  x.planned.push(planned());
  const valid = c.readFeed(x);
  const [row] = c.eventsFrom(valid);
  assert.equal(row.start, null);
  assert.equal(row.end, null);
  assert.equal(row.goal, null);
  assert.equal(
    c.segments([row], x.start_date, x.end_date, x.timezone_name).length,
    0,
  );
  assert.equal(c.formatNumber(0, "kcal"), "0 kcal");
  assert.equal(c.formatNumber(null), "Nincs adat");
});
test("overnight clipping is half-open and preserves both dates", () => {
  const rows = c.segments(
    [event({ start: "2026-10-23T21:30:00Z", end: "2026-10-23T22:30:00Z" })],
    "2026-10-23",
    "2026-10-24",
    "Europe/Budapest",
  );
  assert.deepEqual(
    rows.map((r) => [r.day, r.top, r.bottom]),
    [
      ["2026-10-23", 1410, 1440],
      ["2026-10-24", 0, 30],
    ],
  );
  const midnight = c.segments(
    [event({ start: "2026-10-23T21:30:00Z", end: "2026-10-23T22:00:00Z" })],
    "2026-10-23",
    "2026-10-24",
    "Europe/Budapest",
  );
  assert.equal(midnight.length, 1);
});
test("repeated DST hour is explicitly marked rather than drawn as a negative duration", () => {
  const rows = c.segments(
    [event({ start: "2026-10-25T00:30:00Z", end: "2026-10-25T01:15:00Z" })],
    "2026-10-25",
    "2026-10-25",
    "Europe/Budapest",
  );
  assert.equal(rows.length, 1);
  assert(rows[0].clockChange);
  assert(rows[0].point);
  assert.equal(rows[0].top, 150);
});
test("overlap lanes share the horizontal space and adjacent events reuse it", () => {
  const base = c.segments(
    [event()],
    "2026-10-23",
    "2026-10-23",
    "Europe/Budapest",
  )[0];
  const rows = c.allocateLanes([
    { ...base },
    { ...base, event: event({ key: "b" }), top: 1060, bottom: 1100 },
    { ...base, event: event({ key: "c" }), top: 1100, bottom: 1130 },
  ]);
  assert.equal(rows[0].lanes, 2);
  assert.notEqual(rows[0].lane, rows[1].lane);
  assert.equal(rows[2].lanes, 1);
});
test("an actual goal overrides its linked plan only when an explicit annotation exists", () => {
  const x = feed();
  x.sessions = [
    {
      id: ID,
      started_at: "2026-10-23T15:30:00Z",
      ended_at: null,
      duration_sec: null,
      name: null,
      sport: "KAYAK",
      goal_tag: null,
      linked_goal_tag: { primary_goal: "VO2_CAPACITY" },
    },
  ];
  assert.equal(c.eventsFrom(x)[0].goal, "VO2_CAPACITY");
  x.sessions[0].goal_tag = { primary_goal: null };
  assert.equal(c.eventsFrom(x)[0].goal, null);
});
test("goal color expresses an explicit capability independently of sport or completion", () => {
  assert.equal(c.goalFamily("VO2_CAPACITY"), "vo2");
  assert.equal(c.goalFamily("MAX_STRENGTH"), "strength");
  assert.equal(c.goalFamily("TECHNICAL_SKILL"), "technique");
  assert.equal(c.goalFamily("RECOVERY"), "recovery");
  assert.equal(c.goalFamily(null), "other");
  assert.equal(c.goalFamily("RUNNING"), "other");
});
for (const [name, mutate] of [
  [
    "truncated feed",
    (x) => {
      x.has_more = true;
    },
  ],
  [
    "authority escalation",
    (x) => {
      x.planning_authorized = true;
    },
  ],
  [
    "unknown availability means unavailable",
    (x) => {
      x.availability.absence_means_unavailable = true;
    },
  ],
  [
    "naive planned timestamp",
    (x) => {
      x.planned.push({
        ...planned(),
        planned_start_time: "2026-10-23T17:30:00",
      });
    },
  ],
  [
    "duplicate entity",
    (x) => {
      x.planned.push(planned(), planned());
    },
  ],
  [
    "unsupported goal",
    (x) => {
      x.planned.push({
        ...planned(),
        goal_tag: {
          artifact_id:
            "pt-workout-goal:" + "a".repeat(64) + ":" + "b".repeat(32),
          content_hash: "c".repeat(64),
          primary_goal: "MADE_UP",
        },
      });
    },
  ],
])
  test("rejects " + name, () => {
    const x = feed();
    mutate(x);
    assert.throws(() => c.readFeed(x));
  });
test("server rendering preserves exact event geometry, icon and actual status", () => {
  const x = feed(),
    a = event({ kind: "session", key: "session:" + ID });
  const html = renderToStaticMarkup(
    React.createElement(TimeGrid, {
      feed: x,
      events: [a],
      days: [x.start_date],
      fullDay: false,
      open() {},
      selectDay() {},
      expandHours() {},
    }),
  );
  assert.match(html, /top:71\.875%;height:max\(32px, 4\.6875%\)/);
  assert.match(html, /is-actual/);
  assert.match(html, /pt-goal-vo2/);
  assert.match(html, /teljesített/);
  assert.match(html, /Keret nincs megadva/);
});

function renderedEvents(rows, fullDay = false) {
  const x = feed();
  return renderToStaticMarkup(React.createElement(TimeGrid, {
    feed: x, events: rows, days: [x.start_date], fullDay,
    open() {}, selectDay() {}, expandHours() {},
  }));
}
for (const kind of ["planned", "session"]) {
  for (const minutes of [1, 20])
    test(`${kind} ${minutes} minutes keeps its anchor and exact duration with a readable minimum`, () => {
      const row = event({ kind, duration: minutes * 60,
        start: "2026-10-23T06:00:00Z",
        end: `2026-10-23T06:${String(minutes).padStart(2, "0")}:00Z` });
      const html = renderedEvents([row]);
      assert.match(html, /top:12\.5%;height:max\(32px,/);
      assert.match(html, /is-enlarged/);
      assert.match(html, /pt-event-true-end/);
      assert(html.includes(`${minutes} p`));
      assert.equal(row.duration, minutes * 60);
    });
}
test("unknown duration is readable without an invented endpoint or duration", () => {
  const html = renderedEvents([event({ end: null, duration: null })]);
  assert.match(html, /height:32px/);
  assert.match(html, /is-point/);
  assert.match(html, /végidő nélkül/);
  assert.match(html, /Nincs adat/);
  assert.doesNotMatch(html, /class="pt-event-true-end"/);
});
test("zero duration remains zero inside a readable marker", () => {
  const html = renderedEvents([event({ end: "2026-10-23T15:30:00Z", duration: 0 })]);
  assert.match(html, /height:32px/);
  assert.match(html, /is-point/);
  assert.match(html, /0 p/);
});
test("long events retain proportional heights", () => {
  const html = renderedEvents([
    event({ key: "ninety", start: "2026-10-23T06:00:00Z", end: "2026-10-23T07:30:00Z", duration: 5400 }),
    event({ key: "two-hours", start: "2026-10-23T09:00:00Z", end: "2026-10-23T11:00:00Z", duration: 7200 }),
  ]);
  assert.match(html, /height:max\(32px, 9\.375%\)/);
  assert.match(html, /height:max\(32px, 12\.5%\)/);
});
test("minimum-height collisions use separate lanes without changing actual time spans", () => {
  const base = c.segments([event()], "2026-10-23", "2026-10-23", "Europe/Budapest")[0];
  const input = [
    { ...base, top: 480, bottom: 500 },
    { ...base, event: event({ key: "next" }), top: 500, bottom: 520 },
    { ...base, event: event({ key: "later" }), top: 600, bottom: 620 },
  ];
  const original = structuredClone(input);
  const rows = c.allocateLanes(input, c.MIN_ACTIVITY_HEIGHT / 38 * 60, 360);
  assert.equal(rows[0].lanes, 2);
  assert.notEqual(rows[0].lane, rows[1].lane);
  assert.equal(rows[2].lanes, 1);
  assert.deepEqual(input, original);
  assert.deepEqual(rows.map((r) => [r.top, r.bottom]), [[480, 500], [500, 520], [600, 620]]);
});
test("a clipped early event reserves its whole visible minimum for collision layout", () => {
  const base = c.segments([event()], "2026-10-23", "2026-10-23", "Europe/Budapest")[0];
  const rows = c.allocateLanes([
    { ...base, top: 350, bottom: 370 },
    { ...base, event: event({ key: "next" }), top: 390, bottom: 400 },
  ], c.MIN_ACTIVITY_HEIGHT / 38 * 60, 360);
  assert.equal(rows[0].lanes, 2);
  assert.notEqual(rows[0].lane, rows[1].lane);
});
test("an availability window keeps its actual proportional height", () => {
  const html = renderedEvents([event({ kind: "availability", start: "2026-10-23T06:00:00Z",
    end: "2026-10-23T06:20:00Z", duration: 1200 })]);
  assert.match(html, /is-available/);
  const eventStyle = html.match(/class="pt-event[^\"]*" style="([^\"]+)"/)[1];
  assert.doesNotMatch(eventStyle, /height:32px/);
  assert.doesNotMatch(html, /is-enlarged/);
});
test("the last minute stays at its real anchor and retains the readable minimum", () => {
  const html = renderedEvents([event({ start: "2026-10-23T21:59:00Z",
    end: "2026-10-23T22:00:00Z", duration: 60 })], true);
  assert.match(html, /top:99\.93055555555556%;height:max\(32px,/);
  assert.match(html, /--pt-min-event-height:32px/);
});
for (const [mode, systemDark, result] of [
  ["dark", false, "dark"],
  ["light", true, "light"],
  ["system", true, "dark"],
  ["system", false, "light"],
])
  test(`theme ${mode}, system dark=${systemDark}`, () => {
    assert.equal(theme.resolvedTheme(mode, systemDark), result);
  });
test("theme bootstrap handles unavailable storage and rejects arbitrary stored strings", () => {
  for (const value of [null, "<script>", "light", "system"]) {
    const document = { documentElement: { dataset: {}, style: {} } };
    runInNewContext(theme.themeBootstrap, {
      document,
      localStorage: { getItem: () => value },
      matchMedia: () => ({ matches: false }),
    });
    assert.equal(
      document.documentElement.dataset.theme,
      ["light", "system"].includes(value) ? "light" : "dark",
    );
  }
  const document = { documentElement: { dataset: {}, style: {} } };
  runInNewContext(theme.themeBootstrap, {
    document,
    localStorage: {
      getItem() {
        throw new Error("blocked");
      },
    },
  });
  assert.equal(document.documentElement.dataset.theme, "dark");
});
function request(path, method = "GET", body, headers = {}) {
  return new Request("http://localhost:3000/api/calendar/" + path, {
    method,
    headers: {
      ...(method === "POST"
        ? {
            Origin: "http://localhost:3000",
            "Content-Type": "application/json",
          }
        : {}),
      ...headers,
    },
    ...(body === undefined ? {} : { body }),
  });
}
test("proxy forwards only the bounded calendar endpoint and unchanged write bytes", async () => {
  let calls = 0;
  const send = async (url, init) => {
    calls++;
    assert.equal(
      url.href,
      "http://api.internal/api/v1/planning/calendar/goals",
    );
    assert.equal(init.body, '{"x":"ő"}');
    assert.equal(init.redirect, "error");
    assert(!("Authorization" in init.headers));
    return Response.json({ ok: true });
  };
  const result = await forwardCalendar(
    request("goals", "POST", '{"x":"ő"}', {
      Authorization: "do-not-forward",
      Cookie: "also-do-not-forward",
    }),
    ["goals"],
    "http://api.internal",
    send,
  );
  assert.equal(result.status, 200);
  assert.equal(calls, 1);
  assert.equal(result.headers.get("Cache-Control"), "no-store");
});
for (const [path, method, headers, status] of [
  ["evil", "GET", {}, 404],
  ["goals", "GET", {}, 405],
  ["feed", "POST", {}, 405],
  ["goals", "POST", { Origin: "http://evil.invalid" }, 403],
  ["goals", "POST", { "Content-Type": "text/plain" }, 415],
  ["feed?start_date=a&start_date=b", "GET", {}, 422],
  ["feed?url=http://evil.invalid", "GET", {}, 422],
])
  test(`proxy refuses ${method} ${path}: ${status}`, async () => {
    const r = await forwardCalendar(
      request(path, method, method === "POST" ? "{}" : undefined, headers),
      [path.split("?")[0]],
      "http://api.internal",
      async () => {
        throw new Error("must not forward");
      },
    );
    assert.equal(r.status, status);
  });
test("proxy enforces actual body bytes, uses incoming Host, and sanitizes failures", async () => {
  const tooLarge = await forwardCalendar(
    request("goals", "POST", "ő".repeat(9000), { "Content-Length": "1" }),
    ["goals"],
    "http://api.internal",
    () => {
      throw new Error("must not forward");
    },
  );
  assert.equal(tooLarge.status, 413);
  const incoming = new Request("http://internal:3000/api/calendar/goals", {
    method: "POST",
    headers: {
      Host: "localhost:3000",
      Origin: "http://localhost:3000",
      "Content-Type": "application/json",
    },
    body: "{}",
  });
  assert.equal(
    (
      await forwardCalendar(
        incoming,
        ["goals"],
        "http://api.internal",
        async () => Response.json({}),
      )
    ).status,
    200,
  );
  assert.equal(
    (
      await forwardCalendar(
        request("feed"),
        ["feed"],
        "http://api.internal",
        async () => new Response("internal details"),
      )
    ).status,
    502,
  );
});
test("Python canonical goal receipt roundtrips nested parent hashes and rejects tampering", async () => {
  const fixture = JSON.parse(
    readFileSync(
      new URL("./fixtures/calendar-goal-receipt.json", import.meta.url),
    ),
  );
  await c.verifyGoalReceipt(fixture.receipt, fixture.body, fixture.owner);
  for (const mutate of [
    (r) => {
      r.committed = false;
    },
    (r) => {
      r.artifact.proposal.primary_goal = "MAX_STRENGTH";
    },
    (r) => {
      r.artifact.proposal.previous_reference.content_hash = "0".repeat(64);
    },
    (r) => {
      r.artifact.workouts_changed = true;
    },
  ]) {
    const r = structuredClone(fixture.receipt);
    mutate(r);
    await assert.rejects(c.verifyGoalReceipt(r, fixture.body, fixture.owner));
  }
});
test("state summary retains a manual correction and marks its original source", () => {
  const raw = {
    artifact_id: "raw",
    metric: "daily_steps",
    value: "0",
    unit: "count",
    provider: "POLAR",
    method: "device_estimate",
    aggregation: "total",
    start_date: "2026-10-23",
    end_date: "2026-10-23",
    coverage: { completeness: "sampled" },
  };
  const profile = {
    kind: "profile",
    imported_observations: [raw],
    proposal: {
      data: {
        manual_observations: [
          {
            observation_id: ID,
            metric: "daily_steps",
            value: "4200",
            start_date: "2026-10-23",
            end_date: "2026-10-23",
            method: "self_report",
            aggregation: "total",
            supersedes_candidate_id: "raw",
          },
        ],
      },
    },
  };
  const rows = stateRows([raw], profile, "2026-10-23");
  assert.equal(rows.length, 2);
  assert.equal(rows[0].value, "0");
  assert(rows[0].replaced && rows[0].partial);
  assert.equal(rows[1].value, "4200");
  assert.equal(rows[1].provider, "Kézi bevitel");
});
test("state summary does not sum different devices or carry another day forward", () => {
  const raw = {
    artifact_id: "one",
    metric: "daily_steps",
    value: "100",
    unit: "count",
    provider: "POLAR",
    method: "device_estimate",
    aggregation: "total",
    start_date: "2026-10-23",
    end_date: "2026-10-23",
    coverage: {},
  };
  assert.equal(
    stateRows(
      [raw, { ...raw, artifact_id: "two", value: "200" }],
      null,
      "2026-10-23",
    ).length,
    2,
  );
  assert.equal(stateRows([raw], null, "2026-10-24").length, 0);
});
