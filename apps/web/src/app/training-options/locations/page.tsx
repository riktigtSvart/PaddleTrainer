import OptionsWorkspace from "@/components/training-options/workspace";
export const dynamic = "force-dynamic";
export const metadata = { title: "Helyszínek" };
export default function LocationsPage() {
  return (
    <main className="pt-training-page">
      <header>
        <h1>Edzési lehetőségek</h1>
        <p>Helyszínek és tartós lehetőségek · a konkrét hét ezekre épül.</p>
      </header>
      <OptionsWorkspace mode="locations" />
    </main>
  );
}
