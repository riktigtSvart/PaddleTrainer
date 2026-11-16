import BodyWorkspace from "@/components/nutrition/body-workspace";
export const metadata = { title: "Táplálkozási opciók" };
export default function NutritionPage() {
  return <main className="pt-settings"><h1>Táplálkozási opciók</h1><p className="pt-options-meta">Testsúlycélok és dátumozott testtömegmérések. Az étrendtervezés későbbi modul.</p><BodyWorkspace />
    <section className="pt-panel" id="preferences"><h2>Preferenciák és igények</h2><p>Étrend, ételérzékenységek, kedvelt és kerülendő ételek, vegetáriánus vagy vegán választás. Testsúlycél: fogyás, súlytartás, hízás vagy testösszetétel javítása azonos súly mellett.</p><p>A testtömeg a közös mérési előzményből származik.</p></section>
    <section className="pt-panel" id="shopping-options"><h2>Bevásárlási lehetőségek</h2><p>A működő modulhoz preferált boltok kijelölése szükséges majd; a kedvelt vagy kerülendő márkák megadása opcionális lesz.</p></section>
  </main>;
}
