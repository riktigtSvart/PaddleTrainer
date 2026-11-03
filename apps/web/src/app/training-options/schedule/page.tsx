import OptionsWorkspace from "@/components/training-options/workspace";
export const dynamic = "force-dynamic";
export const metadata = { title: "Általános órarend" };
export default function SchedulePage() {
  return (
    <main className="pt-training-page">
      <header>
        <h1>Edzési lehetőségek</h1>
        <p>
          Amíg nem adsz meg eltérést, a mentett általános órarend szerint érsz
          rá.
        </p>
      </header>
      <OptionsWorkspace mode="schedule" />
    </main>
  );
}
