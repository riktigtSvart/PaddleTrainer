# C21.8 – Sporteredmények és az automatikus tervezés indítása

## Eredménytípusok

A Sportelőélet sporteredményei az eredeti táv–idő pár mellett négy névvel ellátott protokollt fogadnak:

| Típus | Mentett eredmény | További körülmény |
| --- | --- | --- |
| Táv és idő | Méter és p:ss/ó:pp:ss | Változat, körülmények |
| Cooper, 12 perc | Méter, rögzített 12:00 | Felszín, körülmények |
| Korábban teljesített 1RM | Pozitív kilogramm és egy ismétlés | Gyakorlat és a kilogramm értelmezése |
| Maximális ismétlésszám | Egész darabszám, a tényleges nulla is megadható | Gyakorlat, saját testsúly vagy külső terhelés |
| Ismétlésszám adott idő alatt | Darabszám és pozitív időtartam | Gyakorlat és terhelés |

A kilogramm lehet teljes külső súly (rúddal együtt), kézenkénti, testsúlyhoz adott súly vagy a gépen jelzett kilogramm. A külső súly nélküli testsúlyos eredményhez nem keletkezik kitalált terhelés. A nulla ismétlés különbözik a meg nem adott ismétlésszámtól.

A név, változat és körülmények szabadon megadhatók, így a különböző gyakorlatok vagy gépek eredménye nem keveredik össze. A dátum lehet pontos nap, közelítő év vagy ismeretlen. A tizedes számok szöveges pontossága és a korábbi bizonylatok megmaradnak; a korábbi sorok nem kapnak utólag kitalált protokollt.

A Cooper-bevitel rögzített idejének elsődleges szakirodalmi alapja Cooper 1968-as, 12 perces terepi tesztje: https://doi.org/10.1001/jama.1968.03140030033008. A felület az eredményt rögzíti, VO₂max-ot ebből a frissítésből nem állít elő.

A sportmúltba beírt maximum továbbra is tájékozódási adat. Nem kerül át automatikusan friss, tartalékkal és kivitelezéssel ellenőrzött erőfelmérő sorozatként az edzésdózisba. Az 1RM-választás korábban teljesített eredmény rögzítésére szolgál, nem maximális próbára adott utasítás.

## Mi blokkolhatta az indítást?

A teljes profil korábbi `JSON.stringify` összehasonlítása a mezősorrend eltérését is mentetlen változtatásnak tekinthette. Most ugyanaz a szemantikus, blokkonkénti összehasonlítás adja a jelzést, amely a mentési állapotot is meghatározza. A személyes, sportelőéleti és mérési előzménybeli valós módosítások külön nevet és megnyitó gombot kapnak.

A kezdeti kérdéssor a profil, helyszínek és célok konkrét mentett forrásához tartozik. E források változásakor az eredeti igazolás nem íródik át: az oldal megmutatja, mit kell aktualizálni, és a „Felmérési válaszok ellenőrzése” gomb közvetlenül odavisz. A friss források kifejezett átvétele megőrzi a válaszokat, az összegzéshez lép, és új átnézést, majd mentést kér.

A hiányzó válaszok esetén a konkrét lépés neve jelenik meg az általános „Állapotfelmérés még szükséges” szöveg helyett. A mentett, teljes felmérés feltétele továbbra is megmarad; hiányzó vagy elutasított adatot nem minősítünk automatikusan késznek.

## Friss felmérési eredmények

Az oldal helyi frissítési jelzéskor és visszafókuszáláskor újraolvassa a felmérést. A vezetett alkalom által elmentett új verziót a tiszta kérdéssor átveszi, így a referenciaszám és az indíthatóság frissül. A még szerkesztett válasz és a bizonytalan függő mentés megmarad.

Ha közben külön mentett eredmények és helyi piszkozat is keletkezett, a kifejezett forrásátvétel a stabil sorozat-/gyakorlat-azonosítók szerint egyesíti az adatokat. A külön azonosítójú saját és frissen mentett sorozatok megmaradnak. Egyidejű, azonos mezőt érintő eltérésnél a helyi válasz marad az átnézendő szerkesztőben. Az összegzés átnézését ilyenkor újra meg kell jelölni. Az eredeti szerververziók változatlanul visszakereshetők.

Az automatikus tervezés bekapcsolása továbbra is a saját bekapcsológombbal történik. Ha a backend ezután valódi akadályt jelez, az oldal helyben marad és megmutatja azt. A meglévő függő mentés pontos újrapróbálása, tulajdonoskötése, forráshivatkozásai és backend-ellenőrzései megmaradtak.

## Ellenőrzés

- Teljes backendtervezési regresszió: **2140 sikeres**.
- Teljes frontendregresszió: **1303 sikeres**.
- Next útvonaltípusok, TypeScript, ESLint és production build: sikeres.
- Valós API + React DOM próba: Cooper, 1RM, testsúlyos nulla ismétlés és súlyos időre végzett ismétlések mentése; tiszta profilállapot; friss forrás átvétele és összegzés mentése; vezetett alkalom után 0→2 referencia újratöltés nélkül; kifejezett bekapcsolás után valóban létrehozott edzések.
- Ugyanebben a próbában: külön mentett új sorozat egyesítése a még mentetlen saját megjegyzéssel, új átnézés megkövetelésével.

A felületi ellenőrzés funkcionális DOM-próba volt valós API-val. Natív böngészős képi ellenőrzés ebben a környezetben nem történt.
