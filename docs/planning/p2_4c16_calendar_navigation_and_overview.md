# P2.4C16 – Napirend: gyorsnézet és görgethető áttekintés

## Viselkedés

- Az edzéskártya kattintása közvetlenül a tervezett edzés vagy a teljesítés részletes oldalát nyitja meg. Párosított teljesítésnél a teljesítés oldala nyílik meg.
- A jobb oldali részletsáv megszűnt. A naptár teljes szélességű marad.
- Hover és billentyűzetes fókusz rövid gyorsnézetet mutat a már lekért adatokból: kezdet, tényleges idő vagy jelölt becslés, táv, fő cél, ismert átlagpulzus, energia, kapcsolódó terv és ismert ütközés. Hiányzó adatot nem pótol feltételezéssel. További részletes adatokért az edzés oldala nyitható meg.
- Lefelé nyíllal a fókuszált kártya gyorsnézetébe lehet lépni. Escape vagy a naptár görgetése bezárja. Az egér átvihető a kártyáról a gyorsnézetre.
- Az 1 nap / 1 hét / 4 hét nézet gyorsnézetéből a fő cél külön modális űrlapon módosítható, és az edzésterv áthelyezője is megnyitható. A célmentés meglévő függőkérés-kezelése és a napirend húzása, átméretezése, áthelyezése, visszavonása megmaradt.
- Az edzéslehetőség és elfoglaltság kattintása továbbra is az idősáv szerkesztőjét nyitja. Hosszú áttekintésben a napi nézetre visz, ahol az adott nap friss szerkesztési kontextusa lekérhető.

## Időnézetek

A címkék: **1 nap**, **1 hét**, **4 hét**, **Áttekintés**. A korábbi 144 napos gomb megszűnt. Huszonnégy hét 168 nap.

Az Áttekintés hétfőtől indul, kezdetben 24 hetet mutat, hat 4 hetes részletben. Görgetés az időszak eleje vagy vége felé újabb 28 naptári napot kér le. A Korábbi / Következő 4 hét gomb billentyűzettel is használható és sikertelen betöltés újrapróbálására is szolgál.

- Egy időben csak egy új részlet töltődhet; gyors görgetés nem indít duplikált kéréseket.
- Betöltéskor a feed és a napirendi kontextus is lekérődik, csak olvasási kérésekkel. A dátumoknak, tulajdonosnak, időzónának és edzéslehetőség-referenciának egyezniük kell.
- Sikertelen részlet nem lépteti előre a betöltött ablakot. Újrapróbálás ugyanazt a részletet kéri.
- Legfeljebb nyolc 4 hetes részlet marad a megjelenített ablakban. Az ellenkező szélről kiesett részlet később újra lekérhető. Nem tárolódik a teljes végiggörgetett történet.
- Előre- vagy visszabővítéskor a látható részlet helyét DOM-horgony tartja meg. A naptár nem ugrik az újonnan hozzáadott részlet tetejére.
- Az alkalmazás meglévő 1900–2100 közötti dátumtartománya érvényes. Nem keletkezik mesterséges fejléc a támogatott tartományon kívülre.
- Frissítés vagy új dátum választása újra az induló 24 hetes ablakot olvassa. Az áttekintésből kiválasztott nap teljes napi nézetet nyit. Szerkesztéshez friss napi kontextus szükséges; a hosszú nézet nem ad új írási jogosultságot.

## Semleges edzéslehetőség-kijelzés

Az „Edzésidő-beállítás hiányos” felirat és lenyíló magyarázata megszűnt. A napi összesített időkeret nem ugyanaz, mint az egyenként megadott edzéslehetőség. A megadott idősávok láthatók maradnak, az üres nap nem hiba. Az ismeretlen napból nem lesz automatikusan szabad vagy tilos nap; a tervezési korlátok értelmezése változatlan.

## Navigáció

Az Edzéslista és a Menü mérete vezérlők a fő navigáció alatt kapnak helyet, az alsó saroktól távol. Kis képernyőn sem rejtődnek el. A Next fejlesztői állapotjelzője ki van kapcsolva (`devIndicators: false`), a fordítási és futási hibák továbbra is megjelennek.

## Ellenőrzés és határok

Frontendváltozás; nincs API-, adatbázisséma-, migrációs vagy szolgáltatói importmódosítás. A csomag a C14+C15+C15R1 állapotra épül, a C13 commit fölött, commit/push nélkül.

A csomag ellenőrzési eredményei a VALIDATION.json fájlban vannak. A helyi DOM-próbák szintetikus adatokkal futnak; a Windows böngészőben ellenőrizni kell a tényleges görgetési és hover-érzetet, valamint a 175%-os nagyítással használt nézetet.
