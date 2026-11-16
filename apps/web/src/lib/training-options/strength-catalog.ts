import { object, sha, canonical } from "@/lib/planning-cycles/contracts";

export type StrengthEquipment = {
  id: string;
  label: string;
  resource: string;
  category: string;
  illustration: string;
  aliases: string[];
  hint: string;
};
export type StrengthExercise = {
  id: string;
  label: string;
  english: string;
  movement: string;
  requirements: string[][];
  guide_id: string | null;
};
export type StrengthCatalog = {
  schema_version: "strength-catalog-v0.1";
  version: string;
  scope: "equipment_and_exercise_inventory";
  planning_authorized: false;
  workouts_changed: false;
  content_hash: string;
  categories: { id: string; label: string }[];
  movements: { id: string; label: string }[];
  equipment: StrengthEquipment[];
  exercises: StrengthExercise[];
  guides: {
    id: string;
    title: string;
    src: string;
    page: number;
    width: number;
    height: number;
  }[];
  sources: { title: string; url: string | null }[];
};
export type StrengthOptions = {
  location_id: string;
  equipment_ids: string[];
  exercise_ids: string[];
  planning_authorized: false;
  declared_exercise_ids?: string[];
  equipment_exercise_ids?: string[];
};
const invalid = () =>
  Error(
    "Az erősítőeszköz-katalógus vagy a helyszíni eszközegyezés nem ellenőrizhető.",
  );
const identifier = (value: unknown) =>
  typeof value === "string" && /^[a-z][a-z0-9_-]{0,63}$/.test(value);
const label = (value: unknown, max = 200) =>
  typeof value === "string" &&
  value.length > 0 &&
  value.length <= max &&
  value === value.trim();
function entries(value: unknown, max: number) {
  if (!Array.isArray(value) || value.length < 1 || value.length > max)
    throw invalid();
  return value.map(object);
}
export async function readStrengthCatalog(
  value: unknown,
): Promise<StrengthCatalog> {
  const c = object(value),
    { content_hash, ...body } = c;
  if (
    c.schema_version !== "strength-catalog-v0.1" ||
    c.scope !== "equipment_and_exercise_inventory" ||
    c.planning_authorized !== false ||
    c.workouts_changed !== false ||
    !label(c.version, 32) ||
    (await sha(body)) !== content_hash
  )
    throw invalid();
  const categories = entries(c.categories, 24),
    movements = entries(c.movements, 24),
    equipment = entries(c.equipment, 128),
    exercises = entries(c.exercises, 256),
    guides = entries(c.guides, 16);
  for (const values of [categories, movements, equipment, exercises, guides]) {
    const ids = new Set();
    for (const item of values) {
      if (!identifier(item.id) || ids.has(item.id)) throw invalid();
      ids.add(item.id);
    }
  }
  for (const item of [...categories, ...movements])
    if (!label(item.label, 100)) throw invalid();
  const aliases = new Map<string, string>();
  for (const item of equipment) {
    if (
      !label(item.label, 100) ||
      item.resource !== item.label ||
      !categories.some((v) => v.id === item.category) ||
      !identifier(item.illustration) ||
      !label(item.hint, 300) ||
      !Array.isArray(item.aliases) ||
      item.aliases.length > 16 ||
      item.aliases.some((a) => !label(a, 100))
    )
      throw invalid();
    for (const value of [item.resource, ...item.aliases]) {
      const key = normalize(String(value));
      if (aliases.has(key) && aliases.get(key) !== item.id) throw invalid();
      aliases.set(key, String(item.id));
    }
  }
  for (const item of guides)
    if (
      !label(item.title, 100) ||
      item.src !== `/strength-guides/${item.id}.png` ||
      !Number.isInteger(item.page) ||
      Number(item.page) < 1 ||
      Number(item.page) > 16 ||
      !Number.isInteger(item.width) ||
      !Number.isInteger(item.height) ||
      Number(item.width) < 1 ||
      Number(item.width) > 10000 ||
      Number(item.height) < 1 ||
      Number(item.height) > 10000
    )
      throw invalid();
  for (const item of exercises) {
    if (
      !label(item.label, 120) ||
      typeof item.english !== "string" ||
      item.english.length > 120 ||
      !movements.some((v) => v.id === item.movement) ||
      (item.guide_id !== null && !guides.some((g) => g.id === item.guide_id)) ||
      !Array.isArray(item.requirements) ||
      item.requirements.length < 1 ||
      item.requirements.length > 8
    )
      throw invalid();
    for (const group of item.requirements)
      if (
        !Array.isArray(group) ||
        group.length < 1 ||
        group.length > 8 ||
        new Set(group).size !== group.length ||
        group.some((id) => !equipment.some((e) => e.id === id))
      )
        throw invalid();
  }
  if (!Array.isArray(c.sources) || c.sources.length > 16) throw invalid();
  for (const value of c.sources) {
    const source = object(value);
    if (
      !label(source.title, 200) ||
      (source.url !== null &&
        (typeof source.url !== "string" ||
          !/^https:\/\/((www\.)?(acefitness\.org|nasm\.org|eleiko\.com|lifefitness\.com|nohrd\.com)|support\.lifefitness\.com)\//.test(
            source.url,
          )))
    )
      throw invalid();
  }
  return c as unknown as StrengthCatalog;
}
const normalize = (value: string) => value.trim().toLocaleLowerCase("hu");
export function selectedEquipment(
  catalog: StrengthCatalog,
  resources: string[],
) {
  const available = new Set(resources.map(normalize));
  return catalog.equipment.filter((e) =>
    [e.resource, ...e.aliases].some((v) => available.has(normalize(v))),
  );
}
export function managedResource(catalog: StrengthCatalog, value: string) {
  return selectedEquipment(catalog, [value]).length > 0;
}
export function toggleEquipment(
  catalog: StrengthCatalog,
  resources: string[],
  id: string,
  checked: boolean,
) {
  const item = catalog.equipment.find((e) => e.id === id);
  if (!item) throw invalid();
  const names = new Set([item.resource, ...item.aliases].map(normalize));
  if (checked)
    return resources.some((r) => names.has(normalize(r)))
      ? [...resources]
      : [...resources, item.resource];
  return resources.filter((r) => !names.has(normalize(r)));
}
export function matchingExercises(
  catalog: StrengthCatalog,
  resources: string[],
) {
  const available = new Set(
    selectedEquipment(catalog, resources).map((e) => e.id),
  );
  return catalog.exercises.filter((e) =>
    e.requirements.some((group) => group.every((id) => available.has(id))),
  );
}
export type ExerciseLocation = {
  id: string;
  sports: string[];
  resources: string[];
  archived: boolean;
  exercise_confirmations?: {
    exercise_id: string;
    source_kind: "self_report";
    note: string;
  }[];
};
export function declaredExercises(
  catalog: StrengthCatalog,
  place: ExerciseLocation,
) {
  const declared = place.exercise_confirmations ?? [],
    ids = new Set<string>();
  for (const c of declared) {
    if (
      ids.has(c.exercise_id) ||
      c.source_kind !== "self_report" ||
      !catalog.exercises.some((e) => e.id === c.exercise_id)
    )
      throw invalid();
    ids.add(c.exercise_id);
  }
  return place.archived || !place.sports.includes("STRENGTH")
    ? []
    : catalog.exercises.filter((e) => ids.has(e.id));
}
export function availableExercises(
  catalog: StrengthCatalog,
  place: ExerciseLocation,
  resources = place.resources,
) {
  const declared = declaredExercises(catalog, place);
  if (place.archived || !place.sports.includes("STRENGTH")) return [];
  const ids = new Set(
    [...matchingExercises(catalog, resources), ...declared].map((e) => e.id),
  );
  return catalog.exercises.filter((e) => ids.has(e.id));
}
export function equipmentGaps(
  catalog: StrengthCatalog,
  id: string,
  resources: string[],
) {
  const exercise = catalog.exercises.find((e) => e.id === id),
    have = new Set(selectedEquipment(catalog, resources).map((e) => e.id));
  return (exercise?.requirements ?? []).map((group) =>
    group
      .filter((id) => !have.has(id))
      .map((id) => catalog.equipment.find((e) => e.id === id)?.label ?? id),
  );
}
export function expectedStrengthOptions(
  catalog: StrengthCatalog,
  locations: ExerciseLocation[],
): StrengthOptions[] {
  return locations
    .filter((l) => !l.archived && l.sports.includes("STRENGTH"))
    .map((l) => ({
      location_id: l.id,
      equipment_ids: selectedEquipment(catalog, l.resources).map((e) => e.id),
      exercise_ids: availableExercises(catalog, l).map((e) => e.id),
      planning_authorized: false,
      ...(l.exercise_confirmations !== undefined
        ? {
            declared_exercise_ids: declaredExercises(catalog, l).map(
              (e) => e.id,
            ),
            equipment_exercise_ids: matchingExercises(catalog, l.resources).map(
              (e) => e.id,
            ),
          }
        : {}),
    }));
}
export function validateStrengthOptions(
  catalog: StrengthCatalog,
  locations: Parameters<typeof expectedStrengthOptions>[1],
  value: unknown,
) {
  if (
    canonical(value) !== canonical(expectedStrengthOptions(catalog, locations))
  )
    throw invalid();
}
