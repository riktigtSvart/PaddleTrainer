import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const c = load("src/lib/calendar/contracts.ts"),
  o = load("src/lib/calendar/overview.ts"),
  p = load("src/lib/calendar/event-preview.ts");
const event = {
  key: "planned:example",
  kind: "planned",
  entityId: "example",
  title: "6 km kajak",
  sport: "KAYAK",
  date: "2026-10-26",
  start: null,
  end: null,
  duration: null,
  goal: null,
  goalTag: null,
};
test("overview starts on Monday and spans 24 complete weeks across a year boundary", () => {
  const ranges = o.initialOverview("2026-12-31");
  assert.equal(ranges.length, 6);
  assert.equal(ranges[0].start, "2026-12-28");
  assert.equal(c.dateDistance(ranges[0].start, ranges.at(-1).end) + 1, 168);
  for (let i = 0; i < ranges.length; i++) {
    assert.equal(c.dayList(ranges[i].start, ranges[i].end).length, 28);
    if (i) assert.equal(c.addDays(ranges[i - 1].end, 1), ranges[i].start);
  }
});
for (const direction of [-1, 1])
  test(`overview loads repeatedly in direction ${direction} while retaining bounded memory`, () => {
    let ranges = o.initialOverview("2026-10-26");
    for (let i = 0; i < 60; i++) {
      ranges = o.retainOverview(
        ranges,
        o.adjacentOverview(ranges, direction),
        direction,
      );
      assert.ok(ranges.length <= 8);
      assert.equal(
        c.dateDistance(ranges[0].start, ranges.at(-1).end) + 1,
        ranges.length * 28,
      );
      for (let n = 1; n < ranges.length; n++)
        assert.equal(c.addDays(ranges[n - 1].end, 1), ranges[n].start);
    }
  });
test("reversing direction refetches a discarded edge without gaps or duplicates", () => {
  let ranges = o.initialOverview("2026-10-26");
  const initial = ranges[0].start;
  for (let i = 0; i < 5; i++)
    ranges = o.retainOverview(ranges, o.adjacentOverview(ranges, 1), 1);
  for (let i = 0; i < 3; i++)
    ranges = o.retainOverview(ranges, o.adjacentOverview(ranges, -1), -1);
  assert.equal(ranges[0].start, initial);
  assert.equal(new Set(ranges.map((r) => r.start)).size, ranges.length);
});
test("invalid or duplicate chunks cannot silently move the loaded window", () => {
  const ranges = o.initialOverview("2026-10-26");
  assert.equal(o.retainOverview(ranges, ranges[0], -1), ranges);
  assert.throws(() =>
    o.retainOverview(ranges, { start: "2026-01-01", end: "2026-01-28" }, -1),
  );
  assert.throws(() => o.overviewRange("2100-12-20"));
  assert.throws(() => o.overviewRange("1899-12-20"));
});
test("overview civil-day chunks retain all days across DST and leap years", () => {
  for (const date of ["2026-03-29", "2026-10-25", "2028-02-29"]) {
    const ranges = o.initialOverview(date);
    assert.equal(c.dayList(ranges[0].start, ranges.at(-1).end).length, 168);
  }
});
test("paired completion opens its session, remaining plan its workout, and constraints stay editable", () => {
  assert.equal(
    p.eventHref({ ...event, kind: "session", linkedPlanId: "plan" }),
    "/sessions/example",
  );
  assert.equal(p.eventHref(event), "/workouts/example");
  assert.equal(p.eventHref({ ...event, kind: "constraint" }), null);
  assert.equal(p.eventHref({ ...event, kind: "availability" }), null);
});
test("preview preserves known zero values and does not invent absent metrics", () => {
  const lines = p.previewLines(
    { ...event, kind: "session", duration: 0 },
    {
      sessions: [{ id: "example", distance_m: 0, avg_hr: 0, calories: 0 }],
      planned: [],
    },
  );
  for (const value of ["0 km", "0 kcal", "0 bpm átlagpulzus"])
    assert.ok(lines.includes(value));
  assert.deepEqual(p.previewLines(event, { sessions: [], planned: [] }), [
    "Tervezett",
  ]);
});
test("calendar names 4 weeks and overview without a missing-budget warning or side detail pane", () => {
  const html = renderToStaticMarkup(
    React.createElement(load("src/components/calendar/workspace.tsx").default),
  );
  assert.match(html, />4 hét</);
  assert.match(html, />Áttekintés</);
  assert.doesNotMatch(
    html,
    /144 nap|28 nap|Edzésidő-beállítás hiányos|Kijelölt esemény részletei/,
  );
});
