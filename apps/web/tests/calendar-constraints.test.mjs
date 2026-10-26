import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/calendar-constraints.json", import.meta.url)));
const c = load("src/lib/calendar/constraints.ts"), f = load("src/lib/calendar/constraint-forms.ts");
const contracts = load("src/lib/calendar/contracts.ts"), client = load("src/lib/calendar/constraint-client.ts");
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const { forwardCalendar } = load("src/lib/calendar/proxy.ts");
const owner = fixture.context.athlete_id, original = fixture.context.data.rules[0];
const source = fixture.context.occurrences.find((o) => o.source_date === "2026-10-21");
const clone = (value) => structuredClone(value);
const jsonResponse = (value, status = 200) => Response.json(value, { status });

test("real backend context, durable receipt and full availability are accepted", async () => {
  assert.equal((await c.readScheduleContext(fixture.context)).athlete_id, owner);
  assert.equal((await c.readScheduleReceipt(fixture.receipt, owner)).committed, true);
  assert.deepEqual(c.currentCalendar(fixture.context), fixture.availability_body.data);
});
for (const [name, mutate] of [
  ["truncated", (x) => { x.has_more = true; }],
  ["authority", (x) => { x.planning_authorized = true; }],
  ["wrong range", (x) => { x.end_date = "2028-01-01"; }],
  ["edited occurrence", (x) => { x.occurrences[0].details.title = "Forged"; }],
  ["missing issue", (x) => { x.occurrences[0].start_at = null; }],
  ["edited receipt", (x) => { x.saved.artifact.proposal.data.rules[0].details.title = "Forged"; }],
  ["unknown capacity as zero", (x) => { x.opportunities[0].known = false; x.opportunities[0].usable_minutes = 0; }],
  ["foreign availability", (x) => { x.availability.artifact.athlete_id = crypto.randomUUID(); }],
]) test(`context fails closed: ${name}`, async () => {
  const value = clone(fixture.context); mutate(value); await assert.rejects(c.readScheduleContext(value));
});
test("single exception changes Wednesday while preserving the weekly rule", () => {
  const changed = { ...clone(original), id: crypto.randomUUID(), details: { ...original.details, start_time: "19:00", end_time: "20:00" } };
  const value = c.changeSchedule(fixture.context.data, changed, source, "occurrence");
  assert.deepEqual(value.rules, fixture.context.data.rules);
  assert.deepEqual(value.exceptions, [{ rule_id: original.id, date: source.source_date, replacement: changed.details }]);
});
test("skipping one occurrence can be restored without leaving a redundant exception", () => {
  const skipped = c.changeSchedule(fixture.context.data, original, source, "occurrence", true);
  assert.equal(skipped.exceptions[0].replacement, null);
  const restored = c.changeSchedule(skipped, original, source, "occurrence");
  assert.deepEqual(restored, fixture.context.data);
});
test("future split preserves earlier days and later exceptions, but replaces today's override", () => {
  const state = clone(fixture.context.data);
  state.exceptions.push({ rule_id: original.id, date: "2026-10-21", replacement: { ...original.details, title: "Old override" } },
    { rule_id: original.id, date: "2026-10-23", replacement: null });
  const changed = { ...clone(original), id: crypto.randomUUID(), details: { ...original.details, title: "New work" } };
  const value = c.changeSchedule(state, changed, source, "future");
  assert.equal(value.rules[0].end_date, "2026-10-20");
  assert.equal(value.rules[1].start_date, "2026-10-21");
  assert.deepEqual(value.exceptions, [{ rule_id: changed.id, date: "2026-10-23", replacement: null }]);
  assert.equal(state.rules[0].end_date, null);
});
test("future removal keeps historical rule and removes only future exceptions", () => {
  const value = c.changeSchedule(fixture.context.data, original, source, "future", true);
  assert.equal(value.rules[0].end_date, "2026-10-20");
  assert.deepEqual(value.exceptions, []);
});
test("once edits retain identity and once deletion keeps other rules", () => {
  const once = { ...clone(original), repeat: "once", start_date: "2026-10-21", end_date: "2026-10-21", weekdays: [] };
  const state = { timezone_name: fixture.context.timezone_name, rules: [once], exceptions: [] };
  const o = { ...source, repeat: "once" };
  const changed = { ...once, id: crypto.randomUUID(), details: { ...once.details, title: "Changed" } };
  assert.equal(c.changeSchedule(state, changed, o, "future").rules[0].id, once.id);
  assert.equal(c.changeSchedule(state, changed, o, "occurrence", true).rules.length, 0);
});
test("weekday, fold and explicit kind errors never silently become a usable window", () => {
  assert.throws(() => c.readSchedule({ ...fixture.context.data, rules: [{ ...original, weekdays: [] }] }));
  assert.throws(() => c.readDetails({ ...original.details, start_fold: false }));
  assert.throws(() => c.readDetails({ ...original.details, category: "training" }));
});
test("legacy quick edit preserves every other day, window, resource and daily cap", () => {
  const event = contracts.eventsFrom(fixture.feed).find((e) => e.kind === "availability");
  const draft = f.draftFor(event.date, event); draft.daily = "90";
  draft.details.start_time = "06:30";
  const value = f.legacyChange(c.currentCalendar(fixture.context), event, draft, false);
  assert.deepEqual(value.days.slice(1), fixture.availability_body.data.days.slice(1));
  assert.deepEqual(value.days[0].windows[1], fixture.availability_body.data.days[0].windows[1]);
  assert.equal(value.days[0].max_total_minutes, 90);
  assert.equal(value.days[0].windows[0].start_time, "06:30");
  assert.deepEqual(value.days[0].windows[0].resources, event.window.resources);
});
test("deleting last legacy window makes the day unknown, with no stale daily budget", () => {
  const event = contracts.eventsFrom(fixture.feed).find((e) => e.kind === "availability");
  const calendar = clone(c.currentCalendar(fixture.context)); calendar.days[0].windows = [calendar.days[0].windows[0]];
  const value = f.legacyChange(calendar, event, f.draftFor(event.date, event), true);
  assert.equal(value.days[0].status, "unknown"); assert.equal(value.days[0].max_total_minutes, null);
});
test("legacy census extension keeps old data and refuses to drop days beyond 366", () => {
  const calendar = clone(c.currentCalendar(fixture.context));
  const value = f.extendCalendar(calendar, "2026-10-20", fixture.context.timezone_name);
  assert.deepEqual(value.days.slice(3), calendar.days);
  assert.throws(() => f.extendCalendar(calendar, "2024-01-01", fixture.context.timezone_name));
});
test("pending request survives persistence byte for byte with owner and operation", () => {
  const pending = { version: "calendar-editor-pending-v0.1", owner, operation: "constraints", body: JSON.stringify(fixture.receipt.artifact.proposal, null, 2) };
  assert.deepEqual(c.readEditorPending(JSON.stringify(pending)), pending);
  assert.throws(() => c.readEditorPending(JSON.stringify({ ...pending, owner: "other" })));
});
test("receipt requires exact owner, frozen body, valid hash and committed status", async () => {
  await assert.rejects(c.readScheduleReceipt(fixture.receipt, crypto.randomUUID()));
  await assert.rejects(c.readScheduleReceipt({ ...fixture.receipt, committed: false }, owner));
  await assert.rejects(c.readScheduleReceipt(fixture.receipt, owner, JSON.stringify({ ...fixture.receipt.artifact.proposal, request_id: crypto.randomUUID() })));
});
test("uncertain save retries identical bytes; only a verified durable receipt succeeds", async () => {
  const old = globalThis.fetch, bodies = [];
  const pending = { version: "calendar-editor-pending-v0.1", owner, operation: "constraints", body: JSON.stringify(fixture.receipt.artifact.proposal, null, 2) };
  globalThis.fetch = async (_url, options) => { bodies.push(options.body); if (bodies.length === 1) throw new TypeError("Lost reply"); return jsonResponse(fixture.receipt); };
  try { await assert.rejects(client.sendEditor(pending)); await client.sendEditor(pending); assert.deepEqual(bodies, [pending.body, pending.body]); }
  finally { globalThis.fetch = old; }
});
test("availability receipt cannot resolve another owner's pending edit", async () => {
  const old = globalThis.fetch;
  globalThis.fetch = async () => jsonResponse(fixture.context.availability);
  try { await assert.rejects(client.sendEditor({ version: "calendar-editor-pending-v0.1", owner: crypto.randomUUID(), operation: "availability", body: JSON.stringify(fixture.availability_body) })); }
  finally { globalThis.fetch = old; }
});
test("preview verifies the exact proposal hash, owner, dates and projected data", async () => {
  const old = globalThis.fetch, proposal = fixture.receipt.artifact.proposal;
  const value = { ...clone(fixture.context), reference: null, saved: null, proposal_hash: await sha(proposal) };
  globalThis.fetch = async () => jsonResponse(value);
  try {
    await client.previewConstraints(proposal, owner, value.start_date, value.end_date);
    value.proposal_hash = "0".repeat(64);
    await assert.rejects(client.previewConstraints(proposal, owner, value.start_date, value.end_date));
  } finally { globalThis.fetch = old; }
});
for (const [method, path] of [["GET", ["constraints"]], ["POST", ["constraints"]], ["POST", ["constraints", "preview"]]])
  test(`closed proxy accepts ${method} ${path.join("/")} without forwarding credentials`, async () => {
    const request = new Request("http://localhost:3000/api/calendar/" + path.join("/"), { method,
      headers: { Origin: "http://localhost:3000", "Content-Type": "application/json", Authorization: "must-not-forward" },
      ...(method === "POST" ? { body: "{\n \"exact\":true\n}" } : {}) });
    const result = await forwardCalendar(request, path, "http://127.0.0.1:8000", async (url, options) => {
      assert.equal(new URL(url).pathname, "/api/v1/planning/calendar/" + path.join("/"));
      assert.equal(options.headers.Authorization, undefined); assert.equal(options.redirect, "error");
      if (method === "POST") assert.equal(options.body, "{\n \"exact\":true\n}");
      return jsonResponse({ ok: true });
    }); assert.equal(result.status, 200);
  });
for (const [method, path, status] of [["GET", ["constraints", "preview"], 405], ["POST", ["constraints", ".."], 404], ["DELETE", ["constraints"], 405]])
  test(`closed proxy rejects ${method} ${path.join("/")}`, async () => {
    assert.equal((await forwardCalendar(new Request("http://localhost/api/calendar/x", { method }), path, "http://127.0.0.1:8000", () => { throw new Error("must not fetch"); })).status, status);
  });
test("constraint proxy supports full snapshots, enforces 1 MiB streamed bytes and leaves goal limit unchanged", async () => {
  const body = "x".repeat(20000), headers = { Origin: "http://localhost", "Content-Type": "application/json" };
  assert.equal((await forwardCalendar(new Request("http://localhost/x", { method: "POST", headers, body }), ["constraints"], "http://127.0.0.1", async () => jsonResponse({}))).status, 200);
  assert.equal((await forwardCalendar(new Request("http://localhost/x", { method: "POST", headers, body }), ["goals"], "http://127.0.0.1")).status, 413);
  assert.equal((await forwardCalendar(new Request("http://localhost/x", { method: "POST", headers, body: "x".repeat(1048577) }), ["constraints"], "http://127.0.0.1")).status, 413);
});
test("commitments render as neutral background, do not consume training lanes or invent a workout goal", () => {
  const TimeGrid = load("src/components/calendar/time-grid.tsx").default;
  const events = [...contracts.eventsFrom(fixture.feed), ...f.constraintEvents(fixture.context)];
  const html = renderToStaticMarkup(React.createElement(TimeGrid, { feed: fixture.feed, events, days: contracts.dayList(fixture.feed.start_date, fixture.feed.end_date), fullDay: false, open() {}, selectDay() {}, expandHours() {} }));
  assert.match(html, /is-commitment/);
  assert.match(html, /Munka/);
  assert(!html.includes("Munka · 17:00–18:00 · Munka · rögzített · 1 ó · fő cél"));
  assert.match(html, /32px/);
});
