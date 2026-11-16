import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";

const history = load("src/lib/calendar/editor-history.ts");
const schedule = load("src/lib/calendar/constraints.ts");
const moves = load("src/lib/calendar/moves.ts");
const interactions = load("src/lib/calendar/interactions.ts");
const nav = load("src/lib/ui/navigation.ts");
const fixture = JSON.parse(readFileSync(new URL("./fixtures/calendar-history.json", import.meta.url)));
const original = JSON.parse(readFileSync(new URL("./fixtures/calendar-interactions.json", import.meta.url)));
const copy = structuredClone;

for (const operation of ["constraints", "availability"]) test(`${operation}: real HTTP edit, undo, redo and undo retain the exact revision chain`, async () => {
  const f = fixture[operation];
  const contexts = await Promise.all(f.contexts.map((c) => schedule.readScheduleContext(c)));
  const owner = contexts[0].athlete_id;
  let previous;
  for (let index = 0; index < f.receipts.length; index++) {
    const receipt = f.receipts[index], before = contexts[index], after = contexts[index + 1];
    const isUndo = index % 2 === 1, isRedo = index === 2;
    const pending = { version: "calendar-editor-pending-v0.1", operation, owner, body: JSON.stringify(receipt.artifact.proposal) };
    const recovery = await history.readRecovery(JSON.stringify(history.withHistory(pending, before, isUndo, isRedo)));
    assert.equal(recovery.body, pending.body);
    if (previous) {
      assert(history.undoAvailable(previous, before));
      const prepared = history.prepareUndo(before, previous);
      assert.deepEqual(JSON.parse(prepared.pending.body).data, receipt.artifact.proposal.data);
      assert.deepEqual(JSON.parse(prepared.pending.body).previous_reference, receipt.artifact.proposal.previous_reference);
      assert.notEqual(JSON.parse(prepared.pending.body).request_id, receipt.artifact.proposal.request_id);
    }
    const back = await history.makeUndo(recovery, receipt), forward = await history.makeRedo(recovery, receipt);
    assert.equal(back === null, isUndo);
    assert.equal(forward === null, !isUndo);
    previous = await history.readUndo(JSON.stringify(isUndo ? forward : back));
    assert(history.undoAvailable(previous, after));
    assert(!history.undoAvailable(previous, before));
    assert(!history.undoAvailable(previous, { ...after, timezone_review_required: true }));
    assert(!history.undoAvailable(previous, { ...after, athlete_id: crypto.randomUUID() }));
  }
});

test("redo refuses changed receipts, wrong requests, stale heads and ambiguous direction markers", async () => {
  const f = fixture.constraints, ctx = await schedule.readScheduleContext(f.contexts[1]);
  const pending = { version: "calendar-editor-pending-v0.1", operation: "constraints", owner: ctx.athlete_id, body: JSON.stringify(f.receipts[1].artifact.proposal) };
  const recovery = history.withHistory(pending, ctx, true);
  const tampered = copy(f.receipts[1]); tampered.artifact.proposal.data.rules[0].details.title = "Más tartalom";
  await assert.rejects(history.makeRedo(recovery, tampered));
  await assert.rejects(history.makeRedo(recovery, f.receipts[0]));
  assert.throws(() => history.withHistory(pending, ctx, true, true));
  for (const flags of [{ isUndo: true, isRedo: true }, { isUndo: false, isRedo: "yes" }]) {
    await assert.rejects(history.readRecovery(JSON.stringify({ ...recovery, history: { ...recovery.history, ...flags } })));
  }
  const forward = await history.makeRedo(recovery, f.receipts[1]);
  const stale = await schedule.readScheduleContext(f.contexts[3]);
  assert.throws(() => history.prepareUndo(stale, forward));
  const ordinary = history.withHistory({ ...pending, body: JSON.stringify(f.receipts[2].artifact.proposal) }, f.contexts[2], false);
  assert.equal(await history.makeRedo(ordinary, f.receipts[2]), null);
});

test("move redo uses real source-bound inverse commits and survives pending storage without changing bytes", async () => {
  const f = fixture.moves;
  for (let index = 0; index < f.receipts.length; index++) {
    const ctx = moves.readMoveContext(f.contexts[index], f.contexts[index].athlete_id, f.contexts[index].plan_id);
    const receipt = f.receipts[index], proposal = receipt.artifact.proposal;
    const body = JSON.stringify({ proposal, review_hash: f.previews[index].review_hash });
    await moves.readMoveReview(f.previews[index], proposal, ctx.athlete_id);
    await moves.readMoveReceipt(receipt, ctx.athlete_id, body);
    assert.deepEqual(proposal.previous_reference, ctx.previous_reference);
    assert.equal(proposal.expected_source_hash, ctx.source_hash);
    if (index) assert.deepEqual(f.previews[index].after, f.receipts[index - 1].artifact.before);
    const pending = { version: "calendar-move-pending-v0.1", owner: ctx.athlete_id, body, undo: index > 0, ...(index === 2 ? { redo: true } : {}) };
    assert.deepEqual(moves.readMovePending(JSON.stringify(pending)), pending);
    if (index === 2) {
      assert.throws(() => moves.readMovePending(JSON.stringify({ ...pending, undo: false })));
      assert.throws(() => moves.readMovePending(JSON.stringify({ ...pending, redo: "yes" })));
    }
  }
});

test("new slots use clicked civil time at different scales and preserve midnight explicitly", () => {
  const { clockSlot } = interactions;
  const first = clockSlot("2026-11-08", 250, 100, 400, 6, 22);
  assert.deepEqual(first, { date: "2026-11-08", start_time: "12:00", end_time: "13:00", ends_next_day: false });
  assert.deepEqual(clockSlot("2026-11-08", 400, 100, 800, 6, 22), first);
  assert.equal(clockSlot("2026-11-08", 101, 100, 400, 6, 22).start_time, "06:00");
  assert.deepEqual(clockSlot("2026-11-08", 500, 100, 400, 0, 24), { date: "2026-11-08", start_time: "23:55", end_time: "00:55", ends_next_day: true });
  for (const args of [["2026-02-30", 0, 0, 400, 6, 22], ["2026-11-08", NaN, 0, 400, 6, 22], ["2026-11-08", 0, 0, 0, 6, 22]]) assert.throws(() => clockSlot(...args));
});

test("frame sizing leaves the grid within a normal viewport and keeps a usable minimum on short screens", () => {
  assert.equal(interactions.frameHeight(1080, 260), 808);
  assert.equal(interactions.frameHeight(768, 320), 436);
  assert.equal(interactions.frameHeight(480, 350), 230);
});

test("sidebar destinations cover calendar details, six setup stages and existing deep links", () => {
  assert.equal(nav.navigation.length, 4);
  const data = nav.navigation.find((n) => n.href === "/training-planning");
  assert.deepEqual(data.children.map((n) => n.href.split("#")[1]), ["personal", "sports", "goals", "locations", "schedule", "assessment"]);
  for (const [route, primary, child] of [["/coach", "/", "/coach"], ["/personal-response", "/", "/personal-response"], ["/strength-assessment", "/training-planning", "/training-planning#assessment"], ["/training-options/locations", "/training-planning", "/training-planning#locations"], ["/training-options/schedule", "/training-planning", "/training-planning#schedule"]]) {
    assert.equal(nav.activeSection(route), primary);
    assert.equal(nav.activeSubmenu(route, ""), child);
  }
  assert.equal(nav.activeSubmenu("/training-planning", "#sports"), "/training-planning#sports");
});

test("fitted four-week cells expose crowded event totals and an explicit day expansion without slot buttons", () => {
  const { default: Grid } = load("src/components/calendar/period-grid.tsx");
  const { eventsFrom, dayList } = load("src/lib/calendar/contracts.ts");
  const feed = original.feed, source = eventsFrom(feed)[0], day = feed.start_date;
  const events = Array.from({ length: 9 }, (_, i) => ({ ...source, key: `planned:${i}`, entityId: String(i), kind: "planned", date: day, start: null, end: null, title: `Edzés ${i}` }));
  const html = renderToStaticMarkup(React.createElement(Grid, { feed, events, days: dayList(day, feed.end_date), fitted: true, selected: day, overview: false, open() {}, selectDay() {}, addSlot() {} }));
  assert.match(html, /9 esemény/);
  assert.match(html, /\+7 esemény/);
  assert.doesNotMatch(html, /\+ Idősáv|Idősáv hozzáadása/);
  assert.match(html, /Dupla kattintás: új idősáv/);
});
