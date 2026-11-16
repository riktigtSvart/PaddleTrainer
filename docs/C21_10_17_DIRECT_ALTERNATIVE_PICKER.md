# C21.10.17 — Közvetlen edzésválasztó a naptárból

## Felhasználói működés

A naptárban egy cserélhető edzésre egyszer kattintva azonnal megnyílik az adott nap edzésválasztója. Nem kell belépni a részletes edzésbe, lenyitni egy alternatívarészt vagy kipipálni, hogy a mai edzés még nem történt meg. A lehetőségeket az ablak automatikusan, friss napi adatokból tölti be.

Az edzések egymás alatti külön blokkok. A blokk nagy választógombjára kattintás az adott nap edzésének kijelölése és mentési kérése. A háttérben új ellenőrzés, majd azonos tartalmú változat kiválasztása és a napra korlátozott csere történik. Nincs további megerősítő pipa vagy külön mentésgomb. Siker esetén az ablak bezárul, a naptár frissül. Más nap edzéseit ez a választás nem írja át.

A jelenlegi edzés kiemelt blokkban látható. Az alternatívák mellett megmarad a fő cél / alcél / fenntartás besorolás, a fő cél megváltozásának jelzése, az időtartam, helyszín, időpont és legkésőbbi kezdés. A valóban más edzések és az azonos tartalmú időpont/helyszín-változatok külön csoportban vannak; az időpontokat nem kell külön lenyitni a választáshoz. Az egyes edzések részletes utasításai továbbra is lenyithatók, de az utasítások lenyitása nem választja ki az edzést.

A mellékattintás, a **Bezárás** és az **Escape** ugyanúgy bezár. Az ablakon belüli kattintás nem zárja be a párbeszédet. A puszta megnyitás vagy bezárás nem módosítja a naptári edzéseket.

## Aktuális napi forrás, megőrzött teljes terv

A korábbi felület előbb a teljes, esetleg több korábbi forrást és kalibrációt tartalmazó utolsó tervet olvasta vissza. Ennek forrásellenőrzési hibája miatt az alternatívalista sem volt elérhető. Az új választó nem tölti be ezt az egész történeti fát: az adott edzés azonosítója és változatlan tartalomlenyomata alapján külön, friss, egynapos felülvizsgálatot kér. A gyakorlat-, időtartam-, dózis-, napfény-, heti terhelés- és célforrások szigorú ellenőrzése megmarad; a meglévő felméréseket nem kell újra elvégezni vagy igazolni ehhez a felületváltáshoz.

Az új kérés `workout-alternatives-request-v0.1`, mezői: `workout_id` és `expected_workout_hash`. Nem tartalmaz felhasználónak tulajdonított „még nem kezdtem el” nyilatkozatot. A korábbi, kézi megerősítéses szerződés a régi felülvizsgálatok olvasásához kompatibilisen megmarad.

Az egynapos felülvizsgálatok és elfogadások külön logikai történetben maradnak. Nem válnak a teljes program utolsó kalibrációjává, nem rövidítik le az elfogadott időszakot, és nem állítják át az automatikus tervezés dátumtartományát. A napi kérés csak a megnyitott edzést teheti cserélhetővé; a többi terv és teljesítés változatlan kötöttségként számít.

A felhasználó kattintással kiválasztott edzése megjelölést kap, és azt a későbbi automatikus tervezés megőrzi. A felhasználó az edzésre újból kattintva ismét választhat helyette másik, akkor elérhető változatot.

## A bizonyíték, lejárat és frissítés szerepe

Egy tervezett kezdési idő elmúlása önmagában nem bizonyít elvégzett edzést. Az alternatívák a saját teljes időigényük és tényleges időablakuk szerint járnak le. Az óra másodperces ellenőrzése eltávolítja a lejárt változatokat. Nyitott ablakban az elérhetőség 30 másodpercenként, illetve ablakfókuszkor újraellenőrződik.

A szerver elutasítja a cserét, ha a megnyitott terv megváltozott, más tulajdonoshoz tartozik, jóváhagyott külső cél lett, teljesített/kihagyott állapotba került vagy teljesítéshez kapcsolódik. Az adott napon már elkezdődött, rögzített tényleges edzés is megakadályozza az új napi választást akkor is, ha a tervhez való kapcsolása még nincs meg. Ez a mentés pillanatában, tulajdonosi zárolás alatt is ellenőrzött, így egy közben érkező import nem kerülhető meg egy korábban megnyitott kártyával.

A fennmaradó edzések időköze, terhelése, a napi/heti/cikluskeretek, a helyszín/eszköz, a napfény és az egészségi alkalmasság továbbra is számítanak. Ha ezek mellett nincs megfelelő csere, a felület emberi magyarázatot ad és az eredeti edzés megmarad. Az időjárási adatforrás továbbra sincs automatikusan bekötve.

Az újrakezdéshez a konkrét előírt edzésadag változatlan kell maradjon. Kattintás feldolgozása közben megváltozott időtartamot, súlyt, sorozatot, tartalékot vagy célt nem helyettesítünk észrevétlenül. Ilyenkor a friss lista jelenik meg új választáshoz. Dupla kattintásból nem lesz két mentés.

Elveszett hálózati mentési válasznál a megtartott kérésazonosítóval ugyanaz a mentés ellenőrizhető újra; ez nem hoz létre második edzést. Ez a helyreállítás csak tényleges kommunikációs hiba esetén jelenik meg, a normál választás egyetlen kattintás.

## Ellenőrzés

- Teljes backend tervezési készlet: **2431 sikeres teszt**. Az új napi kéréshez 20 eset ellenőrzi az olvasás naptári írásmentességét, az egyetlen nap cseréjét, a tulajdonost/hash-t, a teljesítést és utólagos bizonyítékot, lejáratot, jövőnapi választást, idempotens mentést, a teljes program megőrzését és a kézi választás automatikus megtartását.
- Teljes frontend: **1772 sikeres teszt**. Az új esetek ellenőrzik a napi kérés pontos tartalmát, a történeti állapot betöltésétől való függetlenséget, a dózist megőrző kattintást, a napra korlátozott mentést és a megerősítő pipák nélküli közvetlen felületet.
- Valódi FastAPI + React StrictMode/JSDOM próba: automatikus listabetöltés, olvashatatlan régi globális válasz kihagyása, belső és külső kattintás, közvetlen csere, dupla kattintás, elveszett válasz azonos kérésű helyreállítása, más napok megőrzése és új teljesítési bizonyítékra eltűnő alternatívák. A natív `close` esemény StrictMode alatti hatását is ellenőrzi.

Natív Windows- és natív böngészős vizuális próba nem történt. Az adatbázisséma változatlan. Mind a backend, mind a frontend frissítése és újraindítása szükséges. A `tools/run_c21_10_17_checks.py` az érintett backend- és frontendkészletet, a típusgenerálást, TypeScriptet, lintet és production buildet futtatja; a teljes készletek a szokásos `--full-backend` / `--full-frontend` kapcsolóval kérhetők.
