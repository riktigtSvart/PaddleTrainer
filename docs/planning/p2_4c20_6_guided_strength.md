# C20.6 — Valódi kezdő erőfelmérő alkalom

A C20.4 kérdőíve a jártasságot és a már ismert eredményeket rögzíti, a C20.5 tervező pedig valódi saját sorozatreferenciát igényel. A C20.6 a hiányzó első alkalmat vezeti végig. Friss referencia nélkül is elindítható, de a gyakorlatot már ismerni kell, és az adott helyszínen rendelkezésre kell állnia a felszerelésnek.

## Elérés és felhasználói menet

Útvonal: `/strength-assessment`. Az Edzéstervezés almenü **Kezdő erőfelmérő alkalom** pontja, a kezdeti felmérés teljesítményoldala és mentőfelülete, valamint a terv erőfelmérési panelje is odavezet.

1. A tartósan mentett kezdeti felmérésből helyszínt és legfeljebb öt külön mozgásmintát választ a felhasználó. A hiányos felszerelésű, ismeretlen vagy panasszal jelzett gyakorlat indoklással tiltott. A meglévő referencia nem indítási feltétel.
2. Megadja, hogy órával vagy kézzel rögzíti az alkalmat, és megerősíti az aktuális állapotot, a jártasságot és a helyszíni kereteket.
3. Könnyű bemelegítés után gyakorlatonként egy opcionális próba- és egy referenciasorozatot rögzíthet. A pihenőhöz külön, választható kétperces időzítő tartozik.
4. Az adatlap megőrzi a tényleges ismétlést vagy tartási időt, a terhelés típusát, pontos tizedeseit és jelentését, az oldalt, a gépet/beállítást, a jelzett tartalékot, technikát és panaszt. Az ismeretlen és a nulla különbözik.
5. Gyakorlat kihagyható; az alkalom részleges eredménnyel is lezárható. A „Mentés és szünet” szerverre ment, a mezők ezen felül tulajdonoshoz és pontos szülőváltozathoz kötött helyi piszkozatban maradnak meg.
6. Az eredmények és a valós alkalom rögzítésének áttekintése után következik az explicit lezárás. A külön edzéstervhez továbbra is újraértékelés és külön elfogadás szükséges.

A több napon végzett edzések nem egyetlen alkalom részei. Korábbról nyitva maradt alkalom a valós régi befejezési idővel lezárható; a következő alkalom külön indítható.

## A kezdő protokoll határa

Ez ismert gyakorlatok könnyű, önbevallott kiindulóreferenciája. Nem standardizált maximális erőteszt és nem technikai betanító modul. A következő számok átlátható termékszabályok, nem személyre igazolt optimumok:

| Rész | Kezdő támpont |
|---|---|
| Bemelegítés | 5–10 perc, ismert és könnyű mozgással |
| Opcionális próba | Egy könnyű sorozat, körülbelül 3–5 kontrollált ismétlés |
| Referencia | Egy könnyű sorozat, körülbelül 5–8 kontrollált ismétlés |
| Ismert statikus tartás | Körülbelül 10–20 másodperc |
| Pihenő | Legalább 120 másodperc; szükség szerint tovább |
| Számszerű súly | A személy választja és rögzíti; a program nem talál ki kilogrammot |

A támpont helyett mindig a valóban elvégzett mennyiség kerül mentésre. Nem kell kifáradásig dolgozni. Fájdalom, kellemetlenség, széteső technika vagy 0–1 jelzett ismétléstartalék megállást jelez. A megállást a felmérési állapot is megőrzi, akkor is, ha csak a próbasorozatban jelentkezett. Ismeretlen tartalékot nem kell megbecsülni a továbbhaladás kedvéért.

A későbbi kezdő terv kizárólag a C20.5 külön feltételeinek megfelelő sorozatot használja: friss dátum, ismert és panaszmentes gyakorlat, tisztázott oldal, stabil technika, megfelelően leírt terhelés és az ott előírt óvatos tartalék. A 3-as RIR-határ a termék óvatos újrafelhasználási feltétele, nem univerzális fiziológiai optimum. A hiányos eredmény megmarad, de nem lesz automatikusan használható referencia.

Szakmai háttér: [ACSM 2026 állásfoglalás, PubMed 41843416](https://pubmed.ncbi.nlm.nih.gov/41843416/), [DOI:10.1249/MSS.0000000000003897](https://doi.org/10.1249/MSS.0000000000003897), [ACSM hivatalos közlemény](https://acsm.org/science-spotlight-acsm-releases-new-position-stand-on-resistance-training/). Ezek nem validálják ezt a termékprotokollt vagy egy adott személy terhelhetőségét. Nincs 1RM-számítás, bukásig tesztelés, automatikus súlyemelés vagy egyéni dózisoptimum-állítás.

## Egy fizikai alkalom, egy edzésnapló-bejegyzés

**Órás mód:** a felhasználó a lezáráskor kiválasztja a saját szinkronizált, befejezett STRENGTH felvételét. A rendszer ellenőrzi a tulajdonost, a sportágat, az időket, a megfigyelési napokat és az előző összekapcsolás hiányát. Nem hoz létre másik edzést, és a szolgáltatói adatot nem módosítja. Az órás szinkronizálás külön meglévő funkció; ez az oldal nem indít szolgáltatói lekérést.

**Kézi mód:** explicit, másik felvétel hiányáról szóló nyilatkozat és ellenőrzött valós kezdés/befejezés után egy determinisztikus azonosítójú `WorkoutSession` készül, `PADDLETRAINER_GUIDED` forrással. Az idő a bemelegítést és pihenőket is tartalmazó eltelt idő; nem állítunk aktív munkaidőt, pulzust, kalóriát vagy mért mintasort. A kézi időszak pozitív, legfeljebb hatórás, a kezdés az appbeli indítás előtt legfeljebb egy perccel lehet. A profil időzónáját használja a szerkesztő; nem létező vagy kétértelmű helyi órát nem választ ki önkényesen.

Azonos kérés újraküldése az eredeti bizonylatot adja. A kézi bejegyzés, a vetített kezdeti felmérés és a két auditbizonylat egy tranzakció része. Elrontott commit esetén egyik sem marad meg.

## Tartós protokoll és források

- Zárt GET/POST `/api/v1/planning/guided-strength`, a konfigurált alkalmazástulajdonoshoz kötve; nincs idegen tulajdonost választó query.
- Azonos eredetű frontend proxy: `/api/goal-workflow/guided-strength`.
- Parancsok: `start`, `checkpoint`, `finish`, `abandon`, `apply`.
- `guided-strength-session-v0.1` append-only audit: tulajdonos, logikai alkalom, növekvő változat, pontos előző hivatkozás, immutable induló kontextus, aktuális eredmények és explicit állapot.
- Egy nyitott alkalom lehet sportolónként. Fizikai aktivitás után a puszta elvetés helyett valódi lezárás szükséges.
- A részleges állapot, a próbák és a megjegyzések az alkalom saját auditjában maradnak. A kezdeti felmérés következő változatába csak a tényleges referenciasorozat kerül; a próbából nem lesz további edzéssorozat.
- Megváltozott kiindulóadatoknál a fizikai alkalom és eredményei menthetők, de a kezdeti felmérés nem íródik felül csendben. A friss adatok áttekintése és mentése után külön `apply` veszi át a korábban lezárt eredményeket, új edzés létrehozása nélkül. A gyakorlat/helyszín megfeleltetésnek egyeznie kell. A lezárt fizikai eredményt és időket az átvétel nem szerkesztheti.
- A kérés pontos bájtjai a POST előtt helyben megőrződnek. Újratöltés nem küld kérést; csak ellenőrzött, committed és pontosan egyező válasz oldja fel a függő állapotot.
- Az új `initial_assessment.stage/capture_context` belső segédek lehetővé teszik a közös tranzakciót; a korábbi felmérésbizonylatok formátuma nem változik.

## Tervezési kapcsolat

A `guided-strength-activity-v0.1` kis, tulajdonoshoz kötött auditbizonylatot rögzít minden alkalomparancshoz. A tervező az elmúlt 56 napból logikai alkalmanként a legfrissebbet fogja be. Az időpont, pontos hivatkozás és committed állapot külön ellenőrzött. A teljes felmérőalkalom nagy kontextusa nem kerül minden tervfelülvizsgálatba.

A `training-plan-policy-v0.8`:

- A lezárt alkalom tényleges `WorkoutSession` rekordját beleszámítja a gördülő keretekbe, az edzésnapi foglaltságba és a pihenési időközökbe.
- Az alkalom `reference_occasion` jelölést kap; ideje nem lesz szokásos erőedzés időtartamreferenciája. A pihenő és a kitöltés hossza nem edzéskapacitás.
- Az elmúlt 48 órából nyitott felmérőalkalom a mai és a következő napi új javaslatot visszatartja, amíg a valós alkalom rögzítése nem tisztázott. A felület külön indokot mutat.
- Az `experience=none` történeti választ nem írja át. A legfrissebb kezdeti felméréshez kapcsolt, ténylegesen lezárt felmérőalkalom bizonyítéka mellett eljuthat a megfelelő saját referenciasorozatokból összeállított kezdőjavaslatig. Másik vagy újabb felmérési forrásra ezt nem viszi át automatikusan.
- Nincs automatikus naptári tervelfogadás. A tervező többi kapuja, helyszíni feltétele, ciklusa és terhelési kerete továbbra is érvényes.

A frontend megtartja a v0.6/v0.7 tervbizonylatok olvashatóságát. A modern válaszban ellenőrzi a kis alkalombizonylatokat, az edzésazonosítók és jelölések egyezését, a belső input hash-t, valamint az alkalomból pontosan vetített felmérési adatokat.

## Ellenőrzés

`python tools/run_c20_6_checks.py --build` futtatja a teljes planning regressziót külön folyamatokban, a teljes frontend tesztsort, a Next útvonaltípusokat, TypeScriptet, érintett ESLintet és a production buildet. Az új HTTP-tesztekből készül a szintetikus frontend JSON. Az ellenőrzési csomag külön valódi React DOM-folyamatot is futtatott, a kezdéstől a szüneteltetésen át a bizonytalan POST eredményének pontos újrapróbálásáig.

Nincs új függőség vagy adatbázis-migráció. A két új auditfajta a meglévő szöveges audit-kind mezőben tárolódik. Az éles felhasználó adatbázisát a fejlesztési tesztek nem olvassák és nem módosítják.
