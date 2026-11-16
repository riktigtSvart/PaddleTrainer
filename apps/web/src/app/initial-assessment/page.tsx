import AssessmentWorkspace from "@/components/initial-assessment/workspace";
export const dynamic = "force-dynamic";
export const metadata = { title: "Kezdeti sportági és erőfelmérés" };
export default function InitialAssessmentPage() {
  return (
    <main className="pt-training-page">
      <header>
        <h1>Kezdeti sportági és erőfelmérés</h1>
        <p>
          Közös kiindulópont, fő- és kiegészítő sportágak, gyakorlatonkénti
          jártasság és saját referenciák.
        </p>
      </header>
      <AssessmentWorkspace />
    </main>
  );
}
