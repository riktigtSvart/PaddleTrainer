# C21.7 – Versenyigények, testtömeg-előzmény és táplálkozási cél

## Versenyigények

A `paddling-event-demands-v0.1` profil síkvízi kajak-kenu 200/500/1000 m és 5–50 km távokhoz ad 13 képességet lefedő, relatív 1–5 prioritást. A 10 km és 10000 m azonos profilt kap. Slalom, póló, vadvíz, surfski, sárkányhajó és más sport nem veszi át ezt a profilt. Ismeretlen távból vagy pusztán egy verseny nevéből nem következtetünk.

A pontok szakirodalomra támaszkodó **alkalmazási kezdőszabályok**. Nem mért energia-hozzájárulások, nem validált egyéni deficitpontok és nem edzésidő-százalékok. A sportolói állapot, a felkészülési szakasz és a korábban jóváhagyott szerepek ettől elkülönülnek.

Az 1991-es síkvízi vizsgálat több távot és több teljesítményösszetevőt vizsgált. A maratoni kutatás az anaerob teljesítmény relevanciáját is alátámasztja, de megfigyeléses összefüggése nem ír elő edzésarányt. Az alábbi forrásokból nem vezethetők le közvetlenül a kódban szereplő egész pontok:

- ICF edzői kézikönyv: https://www.canoeicf.com/sites/default/files/icf_csp_coaches_manual_level_23_.pdf
- Physiological and kinanthropometric attributes of elite flatwater kayakists: https://pubmed.ncbi.nlm.nih.gov/1766347/
- Hatchett et al., maratoni kajak-kenu teljesítmény: https://doi.org/10.23937/2469-5718/1510140

A fő fejlesztési hangsúlyok rangsorolása használja a relatív pontot. Az adott mezociklus célversenyének saját pontjai számítanak; a korábbi sprint pontjai nem másolódnak át a későbbi maratonra. A hosszútávú specifikus szakaszban az erőállóképesség és a tempóbeosztás kiemelést kaphat. A meglévő kezdő/visszatérő, fiatalkorú és részvételi keretek érvényben maradnak. Rögzített fejlesztési szerepet a rendszer nem ír át automatikusan.

A felületen az automatikus profil azonnal látszik, és mentéskor bekerül a pontos kérelembe. A kézi módosítás `coach_declared` forrású. A backend elutasítja a gyári automatikus profilnak álcázott eltérő súlyokat. A régi sprintbizonylatok formája megmarad. A korábban mentett, ismert hosszútávú, `unassessed` verseny olvasáskor is ad kiinduló stratégiai javaslatot, a régi bizonylat módosítása nélkül.

## Dátumozott testtömeg

A `body_mass_measurement` auditbejegyzések hozzáfűzéssel tárolódnak. Az aktuális értéket a mérési nap, azonos napon a rögzítés ideje adja. A pontos tizedes szám szövegként marad meg. A hiányzó érték nem nulla; jövőbeli vagy nem pozitív mérés elutasított.

A régi sportolói profilok dátumozott tömegei, az egynapos egyedi kézi és a profilba már átvett mérések olvasáskor csatlakoznak az előzményhez. Az ugyanazon örökölt nap/érték ismételt profilmásolata nem növeli a nézet darabszámát; az eredeti bizonylatok változatlanok. A még be nem töltött/át nem vett órás forrásokat ez a modul nem szinkronizálja magától.

A profilból indított mérés és a profil mentése egy tranzakció. A táplálkozási mérés ugyanígy egy tranzakcióban frissíti a szükséges profilsnapshotot. Régebbi mérés nem cseréli le az újabbat. Külön opcionális `body_mass_recorded_on` mező védi a tömeg dátumát attól, hogy egy magasságmódosítás átírja.

A személyes szerkesztő és a táplálkozási rész a közös, hash-sel ellenőrzött aktuális projekciót használja. A tervezési bemenet ugyanilyen külön projekciót kap, a változatlan profilforrás mellett. A történeti felmérések akkori testtömegét nem írjuk át mai értékre.

Az előzmény lapozható táblázatban látható. A korlát 10000 megfigyelés; túllépése explicit hiba, nem csendes levágás. A grafikon és a személyre szabott étrend későbbi feladat.

## Testsúlycél

Az új edzéscél-választóból a testsúlycsökkentés és -tartás kikerült. A külön `nutrition_goal` rekord fogyás, tartás, növelés vagy azonos tömeg melletti testösszetétel-javítás szándékát rögzíti. Fogyási/növelési célnál szükséges egy tényleges mérés és annak megfelelő irányú céltömeg. A céltömeg mentése sem testtömegmérést, sem kalória-/étrend-előírást nem hoz létre.

A régi testsúlyszándék olvasható, és a táplálkozási szerkesztőbe külön gombbal átvehető, majd kifejezetten menthető. A korábbi edzéscélverzió visszanézhető marad akkor is, ha az aktuális edzéscélokból már kivettük a testsúlycélt. A dátum nélküli régi tömegből nem keletkezik kitalált mérés.

## Mentési és határfelületi szabályok

A tulajdonos a beállított alkalmazásfelhasználó. A cél módosítása pontos előző hivatkozást kér. Az azonos kérés ismétlése ugyanazt a bizonylatot adja, más tartalommal nem használható fel ugyanaz az azonosító. A böngésző a függő kérelmet változatlan bájtokkal őrzi; visszatöltése nem indít mentést.

A meglévő zárt proxy két ismert útvonallal bővült: GET/POST `athlete/body-mass`, POST `athlete/nutrition-goal`. Az eredeti same-origin, méret-, credential- és lekérdezés-védelmek megmaradnak. A JSON-sémák és a tartalmi hash a Python–JavaScript határon is ellenőrzöttek.

## Ellenőrzés

A `tools/run_c21_7_checks.py` alapértelmezetten a teljes backend tervezési tesztcsomagot, a teljes frontend regressziót, Next útvonaltípus-generálást, TypeScriptet, ESLintet és production buildet futtatja. A `--frontend-only` csak a már külön teljesített backend ellenőrzést hagyja ki.

A célzott API-próbák fedik a maratoni profil és a mezociklusok kapcsolatát, a táv-/sportazonosítást, a kézi felülírást, az immutábilis régi szándékot, a külön cél és mérés tárolását, a történeti sorrendet, a tulajdonost, a CAS-t, az exact retry-t és a hibakor teljes tranzakció-visszagörgetést. A frontend valós FastAPI-válaszokkal ellenőrzi a hash-eket, a sorok teljességét, az idegen/átírt adat elutasítását és a pontos függő mentést.

Privát React DOM + valós API próbában ellenőrizve: személyes ↔ táplálkozási tömegszinkron; más mező piszkozatának megőrzése; több történeti mérés; külön cél mentése; elveszett válasz és újranyitás utáni azonos újrapróbálás; 10 km-es profil automatikus megjelenése és tartós mentése; korábbi célkitűzés-szerkesztési és mentési folyamat. Ezek funkcionális DOM-próbák; külön natív böngészős képi ellenőrzés nem történt ebben a környezetben.

A csomag készítésekor: 2114 teljes backendregressziós teszt sikeres; az utolsó három hozzáadott próbával együtt 21 célzott C21.7 teszt sikeres; a végső időhatár-ellenőrzéssel 40 testtömeg/tervezésibemenet-próba sikeres. Frontend: 1288/1288, útvonaltípusok, TypeScript, ESLint és production build sikeres. A telepítő ellenőrzése LF és CRLF alapról, ellenőrző módban, alkalmazáskor, ismételt alkalmazáskor, pontos visszaállításkor és helyi konfliktus esetén is sikeres; az adatbázis-őrfájl változatlan maradt.
