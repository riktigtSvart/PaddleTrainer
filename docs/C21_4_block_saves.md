# C21.4 — Blokkonkénti mentés és a személyes adatok visszaigazolása

C21.3 után telepíthető frontendfrissítés. A backend, az adatbázis és a tárolt bizonylatok adatformátuma változatlan.

## A megakadt profilmentés javítása

A korábbi felület a küldött kérés és a szerver által tárolt adat minden eltérését másik kérésként kezelte. A szerver azonban a saját, zárt adatmodellje szerint kitölti a hiányzó alapértékeket és levágja az erre kijelölt szövegmezők szélső szóközeit. Például egy régi profilból hiányzó `duration_doubling_slowdown_pct` mező `null` értékkel kerülhetett az új mentésbe. Emiatt a mentés megtörténhetett, miközben a felület ellenőrzésre váró állapotban maradt.

A kliens most ugyanezeket a kifejezetten felsorolt, meglévő szerializálási szabályokat használja. Az új kérést már ezekkel az értékekkel rögzíti. A korábban eltárolt kérés bájtjai és azonosítója megmaradnak; a visszaigazolás ellenőrzése felismeri az adatmodell szabályai szerinti eltéréseket. Más kérésazonosító, előzmény, dátum, számérték, sport vagy jogosultsági állítás továbbra sem fogadható el. Az ellenőrzés az ismeretlen mezőket sem dobja el egy egyezés előállításához.

Folytatáskor először a pontos kérésazonosítóhoz és felhasználóhoz tartozó, már eltárolt mentést olvassuk vissza. Ha ilyen még nincs, az eredeti kérés pontos tartalma küldhető újra. A már megtörtént régi mentéshez nem kell újabb írás.

## Mentés a blokkok alján

Mind a hat adatblokkban külön mentési rész található az előző/következő lépés előtt:

| Blokk | Menthető adatok |
| --- | --- |
| Személyes alapadatok | A személyes adatok és keretek. |
| Sportelőélet | A sportágak, szerepek, tapasztalatok és célsport. |
| Célok és felkészülés | Az áttekintett felkészülés, a fejlesztési célok vagy a megnyitott mérési protokoll. |
| Edzéshelyszínek | Az éppen szerkesztett helyszín. |
| Általános edzésrend | A heti órarend és időszaka. |
| Állapotfelmérés | Az aktuális rész válaszai, ismert mérései vagy a folyamatban lévő felmérőalkalom eredményei. |

A blokk alsó gombja az adott szerkesztő eredeti mentési műveletét működteti. A kötelező mezők, az előnézetek, a jóváhagyás és a folyamatban lévő mentések ellenőrzése megmarad. Ha előbb egy helyszínt kell szerkesztésre megnyitni, egy időablak szerkesztését lezárni vagy a felkészülés áttekintéséig eljutni, ezt a mentési rész jelzi. A felmérésnél a kiválasztott részhez tartozó gomb jelenik meg.

A személyes adat és a sportelőélet külön mezőcsoportként menthető. Egy befejezetlen új sportsor nem akadályozza a személyes adatok mentését, és nem kerül be azzal a mentésbe. A másik blokk még nem mentett szerkesztése megmarad. A mérések is külön menthetők az állapotfelmérés megfelelő részéből.

A személyes blokk Mentés gombja egy korábbi profilmentés ellenőrzését is el tudja végezni, majd külön új kérésként elmenti a most módosított adatokat. A korábbi és az új mentés azonosítója elkülönül; a visszaigazolást továbbra is ellenőrizzük.

## Frissítés közbeni adatmegőrzés

Az eltárolt függő mentést a frissítés megőrzi. Az azóta beírt, még el nem küldött értékek a régi oldal memóriájában lehetnek, ezért újratöltés előtt jegyezd fel őket. Az új felület a szerveren igazolt adatokat tölti vissza; a további módosításokat a megfelelő blokkban lehet menteni.

## Ellenőrzés

A `python tools/run_c21_4_checks.py` a teljes frontend regressziót, a Next route-típusokat, a TypeScriptet, az érintett fájlok lintjét és a production buildet futtatja. Nincs új függőség vagy migráció.

- 1242 sikeres frontendteszt, sikeres route-típusgenerálás, TypeScript, ESLint és production build.
- Valódi HTTP-mentésekből előállított tesztadatok a hiányzó alapértékekre, a beágyazott szövegek normalizálására és az ismételt mentésre.
- Újrahashelt, eltérő kérések, előzmények, adatértékek és jogosultsági állítások elutasítása.
- Valódi API-val végrehajtott felületi próba: C21.3-as hiányzó alapértékű függő mentés → tulajdonoshoz kötött visszaolvasás → személyes blokk alsó Mentés gombja → új testadatok mentése egy befejezetlen sportsor mellett → sportsor külön mentése a sportelőélet saját alsó gombjával.
- DOM-ellenőrzés igazolja mind a hat mentési részt, az aktív szerkesztő követését, a kötelező mezők ellenőrzését, a letiltott állapotot és az aktív felmérési rész kiválasztását. Böngészős képernyőképes ellenőrzés nem készült.
