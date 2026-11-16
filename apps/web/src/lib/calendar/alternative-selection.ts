import {canonical} from '@/lib/planning-cycles/contracts';
import {reviewTraining, chooseTraining} from '@/lib/planning-cycles/training-plan';
import type {Candidate, TrainingReview, TrainingPending} from '@/lib/planning-cycles/training-plan';
import type {Reference} from '@/lib/planning-cycles/contracts';
import type {FocusWorkout} from './training-alternatives';
import {focusedChoices} from './training-alternatives';
import {workoutVariant} from './alternative-variants';
import {alternativeExpired} from '@/lib/planning-cycles/alternative-availability';

export type PickerIdentity={owner:string;reference:Reference;zone:string};
export class AlternativesChanged extends Error {
  constructor(public review:TrainingReview) {super('Ez a változat közben megváltozott vagy már nem fér bele. Válassz a friss listából.');}
}
export function loadWorkoutAlternatives(expected:PickerIdentity,target:FocusWorkout,signal?:AbortSignal) {
  return reviewTraining(expected,target.date,target.date,signal,undefined,undefined,{
    schema_version:'workout-alternatives-request-v0.1',workout_id:target.id,expected_workout_hash:target.workout_hash,
  });
}
export function assertDaySelection(review:TrainingReview,target:FocusWorkout) {
  const scope=review.alternatives_for;
  if(!scope||scope.workout_id!==target.id||scope.expected_workout_hash!==target.workout_hash||
    review.start_date!==target.date||review.end_date!==target.date||!focusedChoices(review,target)||
    review.result.blockers.length||review.result.cancel.length!==1||review.result.cancel[0]!==target.id||
    review.result.create.length!==1||review.result.create[0].date!==target.date)throw Error('Az adott nap edzéscseréje most nem menthető. Frissítsd a lehetőségeket.');
}
/** A click may refresh the time, never silently substitute another dose. */
export async function prepareDaySelection(expected:PickerIdentity,target:FocusWorkout,displayed:TrainingReview,clicked:Candidate) {
  const fresh=await loadWorkoutAlternatives(expected,target);
  const focus=focusedChoices(fresh,target),oldMeta=displayed.result.prescription_context?.by_candidate[clicked.candidate_key];
  const wanted=canonical(workoutVariant(clicked as unknown as Record<string,unknown>,(oldMeta??{}) as unknown as Record<string,unknown>));
  const match=focus?.group?.candidates.find(c=>c.opportunity_key===clicked.opportunity_key&&!alternativeExpired(fresh,c,Date.now())&&
    canonical(workoutVariant(c as unknown as Record<string,unknown>,(fresh.result.prescription_context?.by_candidate[c.candidate_key]??{}) as unknown as Record<string,unknown>))===wanted);
  if(!match)throw new AlternativesChanged(fresh);
  const chosen=await chooseTraining(expected,fresh,target.date,match.candidate_key);
  assertDaySelection(chosen,target);
  return chosen;
}
export function selectionRequest(expected:PickerIdentity,target:FocusWorkout,chosen:TrainingReview):TrainingPending {
  assertDaySelection(chosen,target);
  return {owner:expected.owner,program:expected.reference.artifact_id,operation:'accept',body:JSON.stringify({
    request_id:crypto.randomUUID(),review_reference:{artifact_id:chosen.artifact_id,content_hash:chosen.content_hash},acknowledge_reviewed_plan:true,
  })};
}
