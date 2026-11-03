import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/training-options.json", import.meta.url)));
const options = load("src/lib/training-options/contracts.ts");
const { readTrainingReview } = load("src/lib/planning-cycles/training-plan.ts");
const { readScheduleContext } = load("src/lib/calendar/constraints.ts");
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const { forwardGoals } = load("src/lib/planning-goals/proxy.ts");
const { splitWeeklySlots } = load("src/components/training-options/schedule-editor.tsx");
const view = load("src/lib/planning-cycles/plan-view.ts");
const PlanOutput = load("src/components/planning-cycles/plan-output.tsx").default;
const expected = { owner: fixture.review.athlete_id, reference: fixture.review.program_reference, zone: fixture.review.timezone_name };

test("real HTTP options receipt and its exact normalized request are independently verified", async () => {
  const body = JSON.stringify(fixture.receipt.artifact.proposal);
  const receipt = await options.readOptionsReceipt(fixture.receipt, expected.owner, body);
  assert.equal(receipt.committed, true);
  const context = await options.readOptionsContext(fixture.context);
  assert.equal(context.data.locations[1].name, "Csillaghegyi uszoda");
  assert.deepEqual(context.data.locations[1].sports, ["SWIMMING"]);
  assert.deepEqual(context.data.locations[1].resources, []);
  const sameBudget = context.groups.find(group => group.details)?.alternatives;
  assert.equal(sameBudget.length, 2);
});

test("new opportunity source is accepted by the existing real calendar reader", async () => {
  const context = await readScheduleContext(fixture.schedule);
  assert(context.opportunities.some(group => group.source === "training_options"));
  assert(context.training_options_reference);
});

test("location-specific alternatives cannot borrow global equipment in a crafted response", async () => {
  const value = structuredClone(fixture.context);
  value.groups[0].alternatives.find(a => a.name === "Csillaghegyi uszoda").resources.push("Kajak");
  await assert.rejects(() => options.readOptionsContext(value));
});

test("a foreign-owner receipt and a changed exact request are rejected", async () => {
  await assert.rejects(() => options.readOptionsReceipt(fixture.receipt, "00000000-0000-0000-0000-000000000001"));
  const body = structuredClone(fixture.receipt.artifact.proposal);body.data.locations[0].name = "Másik hely";
  await assert.rejects(() => options.readOptionsReceipt(fixture.receipt, expected.owner, JSON.stringify(body)));
});

test("invalid dates, missing venue identities and duplicate slots fail before any request", () => {
  const unknown = structuredClone(fixture.context.data);unknown.weekly_slots[0].details.location_ids.push("00000000-0000-0000-0000-000000000099");assert.throws(() => options.readOptionsData(unknown));
  const date = structuredClone(fixture.context.data);date.schedule_start_date = "2026-02-30";assert.throws(() => options.readOptionsData(date));
  const slots = structuredClone(fixture.context.data);slots.weekly_slots.push(structuredClone(slots.weekly_slots[0]));assert.throws(() => options.readOptionsData(slots));
});

test("splitting a multi-day weekly source preserves each dated exception's actual weekday", () => {
  const data = structuredClone(fixture.context.data), slot = data.weekly_slots[0];
  data.exceptions = [{ slot_id: slot.id, date: "2026-10-25", replacement: null }];
  const split = splitWeeklySlots(data);
  assert.equal(split.weekly_slots.length, 7);
  const target = split.weekly_slots.find(s => s.id === split.exceptions[0].slot_id);
  assert.deepEqual(target.weekdays, [6]);
  assert.equal(split.exceptions[0].replacement, null);
  assert.deepEqual(data.exceptions[0], { slot_id: slot.id, date: "2026-10-25", replacement: null });
});

test("pending request recovery preserves the exact body without sending", () => {
  const value = { version: "training-options-pending-v0.1", owner: expected.owner, body: JSON.stringify(fixture.receipt.artifact.proposal) };
  assert.deepEqual(options.readPending(JSON.stringify(value)), value);
  assert.throws(() => options.readPending("{}"));
});

test("real current and next mesocycle reviews validate beyond the old 28-day limit", async () => {
  const review = await readTrainingReview(fixture.review, expected);
  assert.equal(review.start_date, "2026-10-24");assert.equal(review.end_date, "2026-12-17");
  assert(review.result.proposals.some(c => c.date > "2026-11-20"));
  assert(review.result.alternatives.some(group => group.candidates.length > 1));
  const changed = await readTrainingReview(fixture.changed, expected);assert(changed.selection_preferences);
});

test("unknown recommended alternative is rejected even when outer review is rehashed", async () => {
  const value = structuredClone(fixture.review);value.result.alternatives[0].recommended_candidate_key = "0".repeat(64);const { content_hash, ...raw } = value;value.content_hash = await sha(raw);await assert.rejects(() => readTrainingReview(value, expected));
});

test("rolling dates cross a week and a year without aligning to Monday", () => {
  assert.deepEqual(view.rollingDates("2026-11-04"), ["2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07", "2026-11-08", "2026-11-09", "2026-11-10"]);
  assert.equal(view.rollingDates("2026-12-29").at(-1), "2027-01-04");
  assert.equal(view.localDay("Europe/Budapest", new Date("2026-11-02T23:05:00Z")), "2026-11-03");
});

test("detailed horizon follows saved cycle boundaries instead of assuming four-week cycles", () => {
  const periods = [
    { id: "a", period_type: "MESOCYCLE", title: "A", start_date: "2026-11-01", end_date: "2026-11-20" },
    { id: "b", period_type: "MESOCYCLE", title: "B", start_date: "2026-11-21", end_date: "2026-12-25" },
    { id: "c", period_type: "MESOCYCLE", title: "C", start_date: "2026-12-26", end_date: "2027-01-15" },
  ];assert.equal(view.detailedEnd(periods, "2026-11-02"), "2026-12-25");assert.equal(view.detailedEnd(periods, "2026-11-21"), "2027-01-15");
});

test("a chosen alternative remains one session and planned matching snapshot is not duplicated", () => {
  const day = fixture.review.result.proposals[0], value = structuredClone(fixture.review);value.plan_snapshots.push({ candidate_key: day.candidate_key, workout: { id: "00000000-0000-0000-0000-000000000099", date: day.date, title: day.title, sport: day.sport, duration_sec: day.duration_sec, status: "PLANNED" } });value.result.keep.push("00000000-0000-0000-0000-000000000099");
  const entries = view.entriesOnDay(value, day.date);assert.equal(entries.length, 1);assert.equal(entries[0].kind, "planned");
  const changes = view.reviewChanges(fixture.review, fixture.changed);assert(changes.some(change => change.date === day.date));
});

test("clickable day output contains seven columns and fully expanded distinct alternatives", () => {
  const Native = globalThis.Date, instant = fixture.review.result.alternatives.find(group => group.candidates.length > 1).date + "T12:00:00Z";
  class Clock extends Native { constructor(...args) { super(...(args.length ? args : [instant])); } }
  globalThis.Date = Clock;
  try { const html = renderToStaticMarkup(React.createElement(PlanOutput, { review: fixture.review, disabled: false, onChoose() {} }));assert.equal((html.match(/class="pt-plan-day"/g) ?? []).length, 7);assert(!html.includes("Részletek"));assert(!html.includes("<details"));assert(html.includes("Alapértelmezett · ajánlott"));assert(html.includes("A javaslatban kiválasztva"));assert(html.includes("Bemelegítés"));assert(html.includes("Levezetés"));assert(html.includes("Most nem választható")); } finally { globalThis.Date = Native; }
});

test("training options proxy is scoped and retains same-origin and closed-query protections", async () => {
  let sent = 0;const send = async url => { sent++;assert.equal(new URL(url).pathname, "/api/v1/planning/training-options");return Response.json(fixture.context); };
  const response = await forwardGoals(new Request("https://paddle.test/api/goal-workflow/training-options?start_date=2026-10-24&end_date=2026-10-30"), ["training-options"], "http://127.0.0.1:8000", send);assert.equal(response.status, 200);assert.equal(sent, 1);
  const duplicate = await forwardGoals(new Request("https://paddle.test/api/goal-workflow/training-options?start_date=2026-10-24&start_date=2026-10-25"), ["training-options"], "http://127.0.0.1:8000", send);assert.equal(duplicate.status, 422);assert.equal(sent, 1);
  const foreign = await forwardGoals(new Request("https://paddle.test/api/goal-workflow/training-options", { method: "POST", headers: { Origin: "https://foreign.test", "Content-Type": "application/json" }, body: "{}" }), ["training-options"], "http://127.0.0.1:8000", send);assert.equal(foreign.status, 403);assert.equal(sent, 1);
});
