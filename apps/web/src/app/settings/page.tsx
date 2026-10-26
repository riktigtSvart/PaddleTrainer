import Link from "next/link";
import ThemeControl from "@/components/ui/theme-control";
export const metadata = { title: "Beállítások" };
export default function SettingsPage() {
  return (
    <main className="pt-settings">
      <h1>Személyes beállítások</h1>
      <section className="pt-panel">
        <h2>Megjelenés</h2>
        <p>
          Válassz témát, vagy kövesd a rendszer beállítását. A választást ez a
          böngésző megjegyzi.
        </p>
        <ThemeControl />
      </section>
      <section className="pt-panel">
        <h2>Sportolói háttér és adatátvétel</h2>
        <p>
          A sportmúlt, a korlátozások, az edzéslehetőségek és az órás előzmények
          a profilban kezelhetők.
        </p>
        <Link className="pt-button" href="/athlete-setup">
          Sportolói profil és előzmények
        </Link>
      </section>
      <section className="pt-panel" id="data-connections">
        <h2>Órás adatkapcsolatok</h2>
        <p>
          A fejléc adatkapcsolati ikonjával minden oldalon megnézheted az
          állapotot, és elindíthatod a Polar-edzések és edzéstervek frissítését.
        </p>
        <p>
          A mai napot is tartalmazó gyors frissítés az alapadatokat veszi át. Az
          alvás, aktivitás és egyéb állapotadatok átvétele a profil Előzmények
          lapján érhető el.
        </p>
        <p>
          Garmin és Suunto: előkészített bővítési lehetőség; ezekhez még nincs
          bekötött kapcsolat.
        </p>
      </section>
      <section className="pt-panel">
        <h2>Naptárkapcsolatok</h2>
        <p>
          Google Calendar, Microsoft 365 és iCloud kapcsolatok: tervezett
          integráció. Jelenleg nincs külső naptár összekapcsolva ezen a
          felületen.
        </p>
      </section>
      <details className="pt-panel">
        <summary>Táplálkozási feltételek · későbbi modul</summary>
        <p>
          Az étrendi kizárások, preferenciák, étkezési idősávok és főzési
          lehetőségek itt lesznek megadhatók.
        </p>
      </details>
      <details className="pt-panel">
        <summary>Boltok és márkák · későbbi modul</summary>
        <p>
          Kijelölt boltok, kerülendő márkák, helyettesítések és beszerzési
          szempontok.
        </p>
      </details>
    </main>
  );
}
