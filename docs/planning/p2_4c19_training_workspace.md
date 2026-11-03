# C19.0 – integrált edzéstervezési munkafelület

## Felhasználói folyamat

A fő navigáció asztali nézetben rögzített. Naptár, Edzéstervezés, Edzési
lehetőségek, Táplálkozás, Bevásárlás, Személyes adatok és Beállítások szerepel
benne. Csak az aktív főmenüpont alatt jelenik meg az almenü. Mobilon a navigáció
a rendelkezésre álló helyhez alkalmazkodik. Az új felületek a meglévő alkalmazás
témaváltozóit használják, ezért a világos és sötét téma közös marad.

Az `/training-planning` nyolc egymás alatti, összecsukható lépést tartalmaz:

1. Cél és tervezési időtáv: meglévő vagy új felkészülési program.
2. Személyes alapadatok és mozgáskeretek: a meglévő sportolói felmérés.
3. Előzmények és kiindulópont: az elérhető adatok áttekintése, pontosítása.
4. Edzési helyszínek és lehetőségek.
5. Általános órarend.
6. Az aktuális hét nap lehetőségei.
7. A teljes időszak fejlesztési stratégiája és fejlesztési szerepei.
8. Edzésterv, naptár és edzésváltozatok.

A szükséges első lépés nyílik ki induláskor. Minden blokk megmondja az elvárt
adatot és összefoglalja a mentett állapotot. Frissítés nem váltja át önkényesen
a megnyitott lépést. Az előzmények pontosítása külön, nem kötelező lépés; a
tervező ugyanakkor továbbra sem pótol hiányzó személyes bizonyítékot kitalált
adattal. A cél és a stratégia a meglévő, mentett ciklusprogramhoz kapcsolódik.

## Helyszínek és öröklés

Az `/training-options/locations` oldalon saját névvel, sportokkal, felszereléssel
és megjegyzéssel vehetők fel helyszínek. Külön induló vázlat tartozik az otthoni,
a változó futási és a változó evezési helyszínhez. A vázlat csak kifejezett
mentéskor lesz alkalmazásadat. A változó evezési helyszínhez a hajószállítás
lehetőségét is meg kell adni. A helyszínek archiválhatók, azonosítójuk megmarad.

Az `/training-options/schedule` hét napos táblázatában naponta több idősáv
adható meg. Egy idősávhoz több helyszín választható: ezek alternatívák, egyetlen
közös időkerettel. Az általános terhelési lehetőség alapértéke `any`, vagyis nincs
külön szűkítés. Egy helyszín saját sportjai és saját felszerelése érvényesek;
a rendszer nem kölcsönöz felszerelést más helyszín vagy az általános profil
listájából. A kombinálhatóság külön deklarálható.

Az órarend kezdőnapja és opcionális végdátuma határozza meg az érvényességét.
Végdátum nélkül módosításig marad használatban. Az érvényes általános órarendben
üresen hagyott nap nem elérhető nap. A helyszínjegyzék önálló mentése még nem
váltja le a korábbi naptári lehetőségeket; ehhez tényleges órarend kell.

Az aktuális hét nap erre épül. Egy alkalom dátumhoz kötött felülírást kaphat,
visszaállítható az általánosra, illetve átmeneti sporttilalom rögzíthető egy
helyszínre. Az eltérés nem módosítja a heti mintát. A dátumhoz kötött korlátozás
lejár, és nem zárja le végleg a helyszínt. A „Változás nélkül tovább” nem küld
mentést. A már rögzített naptári elfoglaltságokat a tervezés továbbra is levonja.

## Részletes terv és változatválasztás

A részletes horizont a programban ténylegesen mentett aktuális és következő
mezociklusból származik, nem két rögzített négyhetes mintából.
A belső tervfelülvizsgálat legfeljebb 366 napos. A régi, nyilvános
`planning-inputs` végpont 28 napos korlátja változatlan.

A kimenet naptárt és egymás melletti hét egymást követő napot mutat.
Alapértelmezésben ma és a következő hat nap látszik; naponta lapozható, és a
„Mától 7 nap” visszaállítja. Nincs időpont szerinti naptárrács. A sportoló
időzónája érvényesül, éjfélkor frissül a gördülő nézet.

Egy nap teljes kártyája kattintható. Kattintásra az összes ténylegesen elérhető
edzésváltozat saját, teljesen nyitott blokkban jelenik meg, teljes leírással és
edzésblokkokkal. Nincs külön „Részletek” gomb. Az ajánlott és a kiválasztott
változat jelölése különbözik. A nem használható helyszíneknél az ok látszik.

A változatválasztás új szerveroldali tervjavaslatot készít az egész vizsgált
időszakra, megmutatja a tényleges napközi eltéréseket, és visszavonható. Ez még
nem ír edzést a naptárba. A meglévő felülvizsgálati és kifejezett elfogadási
lépés rögzíti a tervet. Az importált, teljesített, kézzel módosított és védett
edzések megőrzése, valamint az elavult terv elfogadásának tiltása megmaradt.

## Adatkezelés

- `GET/POST /api/v1/planning/training-options`: sportolóhoz kötött deklaráció,
  append-only revíziók, előző állapot ellenőrzése, pontosan ismételhető mentés.
- `POST /api/v1/planning/cycles/programs/{identity}/training-plan/choose`: ellenőrzött korábbi
  tervváltozatból kiválasztott, tényleges jelölt alapján készülő új javaslat.
- A böngésző az azonos eredetű `/api/goal-workflow` közvetítőn keresztül dolgozik.
  A lekérdezések és a törzsek zárt sémájúak.
- Ismeretlen kimenetelű mentésnél a pontos függő kérés helyreállítható. Az oldal
  újbóli megnyitása nem küld automatikusan POST-ot. Az azonos mentés újraküldése
  nem hoz létre másolatot.
- A beállítások mentése nem módosít edzést, és nem ad automatikus engedélyt a
  terv naptárba írására. Új adatbázismigráció és új függőség nem szükséges.

## A kiadás határai

Ez az első integrált munkafelület a meglévő tervezőmotorra épül. A motor jelenleg
három konzervatív mintát támogat: könnyű 30 perces kajak, saját előzménnyel
igazolt 60 perces kajak, illetve saját előzménnyel igazolt 30 perces erősítés.
A hét napra jutó 3 alkalom / 180 perc és a legalább 36 órás kezdési távolság
változatlan. Az ajánlott jelölés e meglévő szabályzat választását jelenti;
nem teljesítménymodellből számított, egyéni fejlődési optimumot.

A futás, úszás és más sportok helyszíni lehetősége már megadható. Az új
sportágak konkrét edzésmintái és az összetett alkalmak automatikus előírása
további motorfejlesztés. A C18.5-ben bevezetett, saját állóképességi
teljesítésekből készülő, korlátozott táv–időbecslés továbbra is rendelkezésre áll;
ez a kiadás nem bővíti új fiziológiai vagy dózisoptimalizáló modellel.
A felület ezeket nem mutatja megvalósult edzésjavaslatként. A táplálkozási
menüpont egyelőre ezt egyértelműen jelző belépőoldal. Helyszínajánló vagy reklám
nem része ennek a kiadásnak.

## Ellenőrzés és telepítés

A `python tools/run_c19_checks.py --build` a teljes backend planning regressziót,
az összes frontend egységtesztet, a Next útvonaltípusokat, a TypeScriptet,
az érintett felületek ESLint ellenőrzését és a produkciós buildet futtatja.
A projekt saját virtuális környezetének Pythonjával kell indítani.

Az új tesztek valós FastAPI/SQLite környezetben ellenőrzik az öröklést,
helyszínhez kötött felszerelést, idempotens mentést, kivételeket, időzónát és
a választott edzés egész horizonton megőrzött hatását. A frontend a backend
által ténylegesen előállított, szintetikus tesztadatot ellenőrzi. Egy külön
React StrictMode életcikluspróba valós végpontokkal, izolált adatbázison
igazolta az elveszett mentési válasz helyreállítását, az újranyitás írásmentességét,
két alternatív helyszín közös idősávját és az általánost megőrző napi kivételt.

A frissítőcsomag minden érintett fájlt ellenőriz az összes írás előtt. Ismeretlen
helyi módosításnál megáll; az LF/CRLF sortörés eltérést megengedi. Mentést készít
a felülírt fájlokról. A csomag nem tartalmaz felhasználói adatbázist,
környezeti titkokat vagy szolgáltatói munkamenetet.
