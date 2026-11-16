# C21.3 — Alapadatok és tervezési adatok

C21.2 után telepíthető felületi frissítés. A backend és az adatbázis adatformátuma változatlan.

## Hat külön adatblokk

A felső hatlépéses navigációs sáv helyét hat önálló, összecsukható blokk veszi át: személyes alapadatok, sportelőélet, célok és felkészülés, edzéshelyszínek, általános edzésrend, állapotfelmérés. Mindig egy van nyitva. A bal oldali almenü, a blokk fejléce és a következő/előző gomb ugyanazt a kiválasztást kezeli. A személyes adatok, sportok és ismert mérések egy közös szerkesztett profilt használnak, így blokkváltáskor megmaradnak a beírt adatok.

A fejlécek zárt állapotban is mutatják a következőket, ikonnal és szöveggel:

| Jelzés | Jelentés |
| --- | --- |
| Tervezési alap megadva | Az adott blokk szükséges mentett alapadatai rendelkezésre állnak. |
| Még szükséges vagy pontosítandó | Hiányos vagy felülvizsgálatra váró mentett adat. |
| Mentetlen változtatás | Az adott blokkhoz tartozó szerkesztés még nincs rögzítve. |
| Mentés ellenőrzésre vár | A korábbi személyesadat-mentés visszaigazolását kell befejezni. |

A jelzés egy adatcsoport kitöltöttségét mutatja. Az automatikus tervezés bekapcsolásakor az alkalmazás együtt ellenőrzi a mentett alapokat, célokat, helyszíneket, időlehetőségeket és felmérést; a backend tervezési feltételei továbbra is érvényesek. A testsúly, magasság és nem hiánya önmagában nem változik új kötelező feltétellé. A személyes rész jelzését nem zárja le egy kizárólag a sportelőéletből hiányzó adat.

## Szerkeszthető személyes adatok és sportok

A születési adatok, a mért testsúly és magasság, a mozgást érintő korlátozások és kihagyások később is módosíthatók. A testméretek a mérés dátumával együtt menthetők. A korábbi mentések megmaradnak.

A sportelőéletben fő-, kiegészítő és szabadidős sportok rögzíthetők. A külön hozzáadógomb a kiegészítő vagy szabadidős szerepet állítja be; a tudásszint továbbra is ismeretlen marad, amíg a sportoló meg nem adja. A sportnév szabad szöveg is lehet. Az ajánlások között megjelenik az alpesi síelés/lesiklás, a snowboard és a korcsolyázás is. Új sport később is felvehető. A sportelőélet adatbevitele és tárolása bővül; a sportágspecifikus tervezés és fáradtságértékelés a külön modulok feladata.

## Érthető folytatás félbemaradt műveletnél

A nagy, általános „Függő mentés / lekérés” kártyát rövid, konkrét üzenet helyettesíti. Más szöveg és folytatógomb tartozik a személyesadat-mentéshez, az edzésidők mentéséhez és az órás adatátvételhez. Utóbbinál a kérdéses adatkör és nap is látszik.

Visszaigazolásra váró művelet mellett az adatmezők szerkeszthetők. Az új mentés a korábbi művelet rendezése után indítható. A folytatás az eredeti, eltárolt kérés pontos bájtjait küldi újra, az eredeti azonosítóval. A közben szerkesztett mezők a visszaigazolás után is megmaradnak, és külön menthetők. A frissebb szerverállapot más, nem érintett mezőit az alkalmazás megtartja. A böngésző tárhelyének olvasási hibája, folyamatban lévő küldés és eltérő felhasználó továbbra is ellenőrzött állapot.

## Ellenőrzés

A `python tools/run_c21_3_checks.py` parancs a teljes frontend regressziót, a Next route-típusokat, a TypeScriptet, a lintet és a production buildet futtatja. Új függőség vagy adatbázis-migráció nem szükséges.

1228 frontendteszt sikeres. DOM-ellenőrzés igazolja az egyetlen nyitott blokkot, az almenüvel összehangolt navigációt, a zárt fejléc mentetlen jelzését, a hozzáadott kiegészítő/szabadidős sport megőrzését és az eredménybeviteli felület elérését. Valódi API-val ellenőrzött az elveszett válasz utáni azonos újraküldés, a közben beírt testadatok megtartása, az új revízió mentése és a másik ablakban rögzített, nem érintett mezők megőrzése. Képernyőképes böngészős ellenőrzés ebben a környezetben nem készült.
