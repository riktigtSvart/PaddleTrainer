import { canonical, object } from '@/lib/planning-cycles/contracts';
import { civilDay, readNutritionData } from './contracts';
import type { Catalog, NutritionData, Reference } from './contracts';
import { ensure } from './journal';
export const draftKey=(owner:string)=>`paddletrainer.nutrition.draft.v1:${owner}`;
export type Draft={schema_version:'nutrition-menu-draft-v0.1';owner:string;base_reference:Reference|null;data:NutritionData;pantry_inputs:Record<string,string>;start:string;count:number;people:number};
export const sameReference=(a:Reference|null,b:Reference|null)=>canonical(a)===canonical(b);
export function readDraft(raw:string,owner:string,c:Catalog):Draft {
  ensure(new TextEncoder().encode(raw).length<=150000);
  const v=object(JSON.parse(raw));ensure(v.schema_version==='nutrition-menu-draft-v0.1'&&v.owner===owner);
  readNutritionData(v.data,c);ensure(typeof v.start==='string');if(v.start!=='')civilDay(v.start);
  ensure(Number.isSafeInteger(v.count)&&Math.abs(Number(v.count))<=1000000&&Number.isSafeInteger(v.people)&&Math.abs(Number(v.people))<=1000000);
  if(v.base_reference!==null){const r=object(v.base_reference);ensure(/^pt-meals:[a-f0-9]{64}$/.test(String(r.artifact_id))&&/^[a-f0-9]{64}$/.test(String(r.content_hash)));}
  const pantry=object(v.pantry_inputs);ensure(Object.keys(pantry).length<=100&&Object.entries(pantry).every(([id,s])=>c.foods.some(f=>f.id===id)&&typeof s==='string'&&s.length<=100));
  return v as unknown as Draft;
}
