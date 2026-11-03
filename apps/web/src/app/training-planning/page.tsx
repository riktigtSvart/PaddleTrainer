import PlanningJourney from "@/components/training-planning/journey";
export const dynamic = "force-dynamic";
export const metadata = { title: "Edzéstervezés" };
export default function TrainingPlanningPage() {
  return (
    <main className="pt-training-page">
      <header>
        <h1>Edzéstervezés</h1>
        <p>
          A mentett kiindulóponttól a konkrét edzéstervig, lépésről lépésre.
        </p>
      </header>
      <PlanningJourney />
    </main>
  );
}
