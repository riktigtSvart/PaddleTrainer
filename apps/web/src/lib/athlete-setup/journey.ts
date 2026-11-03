import type { Context, Profile } from "./contracts";
import type { ScheduleContext } from "@/lib/calendar/constraints";

export type SetupStep = {
  key: "profile" | "calendar" | "history";
  title: string;
  state: "ready" | "needed" | "optional";
  detail: string;
};
export function setupSteps(
  context: Context,
  schedule: ScheduleContext | null,
): SetupStep[] {
  const profile = context.profile?.artifact.proposal.data as
    | Profile
    | undefined;
  const open = context.current_review?.global_entry_gate === "OPEN";
  const equipment =
    !!profile?.resources.length ||
    !!schedule?.opportunities.some(
      (group) =>
        Array.isArray(group.constraints?.resources) &&
        group.constraints.resources.length > 0,
    );
  const opportunities =
    schedule?.opportunities.filter(
      (g) => g.known && (g.usable_minutes ?? 0) > 0,
    ).length ?? 0;
  const recurring =
    (!!schedule?.training_options_schedule_start_date &&
      (!schedule.training_options_schedule_end_date ||
        schedule.training_options_schedule_end_date >= context.local_today)) ||
    schedule?.data.rules.some(
      (r) =>
        r.details.kind === "available" &&
        r.repeat === "weekly" &&
        (!r.end_date || r.end_date >= context.local_today),
    );
  const observations =
    (profile?.manual_observations.length ?? 0) +
    (context.profile?.artifact.imported_observations?.length ?? 0);
  return [
    {
      key: "profile",
      title: "Rólad és a lehetőségeidről",
      state: open && equipment ? "ready" : "needed",
      detail: !context.profile
        ? "Alapadatok, sportmúlt, részvételi keret és eszközök. A bizonytalan adat külön jelölhető."
        : !open
          ? "A mentett felmérésben még tisztázandó adat vagy részvételi keret szerepel."
          : !equipment
            ? "A felmérés mentve. Add meg az általában elérhető eszközöket is."
            : "A kiinduló keret és az eszközlista mentve.",
    },
    {
      key: "calendar",
      title: "Mikor érsz rá?",
      state: opportunities || recurring ? "ready" : "needed",
      detail: recurring
        ? `Heti megállapodás mentve; a megadott érvényesség szerint ismétlődik. A következő 7 napban ${opportunities} használható időablak látszik.`
        : opportunities
          ? `${opportunities} használható időablak a következő 7 napban. Heti ismétlődés is megadható.`
          : "Add meg a szokásos hetedet. A kivételeket később a Napirendben módosíthatod.",
    },
    {
      key: "history",
      title: "Előzmények és visszajelzések",
      state: observations ? "ready" : "optional",
      detail: observations
        ? `${observations} kiválasztott vagy kézzel rögzített megfigyelés. A teljesített edzések időbecsléshez közvetlenül is felhasználhatók.`
        : "A teljesített edzésekből becslés készülhet. További mérésekkel pontosíthatsz; egy egyszerű kezdőmintához nem kell minden mérést kitölteni.",
    },
  ];
}
