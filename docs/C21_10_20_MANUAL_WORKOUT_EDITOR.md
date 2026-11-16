# C21.10.20 – Saját edzésterv szerkesztése

A C21.10.19 naptárára épülő frissítés. A naptár **+ Saját edzés** gombja, illetve egy nap jobb kattintásos menüjének **Új saját edzés…** pontja nyitja meg a szerkesztőt.

## Használat

- Edzésnév, sportág, dátum, opcionális kezdés, teljes időtartam, távolság, helyszín, leírás és fő edzéscél rögzíthető.
- A mezociklus külön választható. Automatikus módban a dátumot lefedő egyetlen saját mezociklushoz kapcsolódik az edzés; többértelmű vagy hiányzó szakasznál nincs automatikus hozzárendelés.
- Az edzés szakaszokra bontható: bemelegítés, főrész, pihenő és levezetés. Az ismétlésszám az adott szakasz időtartamát és távolságát ismétli. Intenzitástípus és számszerű alsó/felső határ is megadható. A teljes időbe a szakaszok és a pihenők is beleszámítanak.
- Kondinál a katalógus gyakorlatai vagy saját gyakorlatnevek használhatók: munkasorozatok, ismétlés **vagy** tartás, súly, összes/kézenkénti értelmezés, pihenő, opcionális ismétléstartalék, megjegyzés.
- A saját recepthez nem kötelező felmérés. A megadott terhelést a felhasználó írja elő; az alkalmazás ebből nem készít mért erőállapotot vagy teljesítési naplót.
- Heti ismétléssel 1–24 alkalom menthető egyszerre. Mindegyik önálló edzés, később külön módosítható. Az ismétlődő helyi időt óraátállításkor egyértelműsíteni kell.
- Egy saját edzésre kattintva megjelenik a részletes recept, a **Saját edzés szerkesztése** és a **Másolás saját edzésként…** gomb. A másolat alapértelmezésben egy héttel későbbre kerül; mentés előtt minden adata módosítható.
- Más tervezett edzésből is készíthető saját másolat. Az eredeti megmarad. Az egymásba ágyazott REPEAT-szakaszok szerkesztése/másolása ebben az első változatban nem támogatott; az alkalmazás nem lapítja el őket észrevétlenül.
- Szerkesztéskor az **Ezt a tervezett edzést elhagyom** választás és az **Edzés elhagyása** gomb az aktív tervből veszi ki az alkalmat. Az előzmény megmarad.
- A mentéskor megjelenő hibaüzenetek megmondják, mi hiányzik vagy érvénytelen. A bevitt adatok a nyitott ablakban megmaradnak. Az ablak melletti kattintás, Escape, Mégse és Bezárás mentés nélkül zár; a még el nem küldött űrlapot nem tároljuk külön vázlatként.

## Együttműködés a tervezővel

A saját edzés `MANUAL` forrású `PLANNED` alkalom. A későbbi automatikus tervezés megőrzi, és figyelembe veszi az időfoglalását/terhelését. A mentés önmagában nem indít újratervezést és nem ír vissza Polarba. Ha ugyanarra a napra másik edzés is tartozik, a mentési visszajelzés jelzi; egyiket sem töröljük vagy cseréljük le automatikusan. A saját tervet a naptárban érdemes együtt átnézni a többi edzéssel.

Ez az első változat naptári alkalmakat és heti ismétléseket szerkeszt. Tetszőleges edzésterv-fájl importálása és önálló sablonkönyvtár nem része.

## Technikai határ

- `GET /api/v1/planning/calendar/manual-workouts/context`: helyi szerkesztői beállítások és gyakorlatkatalógus.
- `GET /api/v1/planning/calendar/manual-workouts/{id}`: kizárólag a saját fiók edzésének aktuális adatai, forráslenyomata és szerkeszthetősége.
- `POST /api/v1/planning/calendar/manual-workouts`: zárt create/update/cancel kérés. A Next proxy csak ezeket a pontos útvonalakat engedi; POST esetén origin-, JSON- és mérethatár-ellenőrzés érvényes.
- Egy tranzakció menti az edzéseket, a szakaszokat, a céljelöléseket és az új `manual_workout_edit` auditbizonylatot. Ismétlésnél bármely hibás nap miatt az egész mentés visszagörgetődik.
- A request UUID idempotens. Elveszett válasznál az eredeti kérés a böngésző munkamenet-tárhelyén megmarad; az azonos kérés ellenőrzése nem hoz létre újabb alkalmat. A kliens nem küld automatikusan új azonosítójú mentést.
- Módosítás és elhagyás az eredeti edzés és külön a céljelölés aktuális változatához kötött. A közben beérkező kapcsolt teljesítés, lezárt állapot, Polar-cél vagy jóváhagyott külső terv megakadályozza az átírást.
- A kézzel megadott recept külön `raw_data.paddletrainer_manual_workout` névtérben marad. Nem `strength_workout_log`, nem felmérés és nem bizonyíték az elvégzett munkára. A súly tizedes szövegként tárolódik, lebegőpontos kerekítés nélkül.
- A naptár már betöltött adatából mutatja a saját receptet. A szerkesztő egyszerű helyi olvasást végez; nem futtat tervezést, forrás-visszajátszást vagy külső adatlekérést. Mentés után a meglévő C21.10.19 gyorsítótár-érvénytelenítés frissíti a nézetet.
- Nincs új adatbázistábla vagy migráció: meglévő edzés-, blokk-, JSON- és audit-tárolás használatos. A telepítő adatbázist és `.env` fájlt nem módosít.

## Ellenőrzés

`python tools/run_c21_10_20_checks.py` futtatja a saját szerkesztő, a megőrzött naptár, az alternatívák és a ciklusok releváns regresszióit, a Next típuskészítést, TypeScriptet, ESLintet és az éles buildet. A `--full-backend` és `--full-frontend` kapcsoló a teljes tesztcsomagot választja.

Külön valódi FastAPI + React StrictMode próba ellenőrzi a felvételt, heti ismétlést, módosítást, másolást, elhagyást, mentés utáni válaszvesztést, azonos kéréses újrapróbálást, közben beérkező teljesítés miatti elutasítást, a kattintással bezárást és a naptári belépési pontokat. A tesztek izolált adatbázison futnak; a felhasználó gépén tárolt adatokhoz nem férnek hozzá.
