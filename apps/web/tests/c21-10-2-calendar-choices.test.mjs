import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { load } from './load-goal-modules.mjs';

const f = JSON.parse(readFileSync(new URL('./fixtures/c21-10-2-calendar-choices.json', import.meta.url)));
const c = load('src/lib/calendar/contracts.ts');
const a = load('src/lib/calendar/training-alternatives.ts');
const { readTrainingReview } = load('src/lib/planning-cycles/training-plan.ts');
const { default: Badge } = load('src/components/calendar/alternative-badge.tsx');
const { default: TimeGrid } = load('src/components/calendar/time-grid.tsx');
const { default: PeriodGrid } = load('src/components/calendar/period-grid.tsx');
const { default: EventDetail } = load('src/components/calendar/event-detail.tsx');
const row = f.feed.planned.find(p => p.id === f.target_id);
const target = { ...row.planning_context, id: row.id };
const expected = { owner: f.feed.athlete_id, reference: target.program_reference, zone: f.feed.timezone_name };

test('real accepted calendar purposes and review hashes are readable without manual tags', async () => {
  for (const feed of [f.feed, f.accepted_feed, f.after]) {
    const parsed = c.readFeed(feed);
    for (const event of c.eventsFrom(parsed).filter(e => e.kind === 'planned')) {
      assert(event.planningContext);
      assert.equal(event.goal, event.planningContext.primary_goal);
      assert.notEqual(c.goalFamily(event.goal), 'other');
      assert.equal(event.goalTag, null);
    }
  }
  await readTrainingReview(f.review, expected);
  await readTrainingReview(f.choice, expected);
});

test('clicked later date has its own choices; today never replaces the clicked date', () => {
  const focused = a.focusedChoices(f.review, target);
  assert(focused);
  assert(target.date > f.feed.local_today);
  assert.equal(focused.group.date, target.date);
  assert(focused.group.candidates.every(p => p.date === target.date));
  assert.equal(focused.group.candidates.filter(p => p.candidate_key !== target.candidate_key).length, target.alternatives_count);
  const next = a.focusedChoices(f.choice, target);
  assert.equal(next.group.selected_candidate_key, f.candidate_key);
  const changes = a.alternativeChanges(f.choice);
  assert(changes.some(v => v.date === target.date));
  assert.equal(new Set(changes.map(v => v.date)).size, changes.length);
  assert(!changes.some(v => v.date === f.feed.local_today));
});

for (const [name, change] of [
  ['another workout', v => v.id = crypto.randomUUID()],
  ['another date', v => v.date = f.feed.local_today],
  ['changed prescription', v => v.workout_hash = 'a'.repeat(64)],
  ['another source candidate', v => v.candidate_key = 'a'.repeat(64)],
  ['another program', v => v.program_reference.artifact_id = 'pt-cycle:' + 'a'.repeat(64)],
]) test(`focus refuses ${name}`, () => {
  const v = structuredClone(target); change(v);
  assert.equal(a.focusedChoices(f.review, v), null);
});

test('protected current source cannot become a selectable replacement', () => {
  const v = structuredClone(f.review);
  v.plan_snapshots.find(p => p.workout.id === target.id).replaceable = false;
  assert.equal(a.focusedChoices(v, target), null);
});

test('fresh check always includes the clicked date even when the last review starts later', () => {
  for (const review of [null, f.review, { ...f.review, start_date: c.addDays(target.date, 1) }, { ...f.review, end_date: c.addDays(target.date, -1) }]) {
    const range = a.alternativeRange(review, target, f.feed.local_today);
    assert(range.first <= target.date && range.last >= target.date);
    assert(range.first >= f.feed.local_today);
  }
});

for (const [name, change] of [
  ['negative count', p => p.alternatives_count = -1],
  ['boolean count', p => p.alternatives_count = true],
  ['fractional count', p => p.alternatives_count = 1.1],
  ['unknown goal', p => p.primary_goal = 'INVENTED_GOAL'],
  ['unknown role', p => p.role = 'INVENTED_ROLE'],
  ['different mesocycle', p => p.mesocycle_id = crypto.randomUUID()],
  ['different date', p => p.date = f.feed.local_today],
  ['bad source hash', p => p.program_reference.content_hash = 'broken'],
  ['missing check instant', p => p.alternatives_checked_at = null],
  ['protected choices', p => p.replaceable = false],
]) test(`calendar projection rejects ${name}`, () => {
  const feed = structuredClone(f.feed); change(feed.planned[0].planning_context);
  assert.throws(() => c.readFeed(feed));
});

test('zero choices, unknown choices and old responses stay distinct', () => {
  const event = c.eventsFrom(c.readFeed(f.feed)).find(e => e.entityId === row.id);
  for (const value of [0, null, 2]) {
    const e = structuredClone(event); e.planningContext.alternatives_count = value;
    if (value === null) e.planningContext.alternatives_checked_at = null;
    const html = renderToStaticMarkup(React.createElement(Badge, { event: e }));
    assert(html.includes(`↔ ${value ?? '?'}`));
    assert(html.includes(value === null ? 'friss ellenőrzés szükséges' : `${value} a legutóbbi felülvizsgálatban`));
  }
  const legacy = structuredClone(f.feed); legacy.planned.forEach(p => delete p.planning_context);
  assert(c.readFeed(legacy));
  assert(c.eventsFrom(legacy).filter(e => e.kind === 'planned').every(e => e.goal === null));
});

test('manual non-null goal remains an override; clearing it restores the planning goal', () => {
  const feed = structuredClone(f.feed), plan = feed.planned[0];
  plan.goal_tag = { artifact_id: 'pt-workout-goal:' + 'a'.repeat(64) + ':' + 'b'.repeat(32), content_hash: 'c'.repeat(64), primary_goal: 'RECOVERY' };
  assert.equal(c.eventsFrom(c.readFeed(feed)).find(e => e.entityId === plan.id).goal, 'RECOVERY');
  plan.goal_tag.primary_goal = null;
  assert.equal(c.eventsFrom(c.readFeed(feed)).find(e => e.entityId === plan.id).goal, plan.planning_context.primary_goal);
});

test('one-day, weekly and four-week cards render the alternative indicator', () => {
  const feed = c.readFeed(f.feed), events = c.eventsFrom(feed);
  for (const span of [1, 7, 28]) {
    const props = { feed, events, days: Array.from({length: span}, (_, i) => c.addDays(target.date, i)), selected: target.date,
      open() {}, selectDay() {}, addSlot() {}, fitted: true, showFullDay: true };
    const html = renderToStaticMarkup(React.createElement(span === 28 ? PeriodGrid : TimeGrid, props));
    assert(html.includes('pt-alternative-badge'));
    assert(html.includes('Alternatív edzések:'));
    assert(html.includes(`pt-goal-${c.goalFamily(target.primary_goal)}`));
  }
});

test('the workout modal shows its mesocycle purpose and a day-specific entry point', () => {
  const feed = c.readFeed(f.feed), event = c.eventsFrom(feed).find(e => e.entityId === row.id);
  const html = renderToStaticMarkup(React.createElement(EventDetail, { event, feed, onClose() {} }));
  assert(html.includes(c.goalLabels[target.primary_goal]));
  assert(html.includes('Az adott nap alternatívái'));
  assert(!html.includes('Edzésterv és újraértékelés'));
  assert(!html.includes('Nincs külön megadva'));
});
