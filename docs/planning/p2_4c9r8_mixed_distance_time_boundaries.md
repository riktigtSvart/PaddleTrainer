# P2.4C9R8 — Távval és idővel előírt szakaszok közös idővonala

A tervblokkok helyreállítása után a távval megadott bemelegítésnek továbbra sem
volt időbeli végpontja. A korábbi vetület csak az explicit időtartamokat tudta
összeadni. Emiatt a kilenc kibontott szakaszból csak a 0:00 kezdőpont látszott.

## A terv és a minták kapcsolata

A meglévő, sportolóhoz kötött edzésrészletező GET az ismeretlen időtartam mellett
opcionálisan megőrzi a szakasz `distance_m` előírását a
`session-plan-timeline-v0.1` vetületben. A táv az idővonal ujjlenyomatának része.
Az API időtartam mezője ettől nem válik mért vagy becsült időtartammá.

A frontend a kiválasztott edzésrész eredeti `DISTANCE` mintasorát használja.
Egyetlen, ismert időközű, nem csökkenő össztávsor szükséges. Az edzés kezdetén
ismert nulla távminta kell; egy későbbi távszakaszhoz a kezdőidőpontra pontosan
illeszkedő, ismert távminta szükséges. A távszakasz célja a kezdőtáv és az előírt
szakasztáv összege. A végpont az első forrásminta, amely eléri ezt az értéket.
A közvetlenül előtte levő mintának is ismertnek kell lennie.

A következő időalapú szakaszok innen a saját előírt időtartamukkal következnek.
Újabb távszakasznál ismét az adott kezdőpont távmintájából indul a számítás.
Nulla táv explicit nulla marad. Hiányzó időköz, több versengő távsor,
számláló-visszaesés, ismeretlen kezdőminta, célértéknél levő mintahiány vagy
el nem ért céltáv esetén az érintett és az utána következő határok ismeretlenek
maradnak, külön felületi magyarázattal. Az előtte ismert határok megmaradnak.

A feldolgozás egy mintabejárást és távcélonként bináris keresést használ.
A mért görbéket és a forrásmintákat nem interpolálja vagy módosítja.

## Ismétlések és megjelenítés

A `REPEAT` egy szakaszcsoport. Két ismétlés esetén minden alárendelt rész
sorrendben kétszer kerül az idővonalra. A példabeli szerkezet:

1. 2600 m bemelegítés;
2. kétszer 12 perc munka + 2 perc pihenő;
3. ismét kétszer 12 perc munka + 2 perc pihenő.

Ez hét tárolt hierarchikus blokk, kilenc kibontott szakasz és tíz különálló
határpont. A két ismétlési csoport eredeti blokkazonosítói és eltérő céljai
megmaradnak. A csoport maga nem lesz külön, ismeretlen hosszúságú munkaszakasz.

A felület felirata: **Számított tervhatárok · mért távsor alapján**. A jelölések
felbontása az eredeti távminták időköze. Minden grafikon ugyanazokat a határokat
kapja, sebességegységtől függetlenül. Az automatikusan kibontott táblázat mutatja
az előírást, a kezdetet, a véget és a távmintákból számolt időtartamot. A
nagyítás és a meglévő határvonal-kapcsoló ezekkel is használható.

A számítás a terv sorrendjét követi. A Polar által rögzített tényleges fázisváltás
igazolása ettől külön adat marad. A kézi váltás, egy kimaradt ismétlés vagy egy
rövidebbre teljesített utolsó pihenő eltérhet ettől az idővonaltól. Az utolsó
tervezett pihenő hosszát nem rövidíti a felvétel vége; a terv végéig kiterjesztett
nézetben a mért görbe a tényleges mintasor végén ér véget.

## Telepítés és ellenőrzés

Előfeltétel: pontosan az alkalmazott C9–C9R7 forrásállapot; még commit nélkül,
`main` és a helyi `origin/main` a `5dbcf3b9b038f63c5b17eafa496eb3e0ea1014ca`
commithoz kötve. A csomag tizenegy fájlt változtat. Nincs migráció, függőségcsere,
új szolgáltatói kérés vagy adatbázis-javítás. A már helyreállított hét blokkot
és a már átvett távmintákat olvassa. Az API és frontend újraindítása után az
**Adatok újraolvasása** gomb frissíti a nézetet.

A tesztek izolált adatbázissal és szintetikus mintákkal ellenőrzik a tulajdonoshoz
kötött vetületet, a távcél megőrzését, a két ismétlési csoportot, az ismeretlen
határok megőrzését, a különböző mintavételi időközöket és a változatlan mért
adatokat. A felületi próbák tényleges React vezérlőket, a zárt proxyt és az
izolált FastAPI végpontot használják. A csomag a korábbi backend- és frontend-
regressziókat, a teljes TypeScript ellenőrzést, a módosított fájlok ESLint
ellenőrzését és a production buildet is lefuttatja.
