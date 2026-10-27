# P2.4C9 – Teljesített edzés részletei és grafikonjai

Alap: `5dbcf3b9b038f63c5b17eafa496eb3e0ea1014ca`, tiszta main / origin/main.
A 995 fájlos, 2026-10-27-én átadott forráscsomag minden fájljának nyers
SHA-256 lenyomata egyezik a mellékelt pillanatfelvétellel.

## Használat

A naptárban egy teljesítésre kattintva az **Edzés minden részlete →** hivatkozás
a meglévő `/sessions/{id}` címen nyitja az új részletezőt. Az oldal a közös
alkalmazáskeret és a világos / sötét / rendszert követő téma színeit használja.

- Hat összesítő kártya, terv–teljesítés összevetés, további forrás szerinti mutatók.
- A kapcsolt terv blokklistája az eredeti ismétlésekkel, távokkal és intenzitással.
  A blokk nem jelent bizonyítottan teljesített szakaszt.
- Külön kapcsolható pulzus, sebesség, távolság, frekvencia, bal / jobb oldali
  hajtókar-teljesítmény, magasság és hőmérséklet, ha a minták tárolva vannak.
- Az iram a pozitív sebességből számított `3600 / km/h` másodperc/km.
  Nulla, hiányzó vagy nem véges sebességhez nem keletkezik véges iram.
- Közös relatív mintasor-idő, kapcsolható adatsorok, egérrel vizsgálható pontok,
  billentyűzetes időcsúszka, pontos számértékek, explicit időtartomány-nagyítás.
- Többrészes edzésnél külön részválasztás; a külön részek óráit nem ragasztjuk
  feltételezett kezdőeltolással egybe. Váltáskor a nagyítás és a kurzor visszaáll.
- Forrásonként lenyitható mintatáblázat, legfeljebb 101 forráshelyes ablakkal.
  Ismeretlen időköznél sorszám szerinti lapozás, kitalált időtengely nélkül.

A forrás által közölt időtartam, valamint a kezdés és befejezés közötti eltelt
idő külön szerepel. Az eltérés önmagában nem bizonyít hibát vagy edzésszünetet.
A nullérték hiányzó adat, a nulla külön érték. VO₂max, izomterhelés vagy más
hiányzó összesítő nem készül következtetésből.

## Minták értelmezése

A megőrzött `exerciseSamples` nézet az elsődleges, ennek hiányában a natív
`exercises` nézet használható. Két nézetet nem számolunk össze. A forrásútvonal
és a csatornatípus megmarad. Az elemző új megjelenítési adapter, a meglévő
tudományos / HR-válasz normalizálót nem módosítja.

A relatív idő az adott rész forrásindexe × a deklarált `intervalMillis`.
Az első forráshely a mintasor saját nullpontja; ez nem igazol abszolút
falióra-időpontot vagy szünetmentes időtengelyt. A forrás kezdetét nyers,
szolgáltatói helyi szövegként mutatja a részválasztó, időzóna kitalálása nélkül.

A nem numerikus, logikai, nem véges és az adott csatornán értelmezhetetlen
negatív érték hiányzó helyet hagy. A negatív magasság és hőmérséklet megmarad.
A hiányzó pont megszakítja a görbét, nem tolja el a későbbi forrásindexeket.
A hosszú sor rajza vödrönként kezdő / minimum / maximum / utolsó pontot őriz,
az eredeti sorrendben, a hiányokat áthidaló összekötés nélkül. A kurzor mindig
a teljes, nem ritkított forráshelyet használja; nincs numerikus interpoláció.
Túl sok különálló szakasznál a felület szűkebb időtartományt kér.

A két hajtókar teljesítménye külön csatorna. Nem összegezzük és nem nevezzük
őket teljes edzésteljesítménynek. Az összesítő átlag / maximum a tárolt külön
forrásérték marad. Még nem támogatott típusok és kiegészítő RR / átmeneti /
úszóminta-konténerek hiánypótlás helyett külön forrásjelzést kapnak.

Dokumentációs támpontok: [Polar Dynamic API v4](https://www.polar.com/polar-api-v4/)
(`trainingsessionIntervalValues`, `IntervalValuesSampleType`) és a
[Polar mintatípus-katalógus](https://www.polar.com/accesslink-api/).
A meglévő SPEED km/h, DISTANCE m és HEART_RATE bpm belső szerződés megmarad.

## Olvasási határ

Új, kizárólag GET művelet:
`/api/v1/planning/calendar/sessions/{session_id}`.
Zárt Next átjáró: `/api/calendar/sessions/{session_id}`, lekérdezési paraméterek
és írási metódusok nélkül. Az összesítő, a kapcsolt terv és a minták egyetlen
tulajdonosra szűrt tranzakcióban kerülnek kiolvasásra; utána rollback zár.
Olvasás nem hoz létre sportolót, nem módosít edzést vagy napirendet, nem ír
auditot, és nem indít szolgáltatói szinkronizálást. Az idegen fiók edzésazonosítója
ugyanúgy 404, mint a hiányzó. Idegen tervhivatkozásból nem kerül ki tervtartalom.

A válaszban nincs GPS-útvonal és nincs teljes nyers szolgáltatói payload.
Minden válasz `no-store`. A frontend ellenőrzi a kért edzésazonosítót, a
tervkapcsolatot, időzónát, mintatípusokat, egységeket, helyszámokat és hiányokat.
Hibás olvasáskor explicit újrapróbálás, edzésváltáskor a régi görbék eltűnnek.
A közös szolgáltatói szinkronizálás befejezési jelzésére a részletező újraolvas.

Korlátok: 64 edzésrész, 128 nyers csatorna, csatornánként 360 000, összesen
500 000 forráshely; tervenként 4000 blokk. Túllépés külön jelzett elutasítás,
nem teljesnek látszó csonka válasz. A nyers adatok tárolása változatlan.
Új függőség, adatbázis-migráció vagy szolgáltatói jogosultság nem szükséges.

## Ellenőrzés

Az izolált backendkapu 261 tesztet futtat, köztük a korábbi naptári,
áthelyezési, személyes időbecslési, Polar-párosítási és megőrzési regressziókat.
429 frontendteszt, teljes TypeScript, módosított forrásokra ESLint és production
Next build is sikeres. A hordozható kapu ideiglenes SQLite-fixture-öket használ;
a backend hálózati kapcsolatait tiltja, a belső Windows stdlib socketpair
kifejezett kivételével.

A 10 esetből álló interaktív ellenőrzés tényleges React DOM-ot, zárt átjárót és
FastAPI / SQLite kódot köt össze stdin/stdout csatornán. Vizsgálja a kapcsolást,
nagyítást, nullás / hiányzó pontot, forrástáblát, több edzésrészt, hiba utáni
újrapróbálást és edzésváltást; igazolja a nyers rekord és az audit változatlanságát.
Ez JSDOM-próba, nem natív böngészős, képernyőképes vagy Windows-ellenőrzés.
