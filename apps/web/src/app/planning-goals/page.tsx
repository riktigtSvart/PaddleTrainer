import Link from "next/link";
import DevelopmentNavigation from "@/components/ui/development-navigation";
import type { Metadata } from "next";
import GoalWorkspace from "@/components/planning-goals/workspace";

export const metadata: Metadata = {
  title: "Célok és mérések · PaddleTrainer",
  description: "Cikluscélok, mérési protokollok, eredmények és célértékelések.",
};
export default async function PlanningGoalsPage({
  searchParams,
}: {
  searchParams: Promise<{
    period?: string | string[];
    cycle?: string | string[];
  }>;
}) {
  const { period, cycle } = await searchParams;
  const initialCycle =
    typeof cycle === "string" && /^pt-cycle:[0-9a-f]{64}$/.test(cycle)
      ? cycle
      : "";
  const initialPeriod =
    typeof period === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
      period,
    )
      ? period
      : "";
  return (
    <main lang="hu" className="pt-development-page">
      <div className="pt-development-body">
        <DevelopmentNavigation />
        <Link href="/" className="text-sm text-zinc-300 hover:text-teal-200">
          ← Napirend
        </Link>
        <header className="my-8">
          <p className="text-sm text-teal-200">PaddleTrainer · Cikluscélok</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
            Célok és mérések
          </h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-zinc-300">
            Előre rögzített célok. Megőrzött mérési körülmények. Értelmezhető
            változás.
          </p>
        </header>
        <GoalWorkspace
          initialPeriod={initialPeriod}
          initialCycle={initialCycle}
        />
      </div>
    </main>
  );
}
