# C20.4 — Vezetett kezdeti sportági és erőfelmérés

A mentett személyes profil és helyszíni felszerelés mellé külön, változatonként megőrzött felmérés kerül. Az **Edzéstervezés → Kezdeti felmérés** oldal (`/initial-assessment`) és a vezetett tervezési folyamat ugyanazt a mentést használja. A lépés az edzési helyszínek után, az órarend előtt található. Részleges állapotban is tovább lehet lépni; a felmérés nem kapcsolja ki a korábban működő kezdőmintákat.

## A hat lépés

| Lépés | Megőrzött adatok |
|---|---|
| Állapot és keretek | Felmérés dátuma, mentett profil, mozgáskorlátok, azóta észlelt változás és megjegyzés |
| Erőedzés-előzmények | Jártasság, elmúlt három hónap gyakorisága, utolsó ismert erőedzés, jellemző időtartam, felügyelet |
| Sportágak, cél és helyszín | Mentett felkészülés vagy általános cél; sportonként fő/kiegészítő/szabadidős/szünetelő szerep; szakág és céltáv; alapértelmezett helyszín |
| Gyakorlatok és jártasság | Húzás, nyomás, térddomináns, csípődomináns és törzsstabilizáló mozgás; helyszín, konkrét gyakorlat, ismertség, komfort, betanulási igény |
| Ismert teljesítések | Gyakorlatonkénti dátum és sorozatok; külön sportági saját referenciák, vagy kifejezett jelzés, hogy nincs további ismert adat |
| Összegzés és mentés | Kitöltési állapot, gyakorlatonkénti hiányok és referenciaállapot, átnézés, külön mentési gomb |

Egy felmérésben több gyakorlat is szerepelhet ugyanahhoz a mozgásmintához. A felszerelés-egyezés mindig egy konkrét helyszín saját eszközeiből készül. A másik helyszín súlyzója, gépe vagy tartozéka nem használható fel hozzá. A hiányos felszerelés vagy az ismeretlen előzmény megőrizhető; az összegzés megmutatja, mit kell még pontosítani.

A katalógus korábbi saját szemléltető lapjai a gyakorlatsor-választóból elérhetők. Ezek nem jelentenek automatikus alkalmassági vagy terhelési megállapítást.

## Sportági bővíthetőség

A verziózott `assessment_registry.json` induló sportágai: kajak, kenu, evezés, futás, kerékpározás, úszás, gyaloglás, túrázás, sífutás, foci, erősítés/kondi, gimnasztika, nyújtás/mobilitás és egyéb sportág. A fő és kiegészítő szerepek az adott felmérésben kiválasztott felkészüléshez tartoznak; több fő sportág is kijelölhető.

A sportági saját referenciákhoz dátum, protokoll, távolság, idő és annak jelentése, watt, pulzus, RPE, szintemelkedés, medencehossz, eszköz és körülmények rögzíthetők. Minden mező opcionális; a sportonkénti súgó segít eldönteni, melyik releváns. Az adatfelvétel támogatottsága külön szerepel az edzésgenerálás támogatottságától. Új sport bekötése a regiszter bővítésével kezdhető; attól még nem keletkezik hozzá terhelésgenerátor vagy tesztnorma.

A sportági referenciák `self_report` eredetűek. Nem írnak új `WorkoutSession` vagy `PlannedWorkout` rekordot, így ugyanaz a korábbi kerékpározás, kajakozás vagy úszás nem számít még egyszer teljesített edzésnek.

## Sorozatok és hiányzó adatok

Minden sorozat saját azonosítót kap. Ismétlésszám vagy tartási idő, terheléstípus, pontos érték, az érték jelentése, RIR, technika és panasz rögzíthető. Saját testsúly, külső kilogramm, kilogrammban megadott rásegítés, gépfokozat és leírt gumiszalag külön fogalom. A kilogramm lehet összsúly, kézenkénti vagy a gép kijelzett kilogrammértéke; a rásegítés nem válik ellenállássá. A gép/fogantyú/beállítás és az oldal külön megjegyezhető.

- A hiányzó szám `null`; az explicit nulla nulla marad. A RIR 0 és a nem ismert RIR külön állapot.
- A tizedesvessző bevihető. A szerver és a böngésző a tizedes számjegyeket karakterláncként őrzi; például `12.500000` nem rövidül le.
- A kitöltési lépések teljesítése nem követel kitalált sorozatot. Kezdőként a jártasság és a komfort „még nem próbáltam” válasza is értelmes.
- A „rögzített kiinduló referencia” az itteni beviteli szabály szerinti **önbevallott** referencia, nem hitelesített mérés és nem edzésengedély.
- A kezdeti referenciaablak 56 nap. Ez nyílt termékszabály, nem személyre kalibrált edzettségi határ. A korábbi adat megmarad, de az összegzés friss referencia hiányát mutatja.
- Új állapotváltozás, ismeretlen vagy felülvizsgálandó profil, nem megfelelő jártasság, bizonytalan komfort, hiányzó eszköz, technikai probléma és panasz nem lesz használható referenciasorozattá. Ha egy sorozatban fájdalom vagy kellemetlenség szerepel, egy másik sikeres sorozat nem fedi el azt.

Az új egészségi vagy mozgáskeretet a személyes profilban is át kell vezetni. Az erre mutató hivatkozás a felmérés első lépésében szerepel. A felmérés mentése a személyes profilt külön nem írja át.

## Tartós mentés és újratöltés

`GET /api/v1/planning/initial-assessment` a konfigurált sportolóhoz tartozó állapotot és forrásokat olvassa. `POST` kizárólag kifejezett mentéskor indul. Nincs sportolóazonosító vagy URL a lekérdezési paraméterek között; a zárt frontendproxy is elutasítja ezeket, az idegen Origint és a nem támogatott útvonalakat/módszereket.

A szerver a meglévő tervezési audit-tárban új `initial_assessment` típust használ, külön migráció nélkül. Megőrzött források: tulajdonos, időzóna, profil- és lehetőségbizonylat, katalógus és regiszter, mentett felkészülések, eredeti kérelem, összegzés, előző változat hivatkozása és hash. A teljes audit-rekord és a szülőhivatkozás ellenőrzött. Az előző változat nem íródik felül.

A mentés tulajdonosi zárolást és előzőváltozat-egyezést használ. Az időközben megváltozott profil, helyszín, katalógus vagy felkészülés új átnézést igényel; ezek nem kerülnek csendben a korábbi piszkozat alá. A felhasználó kifejezetten átveheti a friss forrásokat és a mentési alapot, a saját válaszai megtartásával. Sikertelen tranzakció visszagörgethető; ugyanaz a kérés utána egyszer menthető.

Három külön állapot látható:

1. **Helyi piszkozat:** sportolóhoz kötött, visszaállítható válaszok és nyitott lépés; nem szervermentés.
2. **Függő mentés:** a kérés pontos bájtjai még elküldés előtt helyben megmaradnak. Bizonytalan eredménynél a válaszok zárolódnak; visszatöltéskor nem indul POST. Az újrapróbálás azonos kérésazonosítóval és azonos bájtokkal történik.
3. **Visszaigazolt tartós mentés:** csak tulajdonos-, kérelem-, forrás-, séma-, hash- és committed-egyezés oldja fel a függő kérést. Egy régi kérés újrapróbálása az eredeti bizonylatot adja vissza, akkor is, ha már van újabb változat.

A helyi tárolás meghibásodásakor az alkalmazás nem indít olyan írást, amelynek a kérését nem tudta előtte megőrizni. Az újratöltött állapot minden esetben különbözik a sikeres mentéstől. A referenciák idősödése a friss összegzésben látszik; a korábban kiállított bizonylat tartalma ettől nem változik.

## A jelenlegi fejlesztés határa

A C20.4 a vezetett adatfelvételt és annak tartós tárolását készíti el. **Az új felmérésből még nem számolódik új súly, 1RM, sorozat, ismétlés, progresszió vagy erőedzésterv.** Az edzésgenerátorhoz való bekötés következő, külön feladat; a jelenlegi mintatervező működése megmarad. Az összes új szerver- és kliensszerződésben `planning_authorized`, `workouts_changed` és `clinical_clearance` hamis.

Ellenőrzés: `python tools/run_c20_4_checks.py --build`; célzott Python/Ruff, valódi API-válaszokból származó böngészős szerződéstesztek, helyi DOM-interakció és a csomagtelepítő külön ellenőrzése. A kiadási csomag `VALIDATION.md` fájlja tartalmazza a tényleges eredményeket és az ellenőrzés korlátait.
