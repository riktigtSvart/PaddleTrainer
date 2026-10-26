import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const c = load("src/lib/calendar/contracts.ts");
const { default: TimeGrid, eventLabel } = load("src/components/calendar/time-grid.tsx");
const { default: PeriodGrid } = load("src/components/calendar/period-grid.tsx");
const PLAN = "22222222-2222-4222-8222-222222222222";
const ACTUAL = "33333333-3333-4333-8333-333333333333";
function feed() {
  return {
    schema_version: "calendar-workspace-v0.1",
    athlete_id: "11111111-1111-4111-8111-111111111111",
    timezone_name: "Europe/Budapest",
    local_today: "2026-10-26",
    start_date: "2026-10-26",
    end_date: "2026-10-26",
    retrieved_at: "2026-10-26T08:00:00Z",
    planned: [{
      id: PLAN, date: "2026-10-26", planned_start_time: "2026-10-26T05:00:00Z",
      title: "Reggeli terv", sport: "KAYAK", duration_sec: 1800,
      distance_m: 6000, status: "PLANNED", description: null,
      training_period_id: null, goal_tag: null,
    }],
    sessions: [{
      id: ACTUAL, started_at: "2026-10-26T05:55:00Z", ended_at: "2026-10-26T06:28:00Z",
      name: "Reggeli teljesítés", sport: "KAYAK", duration_sec: 1980,
      distance_m: 6100, calories: 0, avg_hr: null, max_hr: null,
      avg_speed: null, max_speed: null, avg_power: null, max_power: null,
      avg_cadence: null, max_cadence: null, cardio_load: null,
      perceived_load: null, rpe: null, external_provider: "POLAR",
      external_id: "synthetic", planned_workout_id: PLAN,
      goal_tag: null, linked_goal_tag: null,
    }],
    periods: [], availability: {
      reference: null, days: [], carry_windows: [], absence_means_unavailable: false,
    },
    has_more: false, planning_authorized: false, workouts_changed: false,
  };
}
function entries(x) { return c.calendarEntries(c.eventsFrom(x)); }
function render(x, span = 1) {
  const days = c.dayList(x.start_date, c.addDays(x.start_date, span - 1));
  const props = { feed: x, events: entries(x), days, open() {}, selectDay() {} };
  return renderToStaticMarkup(React.createElement(span <= 7 ? TimeGrid : PeriodGrid,
    span <= 7 ? { ...props, fullDay: false, expandHours() {} }
      : { ...props, selected: x.start_date, overview: span === 144 }));
}

test("an exact stored plan reference yields one completion entry without mutating source events", () => {
  const x = c.readFeed(feed()), original = structuredClone(x);
  const source = c.eventsFrom(x), before = structuredClone(source);
  const rows = c.calendarEntries(source);
  assert.equal(source.length, 2);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].key, "session:" + ACTUAL);
  assert.equal(rows[0].pairedPlan.key, "planned:" + PLAN);
  assert.equal(rows[0].linkedPlanId, PLAN);
  assert.deepEqual(source, before);
  assert.deepEqual(x, original);
  assert.deepEqual(c.calendarEntries(rows), rows);
});
test("a combined entry keeps actual geometry and both original durations", () => {
  const [row] = entries(feed());
  const [segment] = c.segments([row], "2026-10-26", "2026-10-26", "Europe/Budapest");
  assert.equal(segment.top, 415);
  assert.equal(segment.bottom, 448);
  assert.equal(row.duration, 1980);
  assert.equal(row.pairedPlan.duration, 1800);
  assert.equal(row.pairedPlan.start, "2026-10-26T05:00:00Z");
  assert.match(eventLabel(row, "Europe/Budapest"), /06:55–07:28.*tervhez párosított teljesítés.*33 p/);
  assert.match(eventLabel(row, "Europe/Budapest"), /Terv: Reggeli terv.*06:00.*30 p/);
});
for (const span of [1, 7])
  test(`${span}-day clock view draws one readable paired card, at the actual start`, () => {
    const html = render(feed(), span);
    assert.equal((html.match(/class="pt-event pt-goal-/g) ?? []).length, 1);
    const [, top] = html.match(/class="pt-event [^"]*" style="top:([\d.]+)%;height:max\(32px,/) ?? [];
    assert(Math.abs(Number(top) - 55 / 960 * 100) < 1e-10);
    assert.equal((html.match(/class="pt-event-status"/g) ?? []).length, 1);
    assert.match(html, /tervhez párosított teljesítés/);
  });
test("the 28-day view renders one paired entry with both values in its accessible label", () => {
  const html = render(feed(), 28);
  assert.equal((html.match(/class="pt-month-event /g) ?? []).length, 1);
  assert.match(html, /tervhez párosított teljesítés.*33 p.*Terv: Reggeli terv.*30 p/);
  assert.match(html, /pt-event-status/);
});
test("the 144-day view counts a linked pair once", () => {
  const html = render(feed(), 144);
  assert.match(html, /okt\. 26\., H · 1 edzés\/terv/);
  assert.equal((html.match(/<b class="pt-goal-/g) ?? []).length, 1);
});
test("identical timestamps, names and sports never imply a link", () => {
  const x = feed();
  Object.assign(x.sessions[0], {
    planned_workout_id: null, name: x.planned[0].title,
    started_at: x.planned[0].planned_start_time,
  });
  assert.equal(entries(x).length, 2);
  assert.equal((render(x).match(/class="pt-event pt-goal-/g) ?? []).length, 2);
  assert.equal(entries(x).find((e) => e.kind === "session").pairedPlan, undefined);
});
test("a reference to a different plan never suppresses a similarly named visible plan", () => {
  const x = feed();
  x.sessions[0].planned_workout_id = "44444444-4444-4444-8444-444444444444";
  assert.equal(entries(x).length, 2);
  assert.equal(entries(x).find((e) => e.kind === "session").pairedPlan, undefined);
});
test("a plan outside the feed retains an honest reference without invented plan data", () => {
  const x = feed();
  x.planned = [];
  const [row] = entries(x);
  assert.equal(row.linkedPlanId, PLAN);
  assert.equal(row.pairedPlan, undefined);
  assert.match(eventLabel(row, x.timezone_name), /tervhez párosított teljesítés/);
  assert.doesNotMatch(eventLabel(row, x.timezone_name), /Terv:/);
});
test("several completions of one plan remain separate measured sessions", () => {
  const x = feed();
  x.sessions.push({ ...x.sessions[0], id: "44444444-4444-4444-8444-444444444444",
    name: "Második rész", started_at: "2026-10-26T06:30:00Z", ended_at: "2026-10-26T06:40:00Z",
    duration_sec: 600 });
  const rows = entries(x);
  assert.equal(rows.length, 2);
  assert(rows.every((e) => e.kind === "session" && e.pairedPlan.entityId === PLAN));
  assert.deepEqual(rows.map((e) => e.duration), [1980, 600]);
});
test("a completion on another day keeps that day and exposes the original plan date", () => {
  const x = feed();
  x.planned[0].planned_start_time = "2026-10-25T05:00:00Z";
  x.planned[0].date = "2026-10-25";
  const [row] = entries(x);
  assert.equal(row.date, "2026-10-26");
  assert.equal(row.pairedPlan.date, "2026-10-25");
  assert.match(eventLabel(row, x.timezone_name), /Terv: Reggeli terv · okt\. 25\. 06:00/);
});
test("an overnight completion keeps its real two-day segments without duplicating its plan", () => {
  const x = feed();
  Object.assign(x.sessions[0], { started_at: "2026-10-26T22:50:00Z",
    ended_at: "2026-10-26T23:10:00Z", duration_sec: 1200 });
  assert.deepEqual(c.segments(entries(x), "2026-10-26", "2026-10-27", x.timezone_name)
    .map((s) => [s.day, s.top, s.bottom]),
  [["2026-10-26", 1430, 1440], ["2026-10-27", 0, 10]]);
});
test("a linked plan with an unknown start is represented once without an extra unscheduled card", () => {
  const x = feed();
  x.planned[0].planned_start_time = null;
  const html = render(x);
  assert.equal(entries(x).length, 1);
  assert.match(eventLabel(entries(x)[0], x.timezone_name), /Terv: Reggeli terv.*időpont nélkül/);
  assert.match(html, /class="pt-unscheduled-day"><\/div>/);
});
test("unknown and zero plan durations remain distinct in combined labels", () => {
  const x = feed();
  x.planned[0].duration_sec = null;
  assert.match(eventLabel(entries(x)[0], x.timezone_name), /33 p.*Terv: Reggeli terv.*Nincs adat/);
  x.planned[0].duration_sec = 0;
  assert.match(eventLabel(entries(x)[0], x.timezone_name), /33 p.*Terv: Reggeli terv.*0 p/);
});
test("an unknown actual duration never inherits the planned duration or endpoint", () => {
  const x = feed();
  x.sessions[0].ended_at = null;
  x.sessions[0].duration_sec = null;
  const [row] = entries(x);
  assert.equal(row.duration, null);
  assert.equal(row.end, null);
  assert.match(render(x), /height:32px/);
  assert.match(eventLabel(row, x.timezone_name), /végidő nélkül.*Nincs adat.*Terv: Reggeli terv.*30 p/);
});
test("a completion's explicit goal remains authoritative over the attached presentation plan", () => {
  const x = feed();
  x.planned[0].goal_tag = { primary_goal: "VO2_CAPACITY" };
  x.sessions[0].linked_goal_tag = x.planned[0].goal_tag;
  assert.equal(entries(x)[0].goal, "VO2_CAPACITY");
  x.sessions[0].goal_tag = { primary_goal: null };
  assert.equal(entries(x)[0].goal, null);
  assert.equal(entries(x)[0].goalTag.primary_goal, null);
});
test("unmatched plans and availability stay visible and preserve their original timing", () => {
  const x = feed();
  x.sessions = [];
  const source = c.eventsFrom(x);
  const availability = { ...source[0], kind: "availability", entityId: "window",
    key: "availability:window", title: "Edzéslehetőség" };
  source.push(availability);
  assert.deepEqual(c.calendarEntries(source), source);
});
test("all raw selection identities remain available after presentation deduplication", () => {
  const source = c.eventsFrom(feed()), [row] = c.calendarEntries(source);
  assert.equal(source.find((e) => e.key === row.key).kind, "session");
  assert.equal(source.find((e) => e.key === row.pairedPlan.key).kind, "planned");
});
for (const value of [true, "", "bad-id", { id: PLAN }])
  test(`malformed stored plan reference is rejected: ${JSON.stringify(value)}`, () => {
    const x = feed();
    x.sessions[0].planned_workout_id = value;
    assert.throws(() => c.readFeed(x));
  });
test("declared labels render as text in the combined tooltip", () => {
  const x = feed();
  x.planned[0].title = '<img src=x onerror="bad()">';
  const html = render(x);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x onerror=&quot;bad\(\)&quot;&gt;/);
});
