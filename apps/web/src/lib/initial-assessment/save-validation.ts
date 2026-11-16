import { normalizeData } from "./contracts";
import { day } from "@/lib/planning-cycles/contracts";
import type { Data } from "./contracts";
export class AssessmentSaveInputError extends Error {
  constructor(message: string, public step: number) { super(message); }
}
export function assessmentSaveData(data: Data, today: string): Data {
  try { day(data.assessment_date); if (data.assessment_date < "1900-01-01" || data.assessment_date > "2100-12-31") throw Error(); }
  catch { throw new AssessmentSaveInputError("Adj meg érvényes dátumot a felméréshez az 1. lépésben.", 0); }
  if (data.assessment_date > today) throw new AssessmentSaveInputError("A felmérés dátuma nem lehet jövőbeli. Ellenőrizd a dátumot az 1. lépésben.", 0);
  const observed = [data.last_strength_date, ...data.exercises.map(e => e.performed_on), ...data.sport_references.map(r => r.performed_on)]
    .filter((v): v is string => typeof v === "string").sort().at(-1);
  if (observed && observed > data.assessment_date) throw new AssessmentSaveInputError(
    `A felmérés dátuma (${data.assessment_date}) korábbi egy rögzített teljesítésnél (${observed}). Ellenőrizd a felmérés dátumát az 1. lépésben. A gyakorlatok eredményei megmaradtak.`, 0);
  return normalizeData(data);
}
