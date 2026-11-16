# C21.10.7 — mezocikluscélok és mikrociklusok a naptárból

## Megnyitás és tartalom

A mezociklus és mikrociklus kezdő/záró felirata valódi, billentyűzettel is elérhető gomb. A naptár feletti szakaszjelző és a Felkészülés menü mezociklusai ugyanazt az ablakot nyitják. Mikrociklus-jelölés esetén az adott szakasz sora kap hangsúlyt. A jelölés nem edzés, nem nyit idősávszerkesztőt, és nem növeli az eseményszámot.

Az ablak a teljes mezociklusra kér adatot, függetlenül a naptár éppen látható dátumablakától. A kezdő és tervezett záródátum évvel együtt látszik, továbbá a jelenlegi nap helye a szakaszban. A mentett képességcélok fő fejlesztési, másodlagos fejlesztési, fenntartási és megengedett átmeneti visszaesési szerep szerint szerepelnek, saját indoklásukkal. A teljes ciklusadatlap és a célok szerkesztője külön hivatkozással elérhető.

A célok a makrociklusterv legutóbbi, az adott sportolóhoz és mezociklushoz tartozó mentett utasításaiból jönnek. Nem képezzük őket a sportág vagy az edzés címéből. A legutóbbi tervezési felülvizsgálat kimaradási okai külön, dátummal jelölt információként jelenhetnek meg; ez segít például megérteni egy hiányzó erőcélt. A megnyitás nem futtat új tervezést és nem írja át a kiosztást.

## Mi számít teljesítésnek?

Az összegzés a sportolói időzónában, a mezociklus kezdő és záró civil napja között számol. A lezárt tényleges edzés akkor kerül a befejezett összegzésbe, ha a befejezési időpontja a lekérésig már eltelt. A kapcsolt tervet és tényleges edzést nem számoljuk két teljesítésnek. A jövőbeli, aktív, tényleges teljesítéshez még nem kapcsolt terv külön jelenik meg.

A céljelölés sorrendje: saját explicit edzéscél, kapcsolt terv explicit céljelölése, majd a kapcsolt, ellenőrzött elfogadott terv fő célja. A felhasználó által kifejezetten törölt cél üresen marad. Egy cél nélküli kézi vagy importált erősítés így látszik a sportági összegzésben, de nem lesz automatikusan maximáliserő-fejlesztésnek minősítve.

A hiányzó időtartam külön jelzést kap; nem tekintjük nulla terhelésnek. A lejárt, teljesítéshez nem kapcsolt tervből nem állapítunk meg kihagyást. A befejezetlen tényleges rögzítés és a tényleges edzésadat nélkül teljesítettnek jelölt terv szintén külön számlálást kap. Alkalomszámot és ismert időt mutatunk, nem kitalált célmegvalósulási százalékot. A képesség változásának igazolásához összehasonlítható felmérés szükséges.

## Kapcsolható színek mind a négy nézetben

A **Mikrociklusok terhelési színei** kapcsoló alapból kikapcsolt. A beállítás sportolónként és napi/heti/négyhetes/áttekintő nézetenként külön tárolódik. A korábban mentett naptári láthatósági kapcsolók megmaradnak; régi beállításból az új kapcsoló kikapcsolt értéket kap.

| Szín | Jelenlegi jelentés | Rögzített kezdőkeret aránya |
| --- | --- | --- |
| Zöld | Közepes, rávezető szakaszkeret | 80% |
| Sárga | Emelkedő szakaszkeret | 90% |
| Piros | Felső tervezési keret | 100% |
| Kék | Könnyebb szakasz | 70% |

Ezek a már meglévő `training-mesocycle-policy-v0.1` mennyiségi keretei. Nem intenzitási zónák, becsült fáradtság vagy személyes fiziológiai határterhelés. Az erőgyakorlatok súlya és ismétlésszáma ettől nem nő. A rövid utolsó mikrociklus kerete továbbra is a tényleges napokkal arányos; nem színezünk át automatikusan egy rövid maradékot regeneráló hétnek.

Kizárólag az utolsó elfogadott terv mentett, összehangolt mikrociklus-blokkjai színeznek. Egy új, még el nem fogadott felülvizsgálat nem festi át a naptárat. Ha a ciklus dátumai az elfogadás óta megváltoztak, a régi színeket nem vetítjük az új napokra. Rövid dátumablakra elfogadott tervből nem találunk ki teljes havi hullámot. A hiányzó, ütköző vagy korábban nem lefedett szakasz szín nélkül marad. A jelmagyarázat ezeket a korlátokat is közli.

A napi/heti nézet napfejléce és naposzlopa, valamint a négyhetes és görgethető áttekintő nézet napcellája kap visszafogott háttérszínt. Az edzések meglévő fő cél szerinti színezése és a kijelölt nap jelzése megmarad. A Felkészülés ciklushatár-réteg és a háttérszínezés külön kapcsolható.

## Adatút és hibakezelés

Az új `GET /api/v1/planning/calendar/cycles` végpont a bejelentkezett alkalmazástulajdonos legfeljebb 366 napos, legfeljebb 100 mezociklust tartalmazó ablakát olvassa. A kliensoldali közvetítő csak GET-et és a két dátumparamétert engedi; másik tulajdonos paraméterként nem adható át. A célverziók és elfogadási/tervezési bizonylatok saját meglévő ellenőrzőiken mennek át. A válasz ellenőrzött tartalomhashét, dátumait, céljait, blokkhatárait és számait a böngésző is vizsgálja.

A ciklusadatok betöltése külön folyamat a naptártól. Hibáját a felület megjeleníti; az edzések olvashatósága ettől nem áll le. A modal bezárása megszakítja a hozzá tartozó kérést, a késői válasz nem nyitja újra. Bezárás és Escape után a fókusz visszatér a megnyitó jelölésre. Nincs automatikus POST, módosított adatbázistábla, új függőség vagy edzéstervezési szabályváltozás.

## Ellenőrzés

A `tools/run_c21_10_7_checks.py` a teljes backend-tervezési és frontend-regressziót, Next típusgenerálást, TypeScriptet, ESLintet és production buildet futtatja. Az új API-próbák ellenőrzik a mentett erőcélt, az elfogadott blokkok egyezőségét, a puszta előnézet változatlanságát, az elmozdított ciklus színeinek visszatartását, a tulajdonosi elhatárolást és az olvasás változatlanságát.

React StrictMode/JSDOM és valódi FastAPI együtt ellenőrzi a kezdő/záró jelölésről megnyitott ablakot, a teljes ciklus céljait és edzésadatait, a négy külön tárolt kapcsolót, újracsatolás utáni visszatöltést, fókusz-visszaadást, Escape-et és a bezárás után érkező választ. A megnyitás előtti és utáni audit-, edzésterv- és ténylegesedzés-rekordszám azonos. A telepítési csomag README-je tartalmazza a tényleges tesztszámokat és parancsokat.
