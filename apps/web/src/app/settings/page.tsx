import Link from "next/link";
import ThemeControl from "@/components/ui/theme-control";
import DataConnectionsControl from "@/components/ui/data-connections-control";
import PolarHistoryControl from "@/components/ui/polar-history-control";
export const metadata = { title: "Általános beállítások" };
export default function SettingsPage() {
  return <main className="pt-settings"><h1>Általános beállítások</h1>
    <section className="pt-panel" id="appearance"><h2>Megjelenés / téma</h2><p>Kövesd a rendszer témáját, vagy válassz világos vagy sötét megjelenést. A választást ez a böngésző megjegyzi.</p><ThemeControl /></section>
    <section className="pt-panel" id="data-connections"><h2>Sportórák és adatkapcsolatok</h2><p>A frissítés gomb az alapértelmezett eszközről tölt. A mellette nyíló menüben ellenőrizheted a kapcsolatot, a lekért adatokat és az időszakot.</p><DataConnectionsControl /><p>Jelenleg a Polar-kapcsolat működik. A Garmin és a Suunto későbbi bekötésre előkészített lehetőség.</p><div className="pt-context-links"><Link href="/training-planning#assessment">Órás előzmények és mérések átvétele</Link></div></section>
    <PolarHistoryControl />
    <section className="pt-panel" id="calendar-connections"><h2>Naptárkapcsolatok</h2><p>Google Calendar, Microsoft 365 és iCloud: későbbi integráció. Az elfoglaltságokat jelenleg a naptárban, kézzel adhatod meg.</p></section>
    <section className="pt-panel" id="language"><h2>Nyelv</h2><p>A nyelvválasztás és a rendszer nyelvének követése későbbi lehetőség. A jelenlegi felület magyarul érhető el.</p></section>
  </main>;
}
