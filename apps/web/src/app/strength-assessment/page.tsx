import GuidedWorkspace from "@/components/guided-strength/workspace";
export const dynamic = "force-dynamic";
export const metadata = { title: "Vezetett kezdő erőfelmérés" };
export default function StrengthAssessmentPage() {
  return (
    <main className="pt-training-page">
      <header>
        <h1>Vezetett kezdő erőfelmérés</h1>
        <p>
          Egy valódi, könnyű felmérőalkalom: bemelegítés, ismert gyakorlatok,
          tényleges sorozatok és menthető eredmények. Az adatokat kézzel adod
          meg; a felmérés egy szokásos erősítő edzés része is lehet.
        </p>
      </header>
      <GuidedWorkspace />
    </main>
  );
}
