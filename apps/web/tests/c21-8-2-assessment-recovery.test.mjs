import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {load} from './load-goal-modules.mjs';

const f = JSON.parse(readFileSync(new URL('./fixtures/c21-8-2-assessment-recovery.json', import.meta.url)));
const {recoverAssessment, assessmentToken} = load('src/lib/initial-assessment/recovery.ts');
const {mergeAssessmentAnswers} = load('src/lib/initial-assessment/draft-sync.ts');
const {readContext, normalizeData} = load('src/lib/initial-assessment/contracts.ts');
const {loadAssessmentRevision} = load('src/lib/initial-assessment/client.ts');
const {forwardGoals} = load('src/lib/planning-goals/proxy.ts');
const owner = f.current.athlete_id, token = f.request.request_id;
const pending = {version:'initial-assessment-pending-v0.1', owner, body:JSON.stringify(f.request)};
const draft = (data = f.request.data, parent = f.old_context.reference, pendingId = null) => JSON.stringify({
  version:'initial-assessment-draft-v0.1', owner, data,
  source_hash:f.request.source_hash, previous_reference:parent, open:4, pending_request_id:pendingId,
});
const lookup = async token => [f.old, f.new, f.before.saved].find(r => r.artifact.proposal.request_id === token) ?? null;

test('real API revisions retain four current references and older August results separately', async () => {
  for (const c of [f.before, f.old_context, f.current]) await readContext(c);
  assert.equal(f.current.summary.recorded_reference_count, 4);
  assert.equal(f.old_context.summary.recorded_reference_count, 0);
});

test('an already committed pending write no longer locks or masks newer saved results', async () => {
  const calls = [];
  const result = await recoverAssessment(f.current, draft(f.request.data, f.request.previous_reference), JSON.stringify(pending), async id => {calls.push(id);return lookup(id);});
  assert.equal(result.pending, null);
  assert.deepEqual(result.committed.artifact, f.old.artifact);
  assert.deepEqual(result.data, f.current.data);
  assert.deepEqual(result.parent, f.current.reference);
  assert.deepEqual(calls, [token]);
});

test('an unchanged stale draft follows the latest saved sets instead of restoring old values', async () => {
  const result = await recoverAssessment(f.current, draft(), null, lookup);
  assert.deepEqual(result.data, f.current.data);
  assert.equal(result.data.reviewed, true);
  assert.deepEqual(result.base, f.current.data);
});

test('an older draft keeps unfinished answers while latest dates, sets and doses remain intact', async () => {
  const local = structuredClone(f.request.data);
  local.state_notes = 'Még mentetlen saját válasz';local.exercises[0].notes = 'Más fogás';
  const result = await recoverAssessment(f.current, draft(local), null, lookup);
  assert.equal(result.data.state_notes, local.state_notes);
  assert.equal(result.data.exercises[0].notes, local.exercises[0].notes);
  assert.equal(result.data.exercises[0].performed_on, '2026-11-11');
  assert.deepEqual(result.data.exercises[0].sets, f.current.data.exercises[0].sets);
  assert.equal(result.data.reviewed, false);
  assert.doesNotThrow(() => normalizeData(result.data));
});

test('pending recovery also retains edits made after the acknowledged snapshot', async () => {
  const local = structuredClone(f.request.data);local.state_notes='Saját változtatás';
  const result = await recoverAssessment(f.current, draft(local, f.request.previous_reference, token), JSON.stringify(pending), lookup);
  assert.equal(result.pending, null);assert.equal(result.data.state_notes, local.state_notes);
  assert.deepEqual(result.data.exercises, f.current.data.exercises);
  assert.equal(result.data.reviewed, false);
});

test('the latest matching committed receipt can resolve pending without an additional request', async () => {
  const result = await recoverAssessment(f.old_context, draft(), JSON.stringify(pending), () => {throw Error('Unexpected read');});
  assert.equal(result.pending, null);assert.deepEqual(result.data, f.old_context.data);
});

test('a legacy draft saved before request freezing cannot hide the newer frozen answers', async () => {
  const request = {...f.new.artifact.proposal, request_id:crypto.randomUUID(), previous_reference:f.current.reference,
    data:{...structuredClone(f.current.data), state_notes:'A függő kérésben már benne van'}};
  const uncertain = {...pending, body:JSON.stringify(request)};
  const result = await recoverAssessment(f.current, draft(f.current.data, f.current.reference), JSON.stringify(uncertain), async () => null);
  assert.equal(result.data.state_notes, request.data.state_notes);
  assert.equal(result.pending.body, uncertain.body);
});

test('a draft linked to its pending write preserves newer edits across reopening', async () => {
  const request = {...f.new.artifact.proposal, request_id:crypto.randomUUID(), previous_reference:f.current.reference};
  const uncertain = {...pending, body:JSON.stringify(request)}, local = structuredClone(f.current.data);
  local.state_notes='A bizonytalan mentés után beírt válasz';
  const result = await recoverAssessment(f.current, draft(local, f.current.reference, request.request_id), JSON.stringify(uncertain), async () => null);
  assert.equal(result.data.state_notes, local.state_notes);
  assert.equal(result.pending.body, uncertain.body);
});

for (const failure of ['missing', 'offline', 'foreign receipt', 'different request', 'edited receipt']) test('uncertain write is retained byte for byte: ' + failure, async () => {
  const uncertain = {...pending, body:JSON.stringify({...f.new.artifact.proposal, request_id:crypto.randomUUID(), previous_reference:f.current.reference})};
  const result = await recoverAssessment(f.current, draft(f.current.data, f.current.reference), JSON.stringify(uncertain), async () => {
    if (failure === 'missing') return null;
    if (failure === 'offline') throw Error('offline');
    if (failure === 'different request') return f.new;
    const wrong = structuredClone(f.old);
    if (failure === 'foreign receipt') wrong.artifact.athlete_id = crypto.randomUUID();
    else wrong.artifact.proposal.data.state_notes = 'Rewritten';
    return wrong;
  });
  assert.deepEqual(result.pending, uncertain);assert.equal(result.committed, null);
  assert.equal(result.pending.body, uncertain.body);
  assert.deepEqual(result.data, f.current.data);
});

test('an altered draft base requires explicit recovery and is never accepted as verified', async () => {
  const wrong = {...f.old_context.reference, content_hash:'0'.repeat(64)};
  const result = await recoverAssessment(f.current, draft(f.request.data, wrong), null, lookup);
  assert.equal(result.recoveryRequired,true);assert.equal(result.data.reviewed,false);
  assert.deepEqual(result.parent,f.current.reference);
  assert.throws(() => assessmentToken(crypto.randomUUID(), f.old_context.reference));
});

test('concurrent results on different days keep their own dates, loads and set counts', () => {
  const local = structuredClone(f.request.data);
  local.exercises[0].performed_on='2026-10-20';local.exercises[0].sets[0].repetitions=23;
  const merged = mergeAssessmentAnswers(f.request.data, local, f.current.data);
  const rows = merged.exercises.filter(e => e.pattern === 'pull');
  assert.equal(rows.length, 2);
  assert(rows.some(e => e.performed_on==='2026-10-20' && e.sets[0].repetitions===23));
  assert(rows.some(e => e.performed_on==='2026-11-11' && e.sets[0].rir==='2'));
  assert.equal(new Set(merged.exercises.map(e=>e.id)).size, merged.exercises.length);
  assert.doesNotThrow(() => normalizeData(merged));
});

test('revision client reads only the exact request and rejects a different valid receipt', async () => {
  const original = globalThis.fetch;let calls=0;
  globalThis.fetch = async (url, init) => {
    calls++;assert.equal(url,'/api/goal-workflow/initial-assessment/revisions/'+token);
    assert.equal(init.method, undefined);assert.equal(init.body, undefined);
    return Response.json(calls===1 ? f.old : f.new);
  };
  try {
    assert.deepEqual((await loadAssessmentRevision(owner,token)).artifact, f.old.artifact);
    await assert.rejects(() => loadAssessmentRevision(owner,token));
    await assert.rejects(() => loadAssessmentRevision(owner,'../evil'));assert.equal(calls,2);
  } finally {globalThis.fetch=original;}
});

for (const [method, tail, query, expected] of [
  ['GET',token,'',200],['POST',token,'',405],['DELETE',token,'',405],
  ['GET',token,'?owner=foreign',422],['GET',token,'?url=http://evil.invalid',422],
  ['GET','evil','',404],['GET',token+'/extra','',404],
]) test(`closed revision proxy ${method} ${tail} ${query}`, async () => {
  let calls=0;
  const path=['initial-assessment','revisions',...tail.split('/')];
  const response=await forwardGoals(new Request('https://app.test/api/goal-workflow/'+path.join('/')+query,{method,
    headers:{Authorization:'secret',Cookie:'secret'}}),path,'http://api.test/',async (url,init) => {
    calls++;assert.equal(String(url),'http://api.test/api/v1/planning/initial-assessment/revisions/'+token);
    assert.equal(init.headers.Authorization,undefined);assert.equal(init.headers.Cookie,undefined);
    return Response.json(f.old);
  });
  assert.equal(response.status,expected);assert.equal(calls,expected===200?1:0);
});
