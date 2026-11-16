# C21.10.5 — mentési visszajelzés, ciklushatárok és célok képviselete

## Mentési kísérletkor is látható hiba

A böngésző natív érvényességvizsgálata megállíthatja az űrlap elküldését, mielőtt a React `onSubmit` kezelője lefutna. Emiatt a korábbi, kizárólag az elküldési kezelőben kiírt hiba nem feltétlenül jelent meg. A közös blokkmentő gomb most még az elküldés előtt megkeresi az első érvénytelen mezőt, és a mező nevével együtt megjeleníti az okot a blokk mentési visszajelzésében. A mező nyitható szülője kinyílik, a mező fókuszt kap. Javítás után a natív hiba törlődik, az eredeti mentési folyamat fut tovább.

A közös gomb a natív `invalid` eseményt is figyeli: az Enterrel vagy `requestSubmit`-tal indított, elutasított küldés is látható visszajelzést kap. A megadott `noValidate` és `formNoValidate` beállítás megmarad. Az általános órarend és a napi eltérés saját idősávszerkesztője is kiírja a natív elakadás okát; a 90 perces ablakhoz megadott 120 perces edzéskeretnél az idősávra vonatkozó részletes üzenet az elsődleges. A napi eltérés mentésekor sem cseréljük általános üzenetre a konkrét idősávhibát.

A szerveroldali validálás, a bizonylat ellenőrzése és az eredeti függő kérés megőrzése változatlanul szükséges. A helyi hiba felismerése nem küld új vagy automatikus szerverírást. A C21.10.4 ugyanabban a böngészőfülben frissítés esetére megőrzött órarend-piszkozata ebben a csomagban is benne van.

## Ciklushatárok a naptáron

A **Felkészülés** kapcsoló a naptár mind a négy nézetében megjeleníti a mezociklusok és mikrociklusok kezdő és záró jelöléseit. A mezociklus színes folytonos, a mikrociklus szaggatott jelölést kap, szöveges névvel is. A jelölés nem edzésesemény: nem növeli az edzések vagy alternatívák számát, és nem foglal terhelési keretet.

A naptár felett a kijelölt naphoz tartozó mezociklus címe, az azon belüli nap, a mikrociklus sorszáma, időtartama és dátumhatára látszik. A cím a meglévő mezociklus-adatlapot nyitja meg. A helyzet a naptárban használt civil dátum alapján számolódik.

A mezociklus határai a naptári API mentett időszakaiból jönnek. A jelenlegi generátor a mezociklus kezdetétől számolt, legfeljebb hétnapos blokkokkal dolgozik; a naptár ugyanezt a dátumfelosztást vetíti ki. Ezek nem ISO-hetek, és nem feltétlenül hétfőn kezdődnek. A rövid utolsó blokk nem lesz mesterségesen teljes hét. A 29 napos, csütörtökön kezdődő és az őszi óraátállítást átfogó szakasz 7+7+7+7+1 napos felosztással ellenőrzött.

Ez a megjelenítés nem vezet be új, önállóan szerkeszthető mikrociklus-adatbázist vagy változó hosszúságú fiziológiai ciklusmodellt. A C21.10.4-ben rögzített rugalmas mikrociklus továbbra is következő fejlesztési irány; a jelenlegi hétnapos tervezési szakaszokat tesszük láthatóvá.

## Miért maradhatott csak futás?

A felhasználói képből a személyes szerveradatok hiányában nem lehet biztosan megállapítani a kimaradás okát. Valódi API-próbában viszont reprodukáltuk: az általános órarend módosítása megváltoztatja a kezdeti erőfelmérés forrását. A jelenlegi felmérési szerződés szerint ilyenkor a korábban megadott válaszok felülvizsgálatra várnak. Az erősítő minta kimarad, miközben a könnyű futás továbbra is tervezhető. Az új órarendhez tartozó válaszok áttekintése és mentése után ismét bekerülhet az erősítés. Ez nem egy új fizikai teszt automatikus előírása.

Az úszásnál továbbra is szükséges a megfelelő időablak, az adott helyszínhez tartozó medence és medencehossz, valamint az önálló úszástudás és a választott úszásnem megadása. A kajaknál a sport-, eszköz-, idő- és napfénykorlátoknak is teljesülniük kell. Az úszás és a futás egyaránt adhat mintát az oxidatív cél támogatására; pusztán a sportág felvétele nem követeli meg, hogy mindegyikből külön edzés kerüljön be minden héten. A kajakos technika fenntartását viszont a futás címkéje nem igazolja.

## Kiosztási javítás és látható hiányok

A `training-plan-policy-v0.10` összehangolt módban a mikrociklusban még nem képviselt mentett célt a már képviselt cél újabb ismétlése elé helyezi. Ezután érvényesül a szerep elsőbbsége, a meglévő sportági és erő/aerob kiosztás, valamint a többi sorrendi szempont. A technika fenntartási szerepét így nem szorítja ki korlátlanul egy ismételten választott aerob fő cél. Azonosan még nem képviselt célok között továbbra is a fejlesztési szerep és a korábbi kiosztási szabályok döntenek. Ez kiosztási termékszabály, nem tudományosan igazolt optimális gyakoriság vagy személyes regenerációs becslés.

A változás csak a lehetséges edzések sorrendjét befolyásolja. A gyakorlathoz tartozó saját referencia, a felmérés érvényessége, az időjárástól független jelenlegi napfénykorlát, a helyszín/eszköz, a gördülő heti és mikrociklus-keret, az edzésközi térköz, a napi egy új javaslat és a korábbi védett teljesítések szabályai megmaradnak. Új súlyt, sorozatot, intenzitást vagy heti terhelési keretet ez nem ad hozzá.

A sportági összegzés új `training-sport-availability-v0.3` változata mezociklusonként, képességenként és fejlesztési/fenntartási szerepenként jelzi:

- hány javasolt edzésnek ez a fő célja;
- hány naphoz készült a célt támogató mintacsaládból választható változat;
- van-e már képviselt cél, maradt-e ki választható cél, vagy jelenleg nem elérhető/nem támogatott a minta;
- milyen konkrét kizárási okokat adott az érintett sportágak vizsgálata.

A lefedetlen célok külön, alapból látható figyelmeztetést kapnak a naptár felett. A részletes okok és teendők kinyithatók; az erőfelméréshez, a helyszínhez és az úszás beállításaihoz hivatkozások vezetnek. Az elérhető, de ki nem osztott úszó vagy más sportági alternatívát megkülönböztetjük a kizárt sportágtól. Az összegzés a legutóbbi felülvizsgálat mintajavaslatairól szól; az importált vagy külön szerkesztett edzéseket nem minősíti át. Egy képviselt cél vagy egy húszperces minta nem bizonyítja a fejlesztési dózis elégségességét, illetve az alkalmazkodást.

A teljes felülvizsgálat böngészőoldali ellenőrzése újraszámolja a céllistát a mentett forrásnapokból, majd az edzés- és alternatívaszámokat, a támogatott sportágakat és a hiány indokait is összeveti a tervvel. Másik mezociklus, elhagyott cél, kitalált teljesülés vagy meghamisított darabszám elutasított, újra aláírt próbaadat esetén is. A régi v0.1/v0.2 sportági összegzések és a v0.9 tervezési bizonylatok továbbra is olvashatók.

## Ellenőrzés és telepítési határ

A csomag C21.10.3-ra és C21.10.4-re közvetlenül telepíthető, és tartalmazza a C21.10.4 javításait is. Nincs új függőség vagy adatbázis-migráció. A backend és a frontend is változik, mindkettőt újra kell indítani. A **Terv frissítése most** az új tervezési és hiányjelzési szabályokkal vizsgálja meg a jelenlegi adatokat.

Ellenőrzött: a teljes frontend-regresszió; az új API céllefedettségi és kizárási próbák; a teljes backend-tervezési regresszió; TypeScript, ESLint és production build. A pontos darabszámok a csomag README-jében vannak. A típusellenőrzés a naptári áttekintő nézet új megjelenítési paraméterének külön deklarálását is ellenőrzi.

Valódi FastAPI-próbákban az órarendváltás miatti erőfelmérési forráseltérés, a válaszok újraellenőrzése utáni vegyes terv, az úszástudás hiánya, a technikai fenntartás képviselete és a változatlan ismételt tervelfogadás is ellenőrzött. A valódi API-ból kapott teljes felülvizsgálatok a böngésző ellenőrzőjén is átmentek. React StrictMode/JSDOM próbában a közös blokkmentés visszajelzése, a zárt rész kinyitása, a hibajavítás utáni egyetlen elküldés és az Enteres hibajelzés ellenőrzött. A C21.10.4 32/33 idősávos, piszkozat-visszaállítási és elvesztett mentési válaszos integrációs próbája is sikeres az új kóddal.

Natív Chromium vizuális ellenőrzés ebben a futtatókörnyezetben nem áll rendelkezésre; a megjelenítés ellenőrzése komponens- és DOM-alapú. A csomag nem állít személyes terhelési optimumot vagy teljes mezociklus-előírási modell készültségét.
