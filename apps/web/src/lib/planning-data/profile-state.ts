import { canonical } from "@/lib/planning-cycles/contracts";
import { domains, emptyProfile } from "@/lib/athlete-setup/contracts";
import type { Context, PendingQueue, Profile, Review } from "@/lib/athlete-setup/contracts";

const personalFields: (keyof Profile)[] = ["birth_date", "sex_reference", "body_mass_kg", "height_cm", "body_measurements_recorded_on", "body_mass_recorded_on"];
export function editingProfile(context: Context): Profile {
  const value = structuredClone(context.profile?.artifact.proposal.data as Profile | undefined ?? emptyProfile());
  const mass = context.body_mass?.current;
  if (mass) { value.body_mass_kg = mass.value_kg; value.body_mass_recorded_on = mass.recorded_on; }
  return value;
}
const sportFields: (keyof Profile)[] = [
  "target_sport", "sport_history_status", "sport_history", "competition_category",
  "constraint_status", "constraints", "participation", "interruption", "last_training_date",
  "typical_days_per_week", "typical_minutes_per_week", "resources", "duration_doubling_slowdown_pct",
  "accessibility_needs", "recovery_notes",
];
const historyFields: (keyof Profile)[] = ["manual_observations", "source_selections", "source_window"];
export type ProfileSection = "all" | "personal" | "sports" | "history";
export function sectionProfile(draft: Profile, saved: Profile | null | undefined, section: ProfileSection): Profile {
  if (section === "all") return structuredClone(draft);
  const result = structuredClone(saved ?? emptyProfile());
  for (const key of [...new Set([...Object.keys(draft), ...Object.keys(result)])] as (keyof Profile)[]) {
    const selected = section === "sports" ? sportFields.includes(key) : section === "history" ? historyFields.includes(key) : personalFields.includes(key);
    if (selected) {
      if (Object.hasOwn(draft, key)) Object.assign(result, { [key]: structuredClone(draft[key]) });
      else delete result[key];
    }
  }
  return result;
}
export type ProfileEditState = { personal: boolean; sports: boolean; history: boolean; profilePending: boolean; saving: boolean };

export function profileChanges(draft: Profile, saved?: Profile | null) {
  const before = saved ?? emptyProfile();
  const changed = (key: keyof Profile) => canonical(draft[key] ?? null) !== canonical(before[key] ?? null);
  return {
    personal: personalFields.some(changed),
    sports: sportFields.some(changed),
    history: historyFields.some(changed),
  };
}

// An exact retry can finish an earlier snapshot while the athlete is editing a
// newer draft. Keep only those fields the athlete changed against the old base.
export function retainProfileEdits(committed: Profile, draft: Profile, previous?: Profile | null): Profile {
  const result = structuredClone(committed), base = previous ?? emptyProfile();
  for (const key of Object.keys(draft) as (keyof Profile)[]) {
    if (canonical(draft[key] ?? null) !== canonical(base[key] ?? null)) {
      Object.assign(result, { [key]: structuredClone(draft[key]) });
    }
  }
  return result;
}

export function profileReadiness(profile: Profile | undefined, review: Review | null | undefined) {
  if (!profile || !review) return { personal: false, sports: false };
  const personal = !!profile.birth_date && !review.reasons.includes("AGE_UNKNOWN");
  const sports = !!profile.target_sport.trim() && profile.sport_history_status !== "unknown" && profile.constraint_status !== "unknown" &&
    !["unknown", "paused", "professional_review"].includes(profile.participation) &&
    review.reasons.every((code) => code === "AGE_UNKNOWN");
  return { personal, sports };
}

export function pendingDescription(queue: PendingQueue, busy = false) {
  const operations = [...new Set(queue.items.map((item) => item.operation))];
  if (operations.length > 1) return {
    title: busy ? "Korábbi műveletek befejezése folyamatban" : "Korábbi mentés és adatátvétel vár befejezésre",
    detail: "A félbemaradt műveletek az eredeti adatokkal folytathatók. A közben szerkesztett mezők megmaradnak; az új változtatásokat utána külön mentsd el.",
    action: "Korábbi műveletek folytatása",
  };
  if (operations.length === 1 && operations[0] === "polar-imports") {
    const first = JSON.parse(queue.items[0].body) as { day: string; domain: keyof typeof domains };
    return {
      title: busy ? "Órás adatok átvétele folyamatban" : "Egy korábbi órás adatátvétel még nem fejeződött be",
      detail: `${domains[first.domain]} · ${first.day}${queue.items.length > 1 ? ` · még ${queue.items.length} napi lekérés` : ""}. A már átvett adatok megmaradnak.`,
      action: "Adatátvétel folytatása",
    };
  }
  const availability = operations.length === 1 && operations[0] === "availability";
  return {
    title: busy ? "Mentés folyamatban" : availability ? "Az edzésidők korábbi mentése még ellenőrzésre vár" : "A személyes adatok és sportelőélet korábbi mentése még ellenőrzésre vár",
    detail: "A szerver visszaigazolása még hiányzik. A folytatás az eredeti mentést ellenőrzi. A mezőket közben szerkesztheted; az új változtatásokat utána külön mentsd el.",
    action: "Mentés ellenőrzése és folytatása",
  };
}
