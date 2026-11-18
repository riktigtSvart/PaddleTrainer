import { object, sha } from '@/lib/planning-cycles/contracts';
import { civilDay } from './contracts';
import { ensure } from './journal';

export const nutrientDetails = {
  energy: ['Energia', 'kcal'],
  protein: ['Fehérje', 'g'],
  carbohydrate: ['Szénhidrát', 'g'],
  fat: ['Zsír', 'g'],
  fiber: ['Rost', 'g'],
  calcium: ['Kalcium', 'mg'],
  iron: ['Vas', 'mg'],
  magnesium: ['Magnézium', 'mg'],
  zinc: ['Cink', 'mg'],
  iodine: ['Jód', 'µg'],
  selenium: ['Szelén', 'µg'],
  b12: ['B₁₂-vitamin', 'µg'],
  folate: ['Folát', 'µg DFE'],
  vitamin_d: ['D-vitamin', 'µg'],
  vitamin_c: ['C-vitamin', 'mg'],
  potassium: ['Kálium', 'mg'],
} as const;

export type Nutrient = keyof typeof nutrientDetails;
type Band = [string, string];
type Reference = {
  minimum: string | null;
  maximum: string | null;
  source: 'efsa' | 'sport' | 'sport_strength' | 'energy_model' | 'assessment';
  scope: 'food_only' | 'total_intake' | null;
  source_name?: string;
  assessed_on?: string;
  valid_until?: string | null;
};
type Amount = { amount: string | null; partial: boolean };
type Intake = { entries: number; unquantified: number; amounts: Record<Nutrient, Amount> };
export type DayRequirements = {
  date: string;
  baseline_kcal: string | null;
  maintenance_kcal: Band | null;
  body_mass_on: string | null;
  missing_profile: ('adult_age' | 'sex_reference' | 'height' | 'body_mass')[];
  workouts: { planned: number; recorded: number; missing_duration: number; unestimated: number;
    seconds: number; endurance_seconds: number; extra_kcal: Band | null };
  references: Partial<Record<Nutrient, Reference>>;
  planned: Intake;
  logged: Intake;
};

export type Requirements = {
  schema_version: 'nutrition-requirements-v0.1';
  athlete_id: string;
  start_date: string;
  end_date: string;
  timezone: string;
  read_only: true;
  body_goal: 'weight_loss' | 'weight_gain' | 'weight_maintenance' | 'recomposition' | null;
  muscle_goal: 'unspecified' | 'maintain' | 'gain';
  performance_goal: 'unspecified' | 'strength' | 'endurance' | 'wellbeing';
  days: DayRequirements[];
  content_hash: string;
};

const nutrients = Object.keys(nutrientDetails) as Nutrient[];
const unavailable = 'A napi tápanyagszámítás nem tölthető be.';
const decimal = (x: unknown): x is string => typeof x === 'string' && /^\d{1,18}(\.\d{1,3})?$/.test(x);
const count = (x: unknown): x is number => typeof x === 'number' && Number.isSafeInteger(x) && x >= 0;
const band = (x: unknown) => Array.isArray(x) && x.length === 2 && x.every(decimal) && Number(x[0]) <= Number(x[1]);

function validateIntake(input: unknown) {
  const value = object(input), amounts = object(value.amounts);
  ensure(count(value.entries) && count(value.unquantified) && value.unquantified <= value.entries, unavailable);
  ensure(Object.keys(amounts).length === nutrients.length, unavailable);
  for (const key of nutrients) {
    const a = object(amounts[key]);
    ensure((decimal(a.amount) || a.amount === null) && typeof a.partial === 'boolean'
      && (value.entries > 0 || (a.amount === null && !a.partial))
      && (value.unquantified === 0 || a.partial), unavailable);
  }
}

export async function readRequirements(raw: unknown, owner: string, start: string, end: string): Promise<Requirements> {
  const v = object(raw), { content_hash, ...payload } = v;
  civilDay(start); civilDay(end);
  const length = (Date.parse(end) - Date.parse(start)) / 86400000 + 1;
  ensure(v.schema_version === 'nutrition-requirements-v0.1' && v.read_only === true && v.athlete_id === owner
    && v.start_date === start && v.end_date === end && length >= 1 && length <= 14
    && typeof v.timezone === 'string' && Array.isArray(v.days) && v.days.length === length, unavailable);
  const goals = v.body_goal === null || ['weight_loss', 'weight_gain', 'weight_maintenance', 'recomposition'].some(x => x === v.body_goal);
  ensure(goals && ['unspecified', 'maintain', 'gain'].some(x => x === v.muscle_goal)
    && ['unspecified', 'strength', 'endurance', 'wellbeing'].some(x => x === v.performance_goal), unavailable);
  ensure(await sha(payload) === content_hash, unavailable);
  for (const [index, input] of v.days.entries()) {
    const d = object(input), workouts = object(d.workouts);
    ensure(d.date === civilDay(start, index) && (decimal(d.baseline_kcal) || d.baseline_kcal === null)
      && (band(d.maintenance_kcal) || d.maintenance_kcal === null)
      && (d.body_mass_on === null || typeof d.body_mass_on === 'string' && civilDay(d.body_mass_on) === d.body_mass_on)
      && Array.isArray(d.missing_profile)
      && d.missing_profile.every(x => ['adult_age', 'sex_reference', 'height', 'body_mass'].includes(x)), unavailable);
    const { planned, recorded, missing_duration, unestimated, seconds, endurance_seconds } = workouts;
    ensure(count(planned) && count(recorded) && count(missing_duration) && count(unestimated)
      && count(seconds) && count(endurance_seconds) && endurance_seconds <= seconds
      && unestimated <= planned + recorded && missing_duration <= unestimated
      && (band(workouts.extra_kcal) || workouts.extra_kcal === null)
      && (d.maintenance_kcal === null || (d.baseline_kcal !== null && unestimated === 0)), unavailable);
    const references = object(d.references);
    for (const [key, input] of Object.entries(references)) {
      const r = object(input);
      ensure(nutrients.includes(key as Nutrient) && (decimal(r.minimum) || r.minimum === null)
        && (decimal(r.maximum) || r.maximum === null) && (r.minimum !== null || r.maximum !== null)
        && (r.minimum === null || r.maximum === null || Number(r.minimum) <= Number(r.maximum)), unavailable);
      if (r.source === 'assessment') {
        ensure((r.scope === 'food_only' || r.scope === 'total_intake')
          && typeof r.source_name === 'string' && r.source_name.length >= 1 && r.source_name.length <= 200
          && typeof r.assessed_on === 'string' && civilDay(r.assessed_on) <= (d.date as string)
          && (r.valid_until === null || typeof r.valid_until === 'string' && civilDay(r.valid_until) >= (d.date as string)), unavailable);
      } else {
        ensure(r.scope === null && ['efsa', 'sport', 'sport_strength', 'energy_model'].some(x => x === r.source), unavailable);
      }
    }
    validateIntake(d.planned);
    validateIntake(d.logged);
  }
  return v as unknown as Requirements;
}

export async function loadRequirements(owner: string, start: string, end: string, signal: AbortSignal) {
  const query = new URLSearchParams({ start_date: start, end_date: end });
  const response = await fetch('/api/goal-workflow/nutrition/requirements?' + query, { signal, cache: 'no-store' });
  ensure(response.ok, unavailable);
  return readRequirements(await response.json(), owner, start, end);
}
