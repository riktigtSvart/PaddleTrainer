import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { load } from "./load-goal-modules.mjs";
const f = JSON.parse(gunzipSync(readFileSync(new URL("./fixtures/calibration-strength.json.gz", import.meta.url))));
const { readContext, readReceipt, readCommand, stopped, readPending } = load("src/lib/guided-strength/contracts.ts");
const { groupIdentity, starterTargets, protocolFor, newMeasurement } = load("src/lib/guided-strength/calibration.ts");
const { recommendationsForContext } = load("src/lib/guided-strength/recommendations.ts");
const { readTrainingReview } = load("src/lib/planning-cycles/training-plan.ts");
const { sha } = load("src/lib/planning-cycles/contracts.ts");
const { default: Movement, CalibrationInstructions } = load("src/components/guided-strength/calibration-movement.tsx");
const { default: Preparation } = load("src/components/guided-strength/preparation.tsx");
const { forwardGoals } = load("src/lib/planning-goals/proxy.ts");
const { registryExtension } = load("src/lib/guided-strength/source-updates.ts");
const { elapsedWholeSeconds } = load("src/lib/guided-strength/activity.ts");
const owner = f.ready.athlete_id;
async function rehash(v) { const b = { ...v }; delete b.content_hash; v.content_hash = await sha(b); }
for (const name of ["ready", "active", "resumable", "complete"]) test(`v2 HTTP ${name} context verifies its exact protocol bank`, async () => { await readContext(f[name]); });
for (const name of ["started", "checkpoint", "second", "third", "finished"]) test(`v2 durable ${name} preserves exact command, protocol and actual results`, async () => { await readReceipt(f[name], owner, JSON.stringify(f[name].artifact.proposal)); });
test("calibration plan verifies reduced targets from the full owned measurement proof", async () => {
  await readTrainingReview(f.plan, { owner, reference:f.plan.program_reference, zone:f.plan.timezone_name });
  const targets = starterTargets(f.finished);
  assert.equal(targets.length, 2);
  assert.deepEqual(targets.map((v) => [v.derivation.source_repetitions, v.derivation.planned_repetitions]), [[6,4],[8,6]]);
  assert.equal(f.finished.artifact.proposal.progress.results[0].observations[0].repetitions,23);
  assert(targets.every((v) => v.sets.length===1 && v.sets[0].rir==="unknown" && v.derivation.planned_minimum_rir===3));
});
for (const rir of ["0","1","unknown"]) test(`actual RIR ${rir} is recordable and does not become a health-change claim`, () => {
  const p=structuredClone(f.finish_request);p.progress.results[0].observations[0].rir=rir;
  assert.equal(readCommand(p).progress.results[0].observations[0].rir,rir);
  assert.equal(stopped(p.progress),false);
});
for (const [name,change] of Object.entries({
  protocol_bank:v=>{v.calibration_protocols.entries[0].planned_measurement.target_rir=0;},
  authority:v=>{v.calibration_protocols.planning_authorized=true;},
  future_protocol:v=>{v.calibration_protocols.schema_version="strength-calibration-protocols-v99";},
})) test(`reject rehashed context: ${name}`,async()=>{const v=structuredClone(f.ready);change(v);await rehash(v.calibration_protocols);await rehash(v);await assert.rejects(()=>readContext(v));});
for (const [name,change] of Object.entries({
  actual_rest_boolean:p=>{p.progress.results[0].observations[0].actual_rest_seconds=true;},
  future_protocol:p=>{p.protocol_version="future";},
  duplicate_trial:p=>{p.progress.results[0].observations[1].trial_number=1;},
  extra_field:p=>{p.progress.results[0].observations[0].estimated_1rm="100";},
})) test(`invalid actual command: ${name}`,()=>{const p=structuredClone(f.finish_request);change(p);assert.throws(()=>readCommand(p));});
for (const [name,change] of Object.entries({
  missing_calibration_evidence:v=>{delete v.inputs.strength_assessment.calibration_evidence;},
  forged_target:v=>{v.result.alternatives.flatMap((g)=>g.candidates).find((c)=>c.sport==="STRENGTH").strength_prescription.movements[0].sets[0].repetitions+=1;},
  source_side:v=>{v.inputs.strength_assessment.calibration_evidence[0].artifact.proposal.progress.results[0].observations[0].side="right";},
})) test(`planner rejects rehashed ${name}`,async()=>{const v=structuredClone(f.plan);change(v);await rehash(v.inputs);await rehash(v);await assert.rejects(()=>readTrainingReview(v,{owner,reference:v.program_reference,zone:v.timezone_name}));});
test("stable unilateral group identities match Python UUIDv5 including Unicode",()=>{for(const [value,id] of Object.entries(f.identity_vectors))assert.equal(groupIdentity(value),id);});
test("native microseconds do not become a one-second duration disagreement",()=>{
  assert.equal(elapsedWholeSeconds("2026-10-23T10:00:00.000018+00:00","2026-10-23T10:20:00.000Z"),1199);
  assert.equal(elapsedWholeSeconds("2026-10-25T02:30:00.000001+02:00","2026-10-25T02:30:00.000001+01:00"),3600);
});
test("unknown rest stays null; real zero and exact decimal kg survive pending recovery",()=>{
  const p=structuredClone(f.finish_request);p.progress.results[0].observations[0].actual_rest_seconds=0;
  const body=JSON.stringify(readCommand(p));const pending=readPending(JSON.stringify({version:"guided-strength-pending-v0.1",owner,body}),owner);
  assert.equal(pending.body,body);assert.equal(JSON.parse(pending.body).progress.results[0].observations[0].actual_rest_seconds,0);
  assert.equal(f.finish_request.progress.results[0].observations[0].actual_rest_seconds,null);
  assert.equal(JSON.parse(pending.body).progress.results[0].observations[0].load_value,"12.500000");
});
test("sport recommendations retain all existing choices and prioritize the main sport",()=>{
  const c=structuredClone(f.ready.intake), before=JSON.stringify(c);
  const recommendations=recommendationsForContext(c);
  assert(recommendations.length);assert.equal(recommendations[0].pattern,"pull");assert.equal(JSON.stringify(c),before);
  c.data.sports.push({sport_key:"CYCLING",role:"secondary",discipline:"Országút",goal:"",notes:""});
  assert.equal(recommendationsForContext(c)[0].pattern,"pull");
  c.data.exercises[0].comfort="symptoms";assert(!recommendationsForContext(c).some((r)=>r.entryId===c.data.exercises[0].id));
});
test("only an additive registry extension can reuse unchanged reviewed answers",async()=>{
  const c=structuredClone(f.ready.intake);c.sources_changed=true;
  assert.equal(registryExtension(c),false);
  c.saved.artifact.snapshot.registry.patterns.forEach((p,i)=>p.exercise_ids=p.exercise_ids.slice(0,[12,9,7,6,8][i]));
  await rehash(c.saved.artifact.snapshot.registry);
  assert.equal(registryExtension(c),true);
  const options=structuredClone(c);options.sources.options_reference.content_hash="f".repeat(64);assert.equal(registryExtension(options),false);
  const changed=structuredClone(c);changed.sources.registry.patterns[0].label="más jelentés";assert.equal(registryExtension(changed),false);
  const removed=structuredClone(c);removed.sources.registry.patterns[0].exercise_ids=[];assert.equal(registryExtension(removed),false);
});
test("an unspecified pair of sides is not promoted to two measured unilateral results",()=>{
  const r=structuredClone(f.finished);r.artifact.proposal.progress.results[0].observations.forEach((s)=>{s.side="both";});
  assert.equal(starterTargets(r).length,1);
});
test("a movement displays its assessment command and direct result fields together",()=>{
  const row=f.started.artifact.proposal.progress.results[0],protocol=f.started.artifact.measurement_protocols.entries[0].protocol;
  const html=renderToStaticMarkup(React.createElement(Movement,{row,protocol,today:f.ready.local_today,mode:"calibration",onChange(){},onSave(){}}));
  assert(html.includes("A felmérés menete")&&html.includes("Tényleges szabályos ismétlésszám")&&html.includes("Elvégzett próba rögzítése és mentése")&&html.includes("Miért fejezted be"));
  assert(!html.includes("Elvégzett referenciasorozat rögzítése"));
});
test("the new instruction preview follows the user's explicit selection order",()=>{
  const place=f.ready.preparation.locations[0];const ids=place.entries.slice(0,2).map((e)=>e.entry_id).reverse();
  const html=renderToStaticMarkup(React.createElement(Preparation,{context:f.ready,place:place.location_id,ids,locked:false,mode:"manual",precheck:false,onPlace(){},onIds(){},onMode(){},onPrecheck(){},onBegin(){}}));
  const preview=html.slice(html.indexOf('aria-label="A kiválasztott gyakorlatok felmérési menete"'));
  const labels=ids.map((id)=>place.entries.find((e)=>e.entry_id===id).label);
  assert(preview.indexOf(labels[0])<preview.indexOf(labels[1]));
});
test("hold, carry, assistance and explosive tasks retain their own measurement instructions",()=>{
  for(const id of ["plank","farmers_carry","assisted_pullup","slam"]){const p=protocolFor(id);assert(p);assert.equal(p.steps.length,7);const m=newMeasurement(p,f.ready.local_today);assert.equal(m.actual_rest_seconds,null);}
  const p=protocolFor("plank");const html=renderToStaticMarkup(React.createElement(CalibrationInstructions,{protocol:p}));assert(html.includes("20 másodperc"));
  assert(protocolFor("assisted_pullup").steps.join(" ").includes("több segítséget"));
});
test("owned history proxy admits only GET UUID revisions and forwards to the exact endpoint",async()=>{
  const token=f.finished.artifact.proposal.request_id;
  const send=async(url,init)=>{assert.equal(String(url),`https://api.test/api/v1/planning/guided-strength/revisions/${token}`);assert.equal(init.method,"GET");return Response.json({ok:true});};
  const response=await forwardGoals(new Request(`https://paddle.test/api/goal-workflow/guided-strength/revisions/${token}`),["guided-strength","revisions",token],"https://api.test",send);assert.equal(response.status,200);
  for(const [method,id,query,status] of [["POST",token,"",405],["GET","bad","",404],["GET",token,"?url=https://evil.invalid",422]]){
    const r=await forwardGoals(new Request(`https://paddle.test/x${query}`,{method}),["guided-strength","revisions",id],"https://api.test",()=>{throw Error("must not forward");});assert.equal(r.status,status);
  }
});
