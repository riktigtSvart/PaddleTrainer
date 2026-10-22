import Link from "next/link";
import type { Metadata } from "next";
import GoalWorkspace from "@/components/planning-goals/workspace";

export const metadata: Metadata = {
  title: "Célok és mérések · PaddleTrainer",
  description: "Cikluscélok, mérési protokollok, eredmények és célértékelések.",
};
export default async function PlanningGoalsPage({
  searchParams,
}: {
  searchParams: Promise<{ period?: string | string[] }>;
}) {
  const { period } = await searchParams;
  const initialPeriod =
    typeof period === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
      period,
    )
      ? period
      : "";
  return (
    <main
      lang="hu"
      className="min-h-screen bg-zinc-950 px-4 py-8 text-zinc-100 sm:px-6 sm:py-10"
    >
      <div className="mx-auto max-w-5xl">
        <Link href="/" className="text-sm text-zinc-300 hover:text-teal-200">
          ← Coach
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
        <GoalWorkspace initialPeriod={initialPeriod} />
      </div>
    </main>
  );
}
