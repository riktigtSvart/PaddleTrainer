import Link from "next/link";
export const metadata = { title: "Bevásárlás" };
export default function ShoppingPage() {
  return (
    <main className="pt-settings">
      <h1>Bevásárlás</h1>
      <section className="pt-panel">
        <h2>Étrendhez kapcsolódó bevásárlólista</h2>
        <p>
          Ez a modul később készül el. A kiválasztott napok étrendjéből, az
          otthoni készletből és a kijelölt boltok kínálatából áll majd össze a
          lista.
        </p>
        <Link className="pt-button" href="/settings">
          Személyes beállítások
        </Link>
      </section>
    </main>
  );
}
