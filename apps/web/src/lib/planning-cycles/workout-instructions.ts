import {workoutPresentation,workSeconds,strengthWorkSource} from "./strength-workout";
import type {StrengthWorkoutDose} from "./strength-workout";
import routines from "./training-routines.v0.1.json";
import {canonical,object} from "./contracts";
import type {AssessedStrengthDose} from "./strength-assessment";
import {strengthPresentation} from "./strength-assessment";
import type {Prescription} from "./prescription-context";
type Row=Record<string,unknown>;
type Step={name:string;duration_sec:number;instruction:string};
export type WorkoutInstructions={schema_version:"workout-instructions-v0.1";library_version:string;sport:string;duration_sec:number;source_kind:string;
  warmup:{duration_sec:number;purpose:string;steps:Step[]};
  main:{duration_sec:number;instruction:string;strength:AssessedStrengthDose|StrengthWorkoutDose|null;introductory_strength:Prescription["introductory_strength"]|null};
  finish:{duration_sec:number;easy_duration_sec:number;purpose:string;stretching_optional:true;stretching_replaces_easy_finish:true;stretches:(Step&{key:string})[];instruction:string};
  stop_rule:string;external_load_increased:false;sets_added:false;recovery_effect_claimed:false;personal_response_model_applied:false;source_urls:string[]};
const check=(v:unknown)=>{if(!v)throw Error("Az edzés gyakorlatsora eltér a mentett terheléstől vagy időkerettől.");};
function deriveWithLibrary(candidate:Row,metadata:Row,library:typeof routines):WorkoutInstructions {
  const routine=library.sports[String(candidate.sport) as keyof typeof library.sports];check(routine);
  const blocks=(candidate.blocks as unknown[]).map(object),warm=Number(blocks[0].duration_sec),finish=Number(blocks.at(-1)!.duration_sec);
  const strength=metadata.strength&&["assessed-strength-dose-v0.1","strength-workout-dose-v0.1"].includes(String(object(metadata.strength).schema_version))?metadata.strength:null;
  const independent=strength&&object(strength).schema_version==="strength-workout-dose-v0.1";
  return {schema_version:"workout-instructions-v0.1",library_version:independent?"training-routines-v0.2":library.schema_version,sport:String(candidate.sport),duration_sec:Number(candidate.duration_sec),source_kind:"verified_prescription_and_product_routines",
    warmup:{duration_sec:warm,purpose:"Fokozatos ráhangolás és kontrollált átmozgatás.",steps:[
      {name:routine.easy,duration_sec:90,instruction:"Kényelmes, könnyű erőfeszítés; a légzés maradjon nyugodt."},
      {name:routine.gym,duration_sec:90,instruction:routine.gym_instruction},
      {name:"Ismert sportmozgás előkészítése",duration_sec:warm-180,instruction:independent?"A főgyakorlatok ismert, fokozatos, könnyű rávezetését végezd. Csak már bevált terhelést használj, kifáradás nélkül; ne ugorj közvetlenül a munkasúlyra. A rávezető sorozatok nem munkasorozatok. Ha a szokásos előkészítés nem fér bele, hagyd el a hátralévő munkát.":routine.specific}]},
    main:{duration_sec:blocks.slice(1,-1).reduce((s,b)=>s+Number(b.duration_sec),0),instruction:String(candidate.description),strength:strength as AssessedStrengthDose|StrengthWorkoutDose|null,introductory_strength:(metadata.introductory_strength??null) as WorkoutInstructions["main"]["introductory_strength"]},
    finish:{duration_sec:finish,easy_duration_sec:finish-120,purpose:"Könnyű levezetés; a választható nyújtás célja a mozgástartomány gyakorlása.",stretching_optional:true,stretching_replaces_easy_finish:true,
      stretches:routine.stretches.map(([key,name,instruction])=>({key,name,duration_sec:60,instruction})),
      instruction:"Először nagyon könnyű sportmozgás vagy séta. A két választható nyújtás a levezetés utolsó két percének alternatívája, nem többletidő. Ha a helyszín, az idő vagy a mozdulat nem megfelelő, maradj könnyű mozgásnál vagy fejezd be. Enyhe húzódásig dolgozz, fájdalom és rugóztatás nélkül."},
    stop_rule:"Csak ismert, panaszmentes mozdulatot végezz. Romló kontroll, fájdalom vagy szokatlan rosszullét esetén állj meg; az időkeretet nem kell kitölteni.",external_load_increased:false,sets_added:false,recovery_effect_claimed:false,personal_response_model_applied:false,source_urls:library.source_urls};
}
export function deriveInstructions(candidate:Row,metadata:Row):WorkoutInstructions {
  return deriveWithLibrary(candidate,metadata,routines);
}
let legacyLibraries:typeof routines[]|undefined;
function knownLegacyLibraries() {
  // Reproduce the old Windows library reader only. Athlete data and the
  // captured review remain intact; never perform a blanket text conversion.
  return legacyLibraries??=(['windows-1250','windows-1252'].map(encoding=>
    JSON.parse(new TextDecoder(encoding,{fatal:true}).decode(new TextEncoder().encode(JSON.stringify(routines)))) as typeof routines));
}
function matchesInstructions(raw:unknown,candidate:Row,metadata:Row) {
  const encoded=canonical(raw);
  return encoded===canonical(deriveInstructions(candidate,metadata))||knownLegacyLibraries().some(old=>encoded===canonical(deriveWithLibrary(candidate,metadata,old)));
}
export function validateInstructionContext(review:Row) {
  const result=object(review.result);
  if(!["training-plan-policy-v0.14","training-plan-policy-v0.15"].includes(String(object(result.policy).version))){check(result.instruction_context===undefined);return;}
  const ctx=object(result.instruction_context),meta=object(object(result.prescription_context).by_candidate),stored=object(ctx.by_candidate),proposals=(result.proposals as unknown[]).map(object);
  check(ctx.schema_version==="training-instructions-v0.1"&&canonical(Object.keys(stored).sort())===canonical(proposals.map(c=>String(c.candidate_key)).sort()));
  for(const c of proposals)check(matchesInstructions(stored[String(c.candidate_key)],c,object(meta[String(c.candidate_key)])));
}
/** A calibrated starter has a prescribed minimum reserve, but its actual RIR
 * is deliberately unknown. Its source observation and reduction must agree;
 * an ordinary self-reported set still needs its recorded reserve of 3+. */
function checkProjectedStrength(dose:Row) {
  check(dose.schema_version==="assessed-strength-dose-v0.1"&&dose.minimum_rir===3&&
    dose.max_sets_per_movement===2&&dose.load_increased===false&&dose.sets_added===false&&
    dose.one_rm_estimated===false&&dose.full_development_claim===false&&
    Array.isArray(dose.movements)&&dose.movements.length===2);
  const movements=(dose.movements as unknown[]).map(object);
  check(dose.calibration_derivations===undefined||Array.isArray(dose.calibration_derivations));
  const derived=((dose.calibration_derivations??[]) as unknown[]).map(object);
  check(derived.length<=2&&new Set(derived.map(d=>d.entry_id)).size===derived.length&&
    derived.every(d=>movements.some(m=>m.entry_id===d.entry_id))&&
    dose.rest_seconds===(derived.length?180:120));
  for(const m of movements){
    check(typeof m.label==="string"&&Array.isArray(m.sets)&&m.sets.length>=1&&m.sets.length<=2);
    const derivation=derived.find(d=>d.entry_id===m.entry_id);
    for(const raw of m.sets as unknown[]){
      const s=object(raw);
      check(s.symptoms==="none"&&s.technique==="stable"&&
        (Number.isInteger(s.repetitions)&&Number(s.repetitions)>=1&&Number(s.repetitions)<=15||
         s.repetitions===null&&Number(s.hold_seconds)>0&&Number(s.hold_seconds)<=60));
      if(!derivation){check(["3","4","5_plus"].includes(String(s.rir)));continue;}
      const reference=object(derivation.guided_reference);
      check((m.sets as unknown[]).length===1&&s.rir==="unknown"&&s.hold_seconds===null&&
        derivation.rules_version==="calibration-starter-v0.1"&&
        derivation.observation_id===s.id&&
        Number.isSafeInteger(derivation.source_repetitions)&&Number(derivation.source_repetitions)>=4&&
        derivation.planned_repetitions===Math.min(8,Number(derivation.source_repetitions)-2)&&
        s.repetitions===derivation.planned_repetitions&&
        ["2","3","4","5_plus"].includes(String(derivation.source_rir))&&
        derivation.planned_minimum_rir===3&&derivation.personal_capacity_estimated===false&&
        derivation.one_rm_estimated===false&&typeof derivation.load_kind==="string"&&
        !["landmine_components","variant_dependent_load"].includes(derivation.load_kind)&&
        typeof reference.artifact_id==="string"&&/^pt-guided-strength:[a-f0-9]{32}:[a-f0-9]{32}$/.test(reference.artifact_id)&&
        typeof reference.content_hash==="string"&&/^[a-f0-9]{64}$/.test(reference.content_hash));
    }
  }
}
export function readProjectedInstructions(raw:unknown,row:Row):WorkoutInstructions {
  const value=object(raw),warm=object(value.warmup),main=object(value.main),finish=object(value.finish);
  check(value.sport===row.sport&&value.duration_sec===row.duration_sec&&main.instruction===row.description&&[300,600].includes(Number(warm.duration_sec))&&finish.duration_sec===300&&Number(main.duration_sec)>0&&Number(warm.duration_sec)+Number(main.duration_sec)+Number(finish.duration_sec)===row.duration_sec);
  const dose=main.strength?object(main.strength):null,intro=main.introductory_strength?object(main.introductory_strength):null;
  if(dose){if(dose.schema_version==="strength-workout-dose-v0.1") checkProjectedWorkout(dose);else checkProjectedStrength(dose);
    const presentation=dose.schema_version==="strength-workout-dose-v0.1"?workoutPresentation(dose as unknown as StrengthWorkoutDose):strengthPresentation(dose as unknown as AssessedStrengthDose,Number(row.duration_sec));check(presentation.description===row.description&&presentation.title===row.title);
  }
  if(intro)check(intro.schema_version==="introductory-strength-v0.1"&&intro.external_load_prescribed===false&&intro.preparatory_only===true&&intro.max_repetitions===5&&intro.sets_per_movement===1);
  const expected=deriveInstructions({sport:row.sport,duration_sec:row.duration_sec,description:row.description,blocks:[{duration_sec:warm.duration_sec},{duration_sec:main.duration_sec},{duration_sec:finish.duration_sec}]},{strength:dose,introductory_strength:intro});
  const candidate={sport:row.sport,duration_sec:row.duration_sec,description:row.description,blocks:[{duration_sec:warm.duration_sec},{duration_sec:main.duration_sec},{duration_sec:finish.duration_sec}]};
  check(matchesInstructions(value,candidate,{strength:dose,introductory_strength:intro}));return expected;
}

function checkProjectedWorkout(raw:Row) {
 const d=raw as unknown as StrengthWorkoutDose;
 check(d.schema_version==="strength-workout-dose-v0.1"&&d.rules_version==="strength-workout-policy-v0.1"&&d.load_increased===false&&d.one_rm_estimated===false&&d.personal_response_model_applied===false&&d.source_url===strengthWorkSource&&d.minimum_rir===3&&d.max_pattern_sets===7&&d.rest_between_sets_preserved===true&&Array.isArray(d.movements)&&d.movements.length>=2&&d.movements.length<=4);
 check(d.movements.filter(m=>m.role==="main").length===2&&new Set(d.movements.map(m=>m.exercise_id+":"+m.side)).size===d.movements.length);
 for(const m of d.movements){
  check(Number.isSafeInteger(m.work_sets)&&m.work_sets>=1&&m.work_sets<=(m.role==="main"?5:2)&&m.minimum_rir===3&&[120,180].includes(m.rest_seconds)&&["main","accessory"].includes(m.role)&&["assessment","workout_log"].includes(m.reference.kind)&&m.reference.set_id===m.reference_set.id&&m.reference_set.symptoms==="none"&&m.reference_set.technique==="stable");
  check(canonical(m.target)===canonical(Object.fromEntries(["repetitions","hold_seconds","load_kind","load_value","load_basis","load_note"].map(k=>[k,m.reference_set[k as keyof typeof m.reference_set]])))&&m.execution_seconds_per_set===Math.max(45,Math.trunc(Number(m.target.hold_seconds??0))*(m.side==="alternating"?2:1)));
  if(m.calibration_derivation){const v=m.calibration_derivation;check(m.reference_set.rir==="unknown"&&m.target.repetitions===Math.min(8,v.source_repetitions-2)&&v.planned_repetitions===m.target.repetitions&&v.observation_id===m.reference.set_id&&v.planned_minimum_rir===3&&v.one_rm_estimated===false&&v.personal_capacity_estimated===false&&m.rest_seconds===180);}
  else check(["3","4","5_plus"].includes(m.reference_set.rir));
 }
 for(const pattern of new Set(d.movements.map(m=>m.pattern)))check(d.movements.filter(m=>m.pattern===pattern).reduce((s,m)=>s+m.work_sets,0)<=7);
 const warm=d.movements.reduce((s,m)=>s+m.work_sets,0)>=6?600:300;
 check(d.warmup_seconds===warm&&d.cooldown_seconds===300&&d.work_seconds===workSeconds(d.movements)&&d.duration_sec===Math.max(1200,Math.ceil((warm+d.work_seconds+300)/300)*300)&&d.duration_sec<=4500&&d.desired_duration_sec>=d.duration_sec&&d.shortened_for_time===(d.duration_sec<d.desired_duration_sec));
}
