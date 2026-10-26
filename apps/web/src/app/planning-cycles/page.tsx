import Link from "next/link";
import CycleWorkspace from "@/components/planning-cycles/workspace";

export const dynamic = "force-dynamic";

export default function PlanningCyclesPage() {
  return (
    <main className="mx-auto max-w-6xl space-y-8 px-5 py-7 sm:px-8 sm:py-10">
      <Link href="/" className="text-sm text-zinc-300 hover:text-teal-200">
        ← Napirend
      </Link>
      <header className="space-y-3">
        <p className="text-sm text-teal-200">
          PaddleTrainer · Felkészülés tervezése
        </p>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Felkészülés és ciklusok
        </h1>
        <p className="max-w-3xl text-base leading-7 text-zinc-300">
          Indulj a célodból. Állítsd össze az időkeretet, majd tekintsd át a
          hozzá tartozó makro- és mezociklusokat.
        </p>
      </header>
      <CycleWorkspace />
    </main>
  );
}
