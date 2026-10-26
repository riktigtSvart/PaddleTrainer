import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';

const fixture=JSON.parse(readFileSync(new URL('./fixtures/calendar-segmented-duration.json',import.meta.url)));
const contracts=load('src/lib/calendar/contracts.ts');
const constraints=load('src/lib/calendar/constraints.ts');
const grid=load('src/components/calendar/time-grid.tsx');
const Details=load('src/components/calendar/duration-details.tsx').default;
const plan=fixture.feed.planned.find(p=>p.title==='6km paddling');

test('three continuous distance legs receive the actual backend estimate and no 08:00 conflict',async()=>{
    const feed=contracts.readFeed(fixture.feed);
    const context=await constraints.readScheduleContext(fixture.context);
    const source=feed.planned.find(p=>p.id===plan.id);
    assert.equal(source.duration_sec,null);
    assert.deepEqual(source.blocks.map(b=>[b.block_type,b.distance_m,b.duration_sec]),[
        ['WARMUP',1000,null],['WORK',2000,null],['WORK',3000,null],
    ]);
    assert.equal(source.duration_estimate.duration_sec,2120);
    assert.equal(source.duration_estimate.sample_count,10);
    assert.deepEqual(context.duration_estimates[plan.id],source.duration_estimate);
    assert(!context.conflicts.some(c=>c.plan_id===plan.id));
});

test('segmented plan card displays ~35 minutes and a labeled estimated 06:35 end',()=>{
    const feed=contracts.readFeed(fixture.feed),events=contracts.eventsFrom(feed);
    const event=events.find(e=>e.kind==='planned'&&e.entityId===plan.id);
    assert.equal(event.end,'2026-10-29T05:35:20.000Z');
    assert.equal(event.endEstimated,true);
    assert.match(grid.eventLabel(event,feed.timezone_name),/06:00–~06:35/);
    const html=renderToStaticMarkup(React.createElement(grid.default,{
        feed,events,days:contracts.dayList(feed.start_date,feed.end_date),fullDay:false,
        open(){},selectDay(){},expandHours(){},
    }));
    assert.match(html,/~35 p/);
    assert.match(html,/28–43 p/);
});

test('segmented estimate details show ten used observations while keeping both excluded sources visible',()=>{
    const html=renderToStaticMarkup(React.createElement(Details,{
        estimate:plan.duration_estimate,zone:fixture.feed.timezone_name,
    }));
    assert.match(html,/Naptári időbecslés · ~35 p/);
    assert.match(html,/10 saját/);
    assert.match(html,/28–43 p/);
    assert.equal((html.match(/becslésből kihagyva/g)||[]).length,2);
    for(const s of plan.duration_estimate.samples)assert(html.includes('/sessions/'+s.session_id));
});
