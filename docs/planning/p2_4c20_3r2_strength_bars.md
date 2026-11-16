# C20.3.2 — Bordásfal és nyújtó / húzódzkodó keret

A helyszín erősítőfelszerelés-listája két képes, külön kijelölhető eszközzel bővül az **Alapfelszerelés és saját testsúly** csoportban:

- **Bordásfal**: függeszkedéshez is alkalmas, stabilan rögzített bordásfal. A külön húzódzkodó feltét külön megadható.
- **Nyújtó / húzódzkodó keret**: húzódzkodásra kialakított nyújtó, állvány vagy erre használható keret. Bordásfali húzódzkodó feltét is itt jelölhető.

A katalógus összesen **93 eszköztípust és 120 gyakorlatot** tartalmaz; az erősítőgépek száma továbbra is 45. Mindkét új eszközhöz saját, témához igazodó SVG ábra tartozik.

## Gyakorlatok és feltételek

| Gyakorlat | Eszközfeltétel |
| --- | --- |
| Húzódzkodás | Korábban megadott húzódzkodó rúd **vagy** nyújtó / húzódzkodó keret |
| Lapockahúzás függésben | Húzódzkodó rúd **vagy** nyújtó / húzódzkodó keret |
| Függeszkedésben térdemelés | Függeszkedésre alkalmas bordásfal **vagy** húzódzkodó rúd **vagy** nyújtó / keret |
| Függeszkedésben lábemelés | Függeszkedésre alkalmas bordásfal **vagy** húzódzkodó rúd **vagy** nyújtó / keret |
| Bordásfalnál kapaszkodásos guggolás | Bordásfal **és** szabad padlófelület |

A három utolsó gyakorlat új katalógustétel. A két meglévő húzódzkodásos gyakorlat a külön megadott keretet is elfogadja. Az eszközegyezés kizárólag a helyszín saját felszereléséből készül. Egy általános erőkeret vagy guggolókeret nem jelent automatikusan húzódzkodási lehetőséget; ezt külön be kell jelölni. A bordásfal kijelölése önmagában nem jelöl be húzódzkodó feltétet, gumiszalag-rögzítési pontot vagy más tartozékot.

## Meglévő adatok

A **Húzódzkodó rúd** korábbi neve, azonosítója és kijelölése változatlan. Nem szükséges újra felvenni vagy másik eszközre cserélni. A felhasználó a konkrét felszerelést választhatja: rúd, nyújtó / keret, vagy mindkettő, ha külön eszközök is vannak.

Az összes korábbi eszközdefiníció és a többi gyakorlat feltétele megmarad. A korábbi C20.3.1 katalógussal rögzített válasz és nyugta a saját befagyasztott adataival továbbra is ellenőrizhető. A helyszíni mentés és újrapróbálás formátuma, a 128-as eszközkorlát és a tervezési jogosultságok nem változnak.

Katalógusverzió: `2026-11-06`; séma: `strength-catalog-v0.1`. A katalógus a lehetőségeket egyezteti; nem ír elő személyes terhelést, és nem módosítja az erőedzés saját referenciafeltételeit. Nincs új útvonal, függőség vagy adatbázis-migráció.

## Forrás és ábrák

A bordásfal és a külön húzódzkodó kapaszkodó megkülönböztetésének gyártói forrása: [NOHRD WallBars](https://www.nohrd.com/uk/wallbars/). Az alkalmazás nem feltételezi egy konkrét gyártó opcionális tartozékainak meglétét. A két kártyakép eredeti, kódból rajzolt SVG; külső termékfotó és márkalogó nem kerül be.

## Ellenőrzés

Új backendtesztek ellenőrzik a húzódzkodási alternatívákat, a függeszkedő gyakorlatokat, a szükséges padlófelületet és a helyszínhez kötött mentést. A frontend valós HTTP-válaszból készült tesztadatot olvas, miközben a C20.3.1 tesztadat is változatlanul megmarad. A helyszínszerkesztő DOM-interakciója mindkét új kártyát kijelöli, szűrés és ki-be kapcsolás után is megőrzi, majd egyetlen kifejezett helyszínmentéssel rögzíti őket. A másik helyszín adatai megmaradnak.

Teljes ellenőrzés: `python tools/run_c20_3_2_checks.py --build`.
