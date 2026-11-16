# C21.6 – Sportmúlt és sportcélok

A C21.5 frissítésre épül. Backend és frontend együttes frissítése szükséges. Nincs új függőség vagy adatbázis-migráció.

## Elnevezések és felület

- Az elsődleges menüpont, az oldal címe és a kapcsolódó hivatkozások neve **Edzéstervezési alapadatok**.
- A harmadik fejezet **Sportcélok és felkészülés**. A korábbi útvonalak és könyvjelzők megmaradnak.
- Felül az **Új cél kitűzése** kártya négy gombot kínál: Olimpiai ciklus, Szezon, Versenycél, Rekreáció. Az új szerkesztő a meglévő célok alatt jelenik meg; a nézete odagördül, a címe billentyűzetes fókuszt kap.
- Egy mentett cél saját kártyájában szerkeszthető. Először a két dátum, majd a külön verseny- és edzéscélkártyák következnek. Az automatikusan előállított mezociklusok alapból összecsukva maradnak.
- A cím és a sportág külön lenyitható. Olimpiai célnál a választott játékok adják a záródátumot. Rekreációnál a zárónap az aktuális, véges makrociklusra vonatkozik; maga a rekreáció folytatható.
- A ciklusonkénti képességszerepek a cél saját, lenyitható fejlesztési részében megadhatók. Ezek a meglévő tervező számára szükséges edzéscélok. A mérési protokollok és eredmények teljes munkafolyamata az Állapotfelmérésből továbbra is elérhető.
- Új cél hozzáadható, a piszkozat céljai módosíthatók és törölhetők. Egy célkitűzés mentése együtt rögzíti a dátumokat, versenyeket, általános edzéscélokat és a ciklusbontást. A részletes ciklusonkénti képességszerepek saját mentéssel rendelkeznek.

## Sportmúlt

A felkészülési szerep és a versenyzési szint külön adat. A korábbi szintértékeket a frissítés nem osztályozza át.

- **Fő sport:** a versenyzési előélet és a korábbi/jelenlegi szint megadható. Opcionálisan több távhoz rögzíthető egyéni csúcs és friss eredmény.
- **Kiegészítő sport:** megjelölhető, mely fő sportokat támogatja, és milyen céllal használja a sportoló: állóképességi helyettesítés, erő, erőállóképesség, gyorsaság/robbanékonyság, technika, mobilitás, általános felkészítés, regeneráció vagy más cél. A gyakorlati jártasság külön kérdés. A versenyzési előélet megmarad opcionális résznek.
- **Szabadidős sport:** a jártasság megadható; felvétele önmagában nem teszi a felkészülési program részévé.

Az időeredmény sporthoz és szakághoz kötött. A táv méterben, az idő perc:másodperc vagy óra:perc:másodperc formában adható meg, legfeljebb három törtmásodperc-jeggyel. A tizedesvessző ponttá normalizálódik, a megadott pontosság megmarad. A dátum lehet pontos nap, csak év vagy ismeretlen. A körülmények és a forrás külön rögzíthetők. Hiányzó dátumból nem lesz mai mérés; hibás vagy jövőbeli eredmény nem menthető.

Ezek tartós, önbevallott tájékozódási adatok, és bekerülnek a profil tervezési bemeneti pillanatképeibe. Az edzésadag számszerű meghatározása továbbra is a meglévő, friss és megfelelően hivatkozott felmérési/edzésadatokra épül. Ez a változat nem illeszt új élettani modellt a régi csúcsokra, és nem vált át automatikusan sportágak közötti tempót, pulzust vagy terhelhetőséget.

## Szakirodalmi háttér és termékdöntés

Blythe és Király futóeredményeken végzett vizsgálata szerint a több távon elért egyéni teljesítményben hasznos információ van a teljesítményprofilról és a specializációról. Ebből termékdöntésként a korábbi eredmények sporthoz, távhoz, időponthoz és körülményekhez kötött megőrzését vezetjük le; a cikk nem igazol tetszőleges régi rekordból mai edzésadag-előírást.

- Blythe, D. A. J.; Király, F. J. (2016): [Prediction and Quantification of Individual Athletic Performance of Runners](https://doi.org/10.1371/journal.pone.0157257).
- Tanaka, H. (1994): [Effects of cross-training. Transfer of training effects on VO2max between cycling, running and swimming](https://doi.org/10.2165/00007256-199418050-00005). A sportágak közötti átvihetőség és a specifikusság korlátai indokolják, hogy a kiegészítő mozgás szerepe külön adat legyen.

## Tartós mentés és visszaállíthatóság

A mentett teljes célkitűzések módosítása `cycle-program-replacement-v0.1` hivatkozásokkal új regisztrációt hoz létre a meglévő audit-tárolóban. A korábbi program, versenyváltozat és ciklushatár-változat pontos hivatkozása megmarad. A szerver ellenőrzi a tulajdonost, a teljes hivatkozási láncot és a legutóbbi forrásállapotot. Egy előzményhez egy következő változat tartozhat; a különböző párhuzamos mentések ütközése írás nélkül megáll.

A korábbi periódusokat és edzéseket a művelet nem írja át. Az új listanézet a cél aktuális változatát mutatja; a korábbi bizonylatok továbbra is pontosan visszaolvashatók. A rekreáció folytatása és egy már létező cél módosítása külön kapcsolat marad: a közös programcsalád nem helyettesíti az előzmény pontos hivatkozását.

A szerver egy tranzakcióban menti az új teljes ciklusgráfot és a bizonylatot. Hibás dátum, idegen előzmény, elavult forrás vagy eltérő azonos kérés esetén nem keletkeznek részleges periódusok. A függő kérés eredeti bájtjai megmaradnak; újratöltés nem küldi el automatikusan. Azonos újraküldés az eredeti eredményt igazolja. Elutasított programmentés visszaállítható szerkesztésre.

Ha az automatikus tervezés még a módosított cél korábbi változatára mutat, megáll és jelzi az új célok áttekintését. Az új változat ciklusonkénti céljainak átnézése után az Állapotfelmérés végén indítható a tervezés az új adatokkal. A korábbi bizonylatok új opcionális mezők nélkül is változatlan tartalommal és hash-sel olvashatók.

## Ellenőrzés

- Teljes meglévő backend-tervezési regresszió, valamint az új 17 célmentési/sportmúlt-teszt. A végső érintett ciklus-, sportolói- és automatikus tervezési kör külön is lefutott: 180 sikeres teszt.
- 1266 frontendteszt; Next route-típusok, TypeScript, ESLint, production build.
- Valódi HTTP API-val működő DOM-ellenőrzés: mentett cél dátumának és edzéscéljának módosítása, a régi cél változatlansága, új kártya hozzáadása és fókusza, írás nélküli oldalbetöltés, megszakadt válasz utáni azonos újraküldés és elutasított kérés szerkesztésének visszaállítása.
- Valódi API-val működő profil-ellenőrzés: új időeredmény kézi megadása tizedesvesszővel és csak évvel, tartós mentése, a korábbi eredmények és kiegészítő célok megőrzése; a személyes és sportolási adatok külön mentése.
- A hat fejezet, az oldalsáv, a piszkozat megőrzése és az egyetlen látható mentési rész DOM-ellenőrzése. Böngészős képernyőképes ellenőrzés nem készült.

Teljes helyi ellenőrzés: `python tools/run_c21_6_checks.py`. A telepítő ellenőrzésének és visszaállításának lépései a csomag README-jében vannak.
