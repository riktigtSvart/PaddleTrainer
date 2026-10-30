# P2.4C17 – Közös edzésgrafikon, útvonal és visszajelzés

## Első nézet

Kompakt fejléc és forrás szerinti összesítők után egy közös grafikon, alatta térkép jelenik meg. A bal és jobb tengely adatsora külön választható, saját skálával és mértékegységgel; egyik tengely kikapcsolható. Ugyanaz az adatsor nem duplikálódik két tengelyre. A grafikon beállításai sportolónként a böngészőben maradnak meg. A sebesség egysége továbbra is km/h, m/s vagy knots.

Az iram csak pozitív sebességből készül. Az összteljesítmény az együtt mért, azonos felbontású bal és jobb csatorna összege; nem sebességből becsült teljesítmény. Hiányzó mérésből nem keletkezik mért görbe.

Az idő az adott edzésrész mintasorának ideje. A távnézethez egyértelmű, nem csökkenő, ismert kezdőértékű távmintasor kell; a táv ehhez a kezdőértékhez viszonyul. Mintahiányt egyik görbe sem hidal át. Eltérő felbontásnál a kijelzett forrásminta saját időpontja látszik. Távnézetben csak pontosan illeszkedő távmintához rajzolunk pontot.

## Szakaszok, zónák, kézi átvezetések

A grafikon alatt keskeny szakaszsáv marad. Az ismert tervhatárok szaggatott vonalak; kézi referencia, áttekintett kezdőpont és távsorból számított határ külön osztályt kap. Ezek nem igazolt Polar-gombnyomások. Bizonytalan kézi továbblépés után a későbbi szakaszok időhelye továbbra is visszatartott.

A Megjelenítés menüben külön kapcsolható:

- szakaszhatárok és köztes várakozási ablakok;
- az adott szakasz tartományába helyezett előírt célsávok;
- a kiválasztott tengelyhez tartozó teljes edzési zónabeosztás.

A Célsáv választó dönti el, melyik tengelyen jelennek meg a sávok. Pulzus-, sebesség-, iram- és összteljesítmény-előírások a meglévő egység- és zónaátváltásokat használják. Alapból a szakaszhatárok és az előírt célsávok látszanak, a teljes zónabeosztás kikapcsolt.

A szakaszillesztő, a kézi kezdőpontok és az elfogadható mozgásjavaslatok megmaradtak. A táblázat kijelölése a közös grafikon és az útvonal megfelelő részét emeli ki. A forrás szerinti körök és a tervszakaszok külön táblázatban maradnak, egyezésükből nem készül feltételezett bizonyíték. A forrásminták külön lenyitható, korlátozott táblázatban ellenőrizhetők.

## GPS

A részletes Polar-szinkron a korábbi statistics/samples/zones/laps mellett routes adatot is kér. A korábbi átvételi bizonylatok érvényesek maradnak, de az új képességhez a részletes átvétel újra szükségessé válhat. A meglévő folytatható szinkron és a naponta korlátozott feldolgozás marad érvényben.

- A natív szolgáltatói rekordok nem módosulnak; a bővített nézet az explicit edzésrész-azonosság alapján őrzi meg az útvonalat.
- A megjelenítési GPS-vetítés legfeljebb 100000 pont, megtartott forrásindexekkel. Érvénytelen koordináta vagy időpont hiány marad.
- Az időpont a route.startTime és exercise.startTime különbsége + elapsedMillis. Hiányzó vagy kevert időzónájú kezdésből nem találunk ki időt. Szünet miatt bizonytalan mintasor-időalapnál a térképes pontkapcsolat nem aktív.
- A kurzorhoz legfeljebb öt másodpercre lévő GPS-forráspont jelölhető; annak saját ideje ki van írva. Nincs interpolált GPS-helyzet. A térképen ismételten érintett ponthoz a jelenlegi kurzorhoz közelebbi forrásidő részesül előnyben.
- A térkép húzható, nagyítható; a GPS-hiányokat, nagy időbeli réseket és dátumvonal-ugrásokat nem köti össze. A rajz korlátozottan egyszerűsített, a kijelölés az eredeti pontokhoz tartozik.
- A GPS-nek külön route_content_hash értéke van. Csak GPS-bővítés miatt nem változik a korábbi mintasor content_hash, így a meglévő kézi szakaszreferenciák kulcsa megmarad.

A Topó alapréteg az OpenTopoMap HTTPS-képeit használja, a térképen látható forrásmegjelöléssel. Kizárólag a látható csempéket kéri le; nincs tömeges letöltés vagy offline előtöltés. Ha az alaptérkép nem elérhető, a tárolt útvonal megmarad.

A Műhold réteg az ArcGIS World Imagery fejlesztői szolgáltatására van bekötve. Beállításához saját, megfelelő szolgáltatási jogosultságú, böngészős használatra korlátozott kulcs szükséges az apps/web/.env.local fájlban:

```text
NEXT_PUBLIC_ARCGIS_API_KEY=<saját böngészős térképkulcs>
```

A NEXT_PUBLIC érték bekerül a böngészőbe: ide nem kerülhet Polar Client Secret vagy más szerveroldali titok. A csomag nem hoz létre fiókot, kulcsot vagy előfizetést, és nem módosít környezeti fájlt. Kulcs nélkül a Műhold kapcsoló inaktív. A kulcs beállítása után a frontend újraindítása/buildje szükséges. A szolgáltató feltételei és használati keretei az adott fiókra érvényesek.

Szolgáltatói dokumentáció: https://opentopomap.org/about és https://developers.arcgis.com/maplibre-gl-js/maps/raster-tile-basemaps/display-multiple-basemap-layers/

## Személyes visszajelzés és gépi előkészítés

Ha még nincs mentett visszajelzés és a sportoló/edzés páros emlékeztetőjét nem halasztották el ebben a böngészőben, az első megnyitáskor külön ablak jelenik meg. Bezárható, és később a Saját visszajelzés gombbal újranyitható. Maga a megnyitás nem küld visszajelzést. A piszkozat, a verzióütközés-kezelés és az azonos bájtú függő mentés újrapróbálása megmarad.

A tanulási kapcsolat alul, lenyitható részben van. A gépi előkészítés automatikusan csak a már ellenőrzött ready_to_freeze állapotú kapcsolatokhoz indul. Ez a meglévő auditált válaszbeolvasást hívja, nem indít új modelltréninget, és nem változtat edzéstervet. Nem fogad el helyettünk bizonytalan tervkapcsolatot vagy szakaszjavaslatot. Az emberi áttekintést igénylő kapcsolat külön művelet marad. Előkészítési hiba nem törli a személyes visszajelzést.

## Alkalmazás és ellenőrzés

A csomag a 2026-10-29T15:11:30Z időpontú, 1108 fájlos, C16-ot tartalmazó forráscsomagra épül; C13 main/HEAD/origin/main fölött még nem commitolt C14–C16 állapot. Nincs migráció. Alkalmazás előtt a backend és frontend álljon le, utána mindkettő újraindítandó.

A célzott backendtesztek új, elkülönített adatbázisokat használnak; projekt-.env és alkalmazás-adatbázis nélkül, hálózati kapcsolatok tiltásával. A Windows belső socketpair kézfogása csak a standard könyvtári hívás szűk körében engedélyezett. Minden tesztfájl külön gyermekfolyamatban fut, és a szülő csak annak kilépése után takarítja el az SQLite-fájlokat.

A VALIDATION.json tartalmazza a tesztek és DOM-próbák eredményeit. Élő Polar-fiókkal, térképcsempe-szolgáltatással vagy a Windows 175%-os nézetében nem történt próba; ezeket a helyi kipróbálás ellenőrzi. GPS csak az útvonalat tartalmazó sikeres részletes szinkron után látható, az adott szinkronizált dátumtartományban.
