# PaddleTrainer funkcióleltár

Állapot: C20.7.1, 2026. november 7. A jelenlegi sportolói webfelület forráskódjából összeállítva.

60 funkcióegység, 17 oldal, négy felhasználói folyamat és 11 rendszerezendő pont. Az egységek felhasználói feladatok, nem minden egyes gomb külön funkció.

A leltár a meglévő működést írja le. A „Rendszerezendő pontok” és a táblázat üres új csoport/név/prioritás/megjegyzés oszlopai az átrendezés előkészítését szolgálják. A menüt ebben a kiadásban nem terveztük újra.

## A hasonló nevű felmérések szerepe

| Felület | Mire való? | Mi az eredménye? |
|---|---|---|
| Sportolói felmérés | Alapadatok, sportmúlt, részvételi és heti keretek. | Mentett profil. |
| Kezdeti sportági és erőfelmérés | Sportági szerepek, gyakorlatok, jártasság, ismert referenciák. | Mentett kiinduló válaszok; a kitöltöttség nem új mért teljesítmény. |
| Vezetett kezdő erőfelmérés | Konkrét próba utasítása, végrehajtása és eredményének kézi rögzítése. | Elvégzett próbák, naplókapcsolat és használható saját referencia. |
| Célok és mérések | Ciklushoz rendelt, előre rögzített mérés és változásértékelés. | Protokollhoz kötött eredmény és célértékelés. |
| Saját visszajelzés | Az edzés utáni / másnap reggeli megfigyelés. | Szubjektív válaszok, külön kapcsolattal az elemzés felé. |

## Támogatás és megőrzés

- A helyszíni katalógus 94 eszköztípust és 120 gyakorlat-/ergométerbejegyzést tartalmaz. 115 erőgyakorlathoz van vezetett felmérési utasítás.
- A felmérési nyilvántartás 14 sportági bejegyzést ismer: kajak, kenu, evezés, futás, kerékpározás, úszás, gyaloglás, túrázás, sífutás, foci, erősítés, gimnasztika, nyújtás/mobilitás és Egyéb sportág.
- Az automatikus mintatervezés jelenleg kajak-, futó- és erősítő mintákat használ. A többi sportág profilja és referenciája kezelhető, de ez még nem jelent hozzájuk teljes automatikus tervgenerálást.
- A szerverre mentett profil, felmérés, tényleges próba, célmérés, visszajelzés és elfogadott terv külön adat. A helyi piszkozat és a grafikon böngészőlapi kézi jelölése nem helyettesíti a szerveres mentést.
- Saját testsúlynál az új kezdő felmérés célja az ismert változatban végzett szabályos ismétlések megfigyelése. Nincs 10 ismétléshez választandó kg-terhelés. A 12-es megfigyelési határ nem maximális ismétléskapacitás. A két sorozatos megfigyelés sem ad még teljes erőállóképességi vagy sorozatkapacitás-besorolást.

## Oldalak és jelenlegi belépők

| Útvonal | Oldalcím | Belépő | Szerep |
|---|---|---|---|
| / | Naptár / Napirend | Főmenü | Naptár, elérhetőség, terv és teljesítés. |
| /training-planning | Edzéstervezés | Főmenü, Tervezés lépései | Kilenc beágyazott tervezési lépés. |
| /athlete-setup | Sportolói felmérés és edzéslehetőségek | Személyes adatok | Profil, naptár és előzmények fülek. |
| /initial-assessment | Kezdeti sportági és erőfelmérés | Edzéstervezés almenü | Jártasság, sportági szerepek és ismert referenciák. |
| /strength-assessment | Vezetett kezdő erőfelmérés | Edzéstervezés almenü | Elvégzendő próba utasítása, eredménybevitel, előzmények. |
| /training-options/locations | Edzési lehetőségek / Helyszínek | Edzési lehetőségek almenü | Tartós helyszíni lehetőségek és felszerelés. |
| /training-options/schedule | Edzési lehetőségek / Általános órarend | Edzési lehetőségek almenü | A szokásos hét. Az aktuális hét a tervezésben nyílik meg. |
| /planning-cycles | Edzésterv és ciklusok | Edzéstervezés almenü | Felkészülés, szerkezet, verseny, konkrét tervjavaslat. |
| /planning-goals | Célok és mérések | Fejlődési célok almenüpont | Szerepek, mérési protokollok, eredmények és értékelések. |
| /coach | Coach / Edzéslista | Bal alsó Edzéslista | Külön lista a mai, közelgő és teljesített edzésekhez. |
| /workouts/[id] | Tervezett edzés | Tervkártya / Edzéslista | Blokkok, előírt cél és kapcsolódó tényleges edzés. |
| /sessions/[id] | Teljesített edzés | Naptár / Edzéslista | Mért adatok, grafikon, szakaszok és visszajelzés. |
| /training-periods/[id] | Edzésidőszak | Naptár, Felkészülés | Régebbi időszaki összesítő nézet. |
| /personal-response | Személyes válaszadatok | Személyes adatok almenü | Bekötött visszajelzések olvasása. |
| /settings | Személyes beállítások | Főmenü | Téma és a kapcsolódó funkciók ismertetése. |
| /nutrition | Táplálkozás | Főmenü | Előkészített, még nincs étrendtervezés. |
| /shopping | Bevásárlás | Főmenü | Előkészített, még nincs listakészítés. |

## Funkciók

Állapotok: **Működik** = használható a leírt körben; **Részleges** = konkrét megvalósítás van, szűkebb támogatással; **Előkészített** = tájékoztató vagy jövőbeli hely, működő folyamat nélkül.

### Közös vezérlők

| ID | Funkció és jelenlegi elérés | Működés és mentés | Előfeltétel és következő lépés |
|---|---|---|---|
| A01 | **Főmenü és almenük** (Működik). Bal oldali menü · `/` | Főoldalak, az aktív főcsoport almenüje, külön Edzéslista és összecsukható menü. Navigáció. A menü összecsukása a megnyitott felület állapota. | Nincs kitöltési előfeltétel. Következő: A választott funkció megnyitása. |
| A02 | **Megjelenési téma** (Működik). Fejléc és Beállítások · `/settings` | Világos, sötét vagy a rendszerhez igazodó téma. Böngészőben megjegyzett választás. | Nincs. Következő: A munka ugyanazon az oldalon folytatható. |
| A03 | **Tárolt adatok újraolvasása** (Működik). Fejléc, Adatkapcsolatok · `/` | A helyben tárolt adatok újraolvasását vagy egy szolgáltatói átvételt lehet a főgombhoz rendelni. A főgomb választását a böngésző megjegyzi. Az újraolvasás önmagában nem új szolgáltatói lekérés. | Betölthető helyi API. Következő: Frissített naptár, profil vagy tervezési nézet. |
| A04 | **Polar-kapcsolat és edzésadatok átvétele** (Működik). Fejléc, Adatkapcsolatok · `/settings#data-connections` | Kapcsolati állapot, csatlakoztatás, választott adatkör és 7/35/89 napos átvétel. Részletes hibák és folytatható lekérések. Szerverre átvett edzések, tervek, párosítási adatok és szinkronfutási eredmények. A profilba emelt megfigyelés külön lépés. | Engedélyezett, működő Polar-kapcsolat. Következő: Naptár / edzésrészletek / profil Előzmények. |

### Sportolói adatok

| ID | Funkció és jelenlegi elérés | Működés és mentés | Előfeltétel és következő lépés |
|---|---|---|---|
| P01 | **Alapadatok és sportmúlt** (Működik). Személyes adatok, Sportolói felmérés, Profil · `/athlete-setup` | Születési dátum, célsport, sportági tapasztalat és korábbi edzésgyakoriság. Verziózott sportolói profil a Felmérés mentése gombbal. | Ismeretlen adat külön megadható. A kezdőtervhez egyes adatok kötelezők. Következő: Helyszínek, időbeosztás és kezdeti felmérés. |
| P02 | **Részvételi keret és korlátozások** (Működik). Sportolói felmérés, Profil · `/athlete-setup` | Állandó/ideiglenes korlátozás, segítségigény, szakembertől kapott keretek, kihagyás és heti összesített edzéskeret. A sportolói profil része. A mentett adatokból tervezési keretértékelés készül. | A saját helyzet megadása. Következő: A hiányzó vagy egyeztetendő adatok rendezése. |
| P03 | **Mért előzmények kijelölése a profilhoz** (Működik). Sportolói felmérés, Előzmények · `/athlete-setup?tab=history` | Tárolt megfigyelések keresése, profilba kijelölése és a kijelölt adatok ellenőrzése. Külön Polar-lekérés is indítható. A kijelölés a profil mentésével végleges. Az átvett nyers adat külön marad. | Mentett vagy lekérhető mért adatok. Következő: Felmérés és kiválasztott adatok mentése. |
| P04 | **Kézi mérés és háttéradat** (Működik). Sportolói felmérés, Előzmények · `/athlete-setup?tab=history` | Kézi mért érték, időszaki terhelés, módszer, sportág, körülmények és egy átvett adat korrekciója. A profilban mentett kézi megfigyelés. Nem azonos egy vezetett felmérőalkalom sorozatnaplójával. | Megadott érték, dátum/időszak és jelentés. Következő: Profil mentése vagy célzott felmérés megnyitása. |

### Edzési helyszínek

| ID | Funkció és jelenlegi elérés | Működés és mentés | Előfeltétel és következő lépés |
|---|---|---|---|
| V01 | **Helyszín létrehozása és kezelése** (Működik). Edzési lehetőségek, Helyszínek · `/training-options/locations` | Állandó/ideiglenes helyszín, mozgásformák és kombinálhatóság. Szerkesztés, törlés és visszaállítás. Tartós helyszínadat. Törölt helyszín visszaállítható. | Helyszín neve és lehetőségei. Következő: Eszközök, majd általános órarend. |
| V02 | **Képes felszereléskiválasztás** (Működik). Helyszín szerkesztése, Erősítő felszerelés · `/training-options/locations` | Kereshető, csoportosított, illusztrált pipálós eszközkatalógus. A teljes katalógus 94 eszköztípust tartalmaz. A kiválasztott eszközök az adott helyszín mentett erőforrásai. | Menthető helyszín. Következő: Az ott elvégezhető gyakorlatok áttekintése. |
| V03 | **Gyakorlatok és eszközigényük áttekintése** (Működik). Helyszín szerkesztése és eszközválasztó · `/training-options/locations` | Eszközök alapján összeálló gyakorlatok, tartozékigény és helyi gyakorlatsegédletek. 120 katalóguselem, ebből 115 erőgyakorlat és 5 ergométeres útvonal. Számított helyszíni lehetőség. Másik helyszín felszerelése nem adódik hozzá. | A helyszín eszközei vagy saját gyakorlatmegadása. Következő: Kezdeti gyakorlatválasztás. |
| V04 | **Elvégezhető gyakorlat közvetlen megadása** (Működik). Helyszín szerkesztése, Gyakorlat megadása ezen a helyszínen · `/training-options/locations` | Katalógusból kiválasztott gyakorlat saját helyszíni megerősítése, megjegyzéssel. Megoldás hiányos eszközmegnevezések esetére. A helyszínhez mentett önbevallás. Nem módosítja a gyakorlat ismeretét vagy a mozgás közbeni komfortot. | Konkrét gyakorlat és helyszíni megerősítés. Következő: Kezdeti felmérés / felmérőalkalom. |

### Időbeosztás

| ID | Funkció és jelenlegi elérés | Működés és mentés | Előfeltétel és következő lépés |
|---|---|---|---|
| T01 | **Általános heti órarend** (Működik). Edzési lehetőségek, Általános órarend · `/training-options/schedule` | Hét napos időablakok, érvényesség, használható idő, helyszíni alternatívák és korlátok. Módosításig vagy megadott végdátumig érvényes általános órarend. | Mentett helyszínek. Következő: Az aktuális 7 nap áttekintése. |
| T02 | **Aktuális 7 nap és napi eltérések** (Működik). Edzéstervezés, Az aktuális 7 nap lehetőségei · `/training-planning#week` | Örökölt időablakok áttekintése, egy nap eltérése és a gördülő hét lapozása. Dátumhoz kötött kivétel. Az általános órarend megmarad. | Általános órarend vagy konkrét időablak. Következő: Tervjavaslat készítése. |
| T03 | **Időszaki helyszíni korlátozás** (Működik). Aktuális 7 nap, Helyszíni kivétel · `/training-planning#week` | Egy helyszín időszakos korlátozása a tartós lehetőség átírása nélkül. Időszakos helyszíni kivétel. | Mentett helyszín és érintett időszak. Következő: Az érintett napok / terv újraellenőrzése. |
| T04 | **Korábbi heti megállapodás és részletes időszaki naptár** (Működik). Sportolói felmérés, Mikor érsz rá? · `/athlete-setup?tab=calendar` | Heti elérhetőség és opcionális napi naptár, másolás, teljes mezociklus kijelölése és előnézet. Külön mentett elérhetőségi / naptári adatok. Párhuzamos belépési út az új órarend mellett. | Profil és érvényes dátumok. Következő: Naptár vagy az új általános órarend. |

### Kezdeti felmérés

| ID | Funkció és jelenlegi elérés | Működés és mentés | Előfeltétel és következő lépés |
|---|---|---|---|
| I01 | **Állapot és erőedzés-előzmény** (Működik). Edzéstervezés, Kezdeti felmérés, 1–2. lépés · `/initial-assessment` | Állapotváltozás, korlátozások, erőedzésmúlt, gyakoriság, utolsó alkalom és segítségigény. Részlegesen is menthető, verziózott kezdeti felmérés. | A sportolói profil aktuális forrásként kapcsolódik. Következő: Sportágak, cél és helyszín. |
| I02 | **Fő- és kiegészítő sportágak** (Működik). Kezdeti felmérés, 3. lépés · `/initial-assessment` | Felkészülés, cél, helyszín, sportági szerep és szakág. 14 sportági bejegyzés, köztük kerékpározás és Egyéb sportág. A kezdeti felmérés része. A sportági profil nem jelent minden sporthoz kész edzésterv-generátort. | Sportágak és szerepük megadása. Következő: Gyakorlatok és saját sportági referenciák. |
| I03 | **Gyakorlatválasztás és jártasság** (Működik). Kezdeti felmérés, 4. lépés · `/initial-assessment` | Húzás, nyomás, térddomináns, csípődomináns és törzs területe. Ismert gyakorlat, komfort és helyszín megadása. Mentett gyakorlat, jártasság és saját megjegyzés. Ez a lépés még nem ír elő edzésadagot. | Az adott helyszíni lehetőség és saját tapasztalat. Következő: Ismert eredmény rögzítése vagy vezetett felmérés. |
| I04 | **Sportági és helyszíni gyakorlat-ajánlás** (Működik). Kezdeti felmérés és felmérőalkalom előkészítése · `/initial-assessment` | A fő- és kiegészítő sportág, jártasság, komfort, eszközök és friss referencia alapján sorrendet és ajánlott gyakorlatot ad. Megjelenített ajánlás. A felhasználó választ; a többi elérhető gyakorlat megmarad. | Mentett sportági szerepek és ismert gyakorlatok. Következő: A kiválasztott gyakorlat felmérése. |
| I05 | **Korábbi eredmények és referenciák** (Működik). Kezdeti felmérés, 5. lépés · `/initial-assessment` | Dátumozott erősítő sorozatok, terhelés, ismétlés/tartás, tartalék, oldal és kivitelezés. Külön sportági táv/idő/teljesítmény referenciák. A kezdeti felméréshez mentett saját teljesítések. | A ténylegesen ismert adat. A hiányzó referencia üres maradhat. Következő: Összegzés vagy új felmérőalkalom. |
| I06 | **Áttekintés, mentés és források egyeztetése** (Működik). Kezdeti felmérés, 6. lépés és alsó gombok · `/initial-assessment` | Hiányok és referenciaállapot, átnézés, tartós mentés, szerverfrissítés, mentett változat és friss profil/helyszín átvétele. Átnézett válaszok és pontos forráshivatkozás. Helyi piszkozat és szerverre mentett felmérés külön állapot. | A kötelező kitöltési/áttekintési lépések teljesülése. Következő: Vezetett felmérőalkalom vagy tervezés. |

### Vezetett erőfelmérés

| ID | Funkció és jelenlegi elérés | Működés és mentés | Előfeltétel és következő lépés |
|---|---|---|---|
| G01 | **Alkalom előkészítése és indítási feltételek** (Működik). Edzéstervezés, Kezdő erőfelmérő alkalom · `/strength-assessment` | Helyszín, 1–5 különböző mozgásminta, naplózási mód és saját megerősítés. Konkrét hiányok és beágyazott kezdeti válaszszerkesztő. Az indítás rögzített gyakorlatokat és utasításváltozatot ment. Eredmény még nem keletkezik. | Aktuális, átnézett kezdeti felmérés; ismert, panaszmentes, helyszínen elvégezhető gyakorlat. Következő: Bemelegítés, majd az első próba. |
| G02 | **Gyakorlatonkénti végrehajtási utasítás** (Működik). Előkészítésben lenyitható kártyák, majd az aktív gyakorlat · `/strength-assessment` | Hétpontos felmérési utasítás 115 erőgyakorlathoz. A saját testsúlyos cél ismétlésreferencia, a kitartás időalapú. Nem technikai betanítás. Az alkalom indulásakor az alkalmazott utasítás tartósan rögzül. | Kiválasztott, ismert gyakorlat. Következő: Tényleges próba és eredménybevitel. |
| G03 | **Elvégzett próba közvetlen rögzítése** (Működik). Bemelegítés után, az aktív gyakorlat alatt · `/strength-assessment` | Tényleges ismétlés/idő/táv, terhelés vagy saját testsúly, oldal, tartalék, kivitelezés, panasz és befejezési ok. Eltérő próba is megőrizhető. Próbánként szerverre menthető adat. A beírt, még meg nem erősített mező piszkozat. | Elvégzett próba. Az óra ismétlésszámlálása nem szükséges. Következő: Következő próba / következő gyakorlat / áttekintés. |
| G04 | **Pihenő és új próba** (Működik). Aktív gyakorlat, eredménybevitel alatt · `/strength-assessment` | Pihenőmérés, eltelt idő kézi átvétele és új eredménysor. A javasolt pihenő nem lesz automatikusan mért adat. A tényleges pihenő és a külön próbák az alkalom eredményeihez tartoznak. | A gyakorlat kártyája szerinti új próba. Következő: Következő gyakorlat vagy áttekintés. |
| G05 | **Ismételt sorozatok megfigyelése** (Működik). Előkészítés, mérési mód választása · `/strength-assessment` | Két rövid sorozat azonos feladattal és megállási szabállyal, tényleges pihenővel. Saját testsúlynál azonos változatot használ. Külön ismételhetőségi eredmények. Ebből még nincs teljes erőállóképességi besorolás vagy optimális sorozatszám. | Dinamikus gyakorlat és megfelelő saját kiinduló referencia. Következő: Eredmények mentése és későbbi összehasonlítása. |
| G06 | **Alkalom lezárása és edzésnapló** (Működik). Az alkalom áttekintése · `/strength-assessment` | Kézi teljes edzés létrehozása tényleges kezdéssel/véggel, vagy saját már rögzített edzés hozzárendelése. Az alkalom és a saját referenciák tartós mentése; kézi módban egy edzésnapló-bejegyzés. Meglévő edzésnél nincs új másolat. | Mentett próbák és ellenőrzött naplózás. Következő: Tervezési felület, újraértékelés. |
| G07 | **Folytatás, előzmény és függő mentés** (Működik). Felmérőfelület, szerverfrissítés és Korábbi felmérési eredmények · `/strength-assessment` | Aktív alkalom folytatása, eredmények újraolvasása, régi alkalom megnyitása és bizonytalan mentés azonos kéréssel ismétlése. Szerveroldali felméréstörténet. A helyi piszkozat és függő kérés elkülönül. | Saját mentett vagy folyamatban lévő alkalom. Következő: Folytatás / lezárás / korábbi eredmény áttekintése. |

### Felkészülés és ciklusok

| ID | Funkció és jelenlegi elérés | Működés és mentés | Előfeltétel és következő lépés |
|---|---|---|---|
| C01 | **Felkészülés létrehozása** (Működik). Edzéstervezés, Edzésterv és ciklusok · `/planning-cycles` | Olimpiai, szezon-, verseny- vagy szabadidős cél, időtáv, célsport és strukturált céladatok. Előnézet után tartósan mentett felkészülés és teljes ciklusszerkezet. | Érvényes időtáv és a választott célhoz szükséges adatok. Következő: Versenyek és ciklushatárok áttekintése. |
| C02 | **Versenyek és versenyprofil** (Működik). Ciklusok, versenyadatok és pontosítás · `/planning-cycles` | Fő- és másodlagos versenyek, pontos/hozzávetőleges dátumok, táv és sportági profil. Verziózott versenypontosítások. | Mentett vagy szerkesztett felkészülés. Következő: Cél- és határpontosítás. |
| C03 | **Makro- és mezociklusok szerkesztése** (Működik). Ciklusok, szerkezet és határok · `/planning-cycles` | Ciklusfelosztás, szomszédos határok egyeztetése, rövidebb maradék időszakok, makrociklusbontás és szabadidős folytatás. Ellenőrzött, verziózott szerkezet és határmódosítás. | Felkészülés és érvényes, folyamatos dátumok. Következő: Fejlesztési stratégia / tervjavaslat. |
| C04 | **Mentett felkészülés és ciklusáttekintés** (Működik). Ciklusok, mentett felkészülés kiválasztása · `/planning-cycles` | Mentett struktúra, versenyek, sportolói keretek és célokra mutató hivatkozások. Megjelenítés a mentett felkészülésből. | Mentett felkészülés. Következő: Képességcélok / aktuális és következő mezociklus terve. |
| C05 | **Vezetett tervezési lépések** (Működik). Edzéstervezés, Tervezés lépései · `/training-planning` | Kilenc beágyazott lépés a céltól a profilon és lehetőségeken át a stratégiáig és tervig. A beágyazott funkciók saját mentései. A kiválasztott felkészülés böngészőlapi navigációs választás. | Az adott lépés előfeltételei. Következő: A még szükséges lépés vagy terv elkészítése. |

### Célok és mérések

| ID | Funkció és jelenlegi elérés | Működés és mentés | Előfeltétel és következő lépés |
|---|---|---|---|
| D01 | **Képességek fejlesztési szerepe** (Működik). Fejlődési célok, Makrocikluscélok · `/planning-goals` | Fő/másodlagos fejlesztés, szinten tartás és megengedett átmeneti visszaesés. Külön kérhető céljavaslat. Verziózott makrocikluscélok és mezociklusonkénti szerepek. | Mentett ciklus és kifejezett szerepválasztás. Következő: Mérési protokoll vagy tervjavaslat. |
| D02 | **Ciklushoz tartozó mérési protokoll** (Működik). Fejlődési célok, Mérési protokollok · `/planning-goals` | Mérendő képesség, mutató, egység, körülmény, mérési ablak és értékelési kritérium. Előre rögzített, verziózott mérési protokoll. | Makrocikluscél és kijelölt mezociklus. Következő: A mérés eredményének rögzítése. |
| D03 | **Protokoll szerinti mérési eredmény** (Működik). Fejlődési célok, Mérési eredmények · `/planning-goals` | Konkrét mérés értéke, időpontja, körülményei és forrása. A kijelölt protokollhoz kapcsolt tartós eredmény. | Mentett mérési protokoll. Következő: Célértékelés. |
| D04 | **Célértékelés és mérési előzmény** (Működik). Fejlődési célok, Célértékelések · `/planning-goals` | Kezdő- és végmérés összevetése a rögzített kritérium szerint, bizonytalanság és hiányok megjelenítésével. Mentett célértékelés és visszaolvasható korábbi verziók. | Összevethető, protokollhoz rendelt mérések. Következő: Stratégia és következő felülvizsgálat. |

### Konkrét edzéstervezés

| ID | Funkció és jelenlegi elérés | Működés és mentés | Előfeltétel és következő lépés |
|---|---|---|---|
| L01 | **Tervjavaslat és újraértékelés** (Részleges). Edzéstervezés, tervlépés; Ciklusok, Edzésterv és újraértékelés · `/training-planning#plan` | A mentett szerepek, profil, időablakok és referenciák alapján jelölteket, változtatásokat és elmaradó célokat mutat. Mentett felülvizsgálat. A javaslat önmagában nem írja át az edzésnaptárt. | Mentett felkészülés, célok és használható lehetőségek. Következő: Napok és alternatívák átnézése, elfogadás. |
| L02 | **Mezociklusok összehangolása** (Működik). Tervjavaslat, Ciklusok összehangolása · `/planning-cycles` | Az aktuális és következő mentett mezociklus heti szakaszait, idő- és alkalomkereteit összehangolja. Külön áttekinthető koordinált javaslat. Az időkeret felső határ. | Mentett ciklushatárok és tervezési források. Következő: Javaslat felülvizsgálata és elfogadása. |
| L03 | **Mentett erőfelmérés használata a kezdőtervben** (Működik). Tervjavaslat, erőfelmérési összefoglaló · `/training-planning#plan` | A használható saját referenciákból ismert gyakorlatot és visszafogott kezdőadagot képez. A C20.7 mért próbáiból a céladag külön származtatott adat. A felmérés bizonyítéka és a terv jelöltje külön marad. Automatikus 1RM- vagy sorozatkapacitás-becslés nincs. | Aktuális, áttekintett felmérés, megfelelő sportági szerepek és legalább két használható külön mozgásminta. Következő: Tervjavaslat átnézése és elfogadása. |
| L04 | **Napi edzésváltozat kiválasztása** (Működik). Tervjavaslat, kattintható napok és alternatívák · `/training-planning#plan` | A gördülő hét egy napján konkrét alternatíva választása. A későbbi javaslat együtt frissül, a választás visszaállítható. Rögzített tervválasztás, újraértékelt javaslat. | Elérhető napi alternatívák. Következő: Módosult napok áttekintése és elfogadás. |
| L05 | **Változtatások elfogadása és teljesítések rendezése** (Működik). Tervjavaslat alja, átnézési megerősítés · `/training-planning#plan` | Új/elhagyandó tervek áttekintése, elfogadása; teljesített, tisztázandó és kihagyott edzések megkülönböztetése. Kifejezetten elfogadott naptári változások és mentési bizonylat. A kihagyott terhelést nem pótolja automatikusan. | Átnézett, még aktuális javaslat. Következő: Naptár és az edzés végrehajtása. |

### Naptár

| ID | Funkció és jelenlegi elérés | Működés és mentés | Előfeltétel és következő lépés |
|---|---|---|---|
| N01 | **Napirend és többhetes áttekintés** (Működik). Naptár · `/` | 1 nap, 7 nap, 4 hét és hosszú áttekintés. Tervezett, teljesített, szabad és foglalt időszakok; terv és kapcsolt teljesítés közös megjelenítése. A nézet mentett forrásadatokat jelenít meg. | Tárolt naptári / edzésadatok. Következő: Esemény megnyitása vagy időablak szerkesztése. |
| N02 | **Szabad és foglalt idősáv kezelése** (Működik). Naptár, idősáv szerkesztése / új idősáv · `/` | Egyszeri és heti ismétlődés, dátum, idő, rendelkezésre állás és napi/ablakonkénti korlát. Előnézet után mentett naptári szabály vagy kivétel. | Érvényes helyi időpont és a módosítás hatóköre. Következő: Használható időablakok és terv ellenőrzése. |
| N03 | **Idősáv húzása, méretezése és visszavonása** (Működik). Naptár időrácsa, valódi időablak · `/` | Idősáv mozgatása, ötperces módosítás és szélek külön méretezése. Utolsó támogatott módosítás visszavonása. Átnézett, mentett új szabály/kivétel; visszavonás is külön mentés. | Szerkeszthető időablak. Mért edzés nem ilyen idősáv. Következő: Új elérhetőség áttekintése. |
| N04 | **Tervezett edzés áthelyezése** (Működik). Naptár, mozgatható tervkártya · `/` | A támogatott tervezett edzés napjának/kezdésének módosítása és az ütközések előnézete. Jóváhagyott új időpont. Az előírt edzésadag nem változik a húzástól. | Áthelyezhető terv, ismert időtartam és megengedett célidő. Következő: Áthelyezés elfogadása / visszaállítása. |
| N05 | **Egy edzés fő képességcélja** (Működik). Naptár, edzés fő céljának szerkesztése · `/` | Kifejezett képességcél rögzítése és a cél szerinti megjelenítés. A konkrét eseményhez mentett célmegjelölés. | Kiválasztott támogatható edzés. Következő: Edzés részletei vagy tervezés. |
| N06 | **Időtartam, ütközés és állapotadatok** (Működik). Naptár esemény és részletek · `/` | Mért, előírt és becsült idő elkülönítése, becslési források, átfedések, napi állapot és hiányok. Számított megjelenítés, a forrásértékek átírása nélkül. | Az adott eseményhez rendelkezésre álló adatok. Következő: Pontosítás vagy edzésrészletek. |

### Edzésnapló és elemzés

| ID | Funkció és jelenlegi elérés | Működés és mentés | Előfeltétel és következő lépés |
|---|---|---|---|
| E01 | **Edzéslista és tervrészletek** (Működik). Bal alsó Edzéslista; naptári tervkártya · `/coach` | Mai, közelgő és teljesített edzések listája; a terv oldala a blokkokat és kapcsolt teljesítést mutatja. Mentett tervek és edzések megjelenítése. | Tárolt tervek / edzések. Következő: Terv vagy tényleges edzés részletei. |
| E02 | **Mért edzés összesítése és grafikonok** (Működik). Teljesített edzés megnyitása · `/sessions/[id]` | Mért mutatók, grafikon, idő/táv tengely, nagyítás, csatorna és sebességegység választása. A mért adatok megjelenítése; grafikonbeállítás a böngészőben. | Saját tárolt edzés; részletes grafikonhoz mért minták. Következő: Szakaszok, visszajelzés vagy terv összevetése. |
| E03 | **Térkép, körök és szakasztáblák** (Működik). Mért edzés részletei · `/sessions/[id]` | GPS-útvonal, kurzorhoz kötött hely, szolgáltatói körök/szakaszok, pulzus-, sebesség- és teljesítményadatok. Forrásadatok olvasása; az adathiány látható marad. | Az edzésben ténylegesen tárolt útvonal- és köradatok. Következő: Tervhez vagy szakaszhoz tartozó elemzés. |
| E04 | **Tervhatárok és szakaszonkénti értékelés** (Működik). Mért edzés, Szakaszhatárok és Szakaszonkénti értékelés · `/sessions/[id]` | Idő-/távhatárok, kézi következő kezdés, várakozási javaslatok, szakaszátlagok és célzónában töltött idő. A kézi grafikonjelölések és kezdésreferenciák jelenleg böngészőlapon tároltak, nem központi szerveres felmérési eredmények. | Terv vagy kifejezett kézi jelölés és használható mintasor. Következő: Szakasz vagy grafikon további vizsgálata. |
| E05 | **Edzés utáni és másnap reggeli visszajelzés** (Működik). Mért edzés, Saját visszajelzés · `/sessions/[id]` | Nehézség/RPE, fáradtság, izomláz, regeneráltság és energiaszint 0–10 skálán, megfigyelési idővel és megjegyzéssel. Verziózott szerveroldali válaszok és helyi piszkozat. Az üres válasz nem nulla. | Saját teljesített edzés. Következő: Tanulási kapcsolat ellenőrzése. |
| E06 | **Terv–teljesítés bizonyíték és tanulási kapcsolat** (Működik). Mért edzés, Tanulási kapcsolat · `/sessions/[id]` | Tervkapcsolat és végrehajtási bizonyíték áttekintése/megerősítése, saját válasz megfelelő változatának kiválasztása. Rögzített kapcsolat és elemzéshez kiválasztott megfigyelés. Nem állít be tanult személyes terhelési modellt. | Saját tervkapcsolat és szükség szerint visszajelzés. Következő: Személyes válaszadatok. |
| E07 | **Időszaki terv–teljesítés összesítés** (Működik). Naptár Felkészülés részéből · `/training-periods/[id]` | Heti tervezett/tényleges mennyiség, teljesítési állapot és terhelési összesítők a régebbi időszaknézetben. Tárolt időszak és hozzá kapcsolódó adatok olvasása. | Meglévő edzésidőszak. Következő: Kapcsolódó edzés vagy képességcél megnyitása. |

### Saját válaszadatok

| ID | Funkció és jelenlegi elérés | Működés és mentés | Előfeltétel és következő lépés |
|---|---|---|---|
| R01 | **Visszajelzések időbeli áttekintése** (Működik). Személyes adatok, Személyes válaszadatok · `/personal-response` | Időszak, sportági/időzítési kontextus, idősor, pontdiagram és adatlista. Ismert/hiányzó válaszok elkülönítése. Olvasási nézet a már bekötött válaszokból; nincs önálló adatbevitel. | Bekötött, saját visszajelzések. Üres állapotból edzésre irányít. Következő: Teljesített edzés megnyitása és visszajelzés. |

### Előkészített részek

| ID | Funkció és jelenlegi elérés | Működés és mentés | Előfeltétel és következő lépés |
|---|---|---|---|
| S01 | **Táplálkozás** (Előkészített). Táplálkozás · `/nutrition` | Tájékoztató oldal a tervezett táplálkozási modulról. Étrendtervező és tényleges adatbevitel nincs ezen a felületen. | Későbbi megvalósítás. Következő: Nincs működő táplálkozási folyamat. |
| S02 | **Bevásárlás** (Előkészített). Bevásárlás · `/shopping` | Tájékoztató a későbbi étrendhez kapcsolódó bevásárlólistáról. Bevásárlólista-generálás nincs ezen a felületen. | Későbbi megvalósítás. Következő: Beállításokra mutató hivatkozás. |
| S03 | **További szolgáltatók és külső naptárak** (Előkészített). Beállítások és Adatkapcsolatok · `/settings` | Garmin, Suunto, Google Calendar, Microsoft 365, iCloud; további táplálkozási és bolti beállítások előkészített helyei. Ezekhez még nincs bekötött működő kapcsolat ezen a felületen. | Későbbi integráció. Következő: Jelenleg a Polar és a helyi naptár használható. |

## Felhasználói folyamatok

### Erőfelmérés

| Lépés | Feladat | Kapcsolódó funkció | Ellenőrizendő eredmény | Következő hely |
|---|---|---|---|---|
| 1 | Profil és helyszín | P01–P02, V01–V04 | Mentett, aktuális sportolói keret és az adott helyszínen végezhető gyakorlat. | Kezdeti felmérés |
| 2 | Jártasság és ismert referenciák | I01–I06 | A releváns válaszok átnézése és mentése. A 6/6 kitöltött lépés önmagában nem mért erőeredmény. | Kezdő erőfelmérő alkalom |
| 3 | Alkalom előkészítése | G01–G02 | A helyszín és ismert gyakorlatok kijelölése; jelzett előfeltételek rendezése, majd indítás. | Bemelegítés |
| 4 | Bemelegítés és tényleges próba | G02–G04 | Bemelegítés visszajelzése után az utasítás és az eredménymezők ugyanazon a gyakorlaton látszanak. | Próba rögzítése és mentése |
| 5 | További eredmények és lezárás | G03–G07 | Következő gyakorlat, áttekintés, kézi időpontok vagy a saját már rögzített edzés kiválasztása. | Alkalom lezárása |
| 6 | Referencia felhasználása | L01, L03, L05 | A lezárt eredmény után új tervjavaslatot kell kérni és a változtatásokat elfogadni. | Naptár |

### Tervezés

| Lépés | Feladat | Kapcsolódó funkció | Ellenőrizendő eredmény | Következő hely |
|---|---|---|---|---|
| 1 | Cél és tervezési időtáv | C01–C04 | Felkészülés, versenyek és ciklushatárok. | Sportolói adatok és lehetőségek |
| 2 | Profil és előzmények | P01–P04 | Aktuális keretek és a rendelkezésre álló saját adatok. | Helyszínek és kezdeti felmérés |
| 3 | Helyszínek és felmérés | V01–V04, I01–I06 | Tartós lehetőségek, gyakorlatok, sportági szerepek és saját referenciák. | Általános órarend |
| 4 | Időbeosztás | T01–T03 | Szokásos hét és a konkrét következő 7 nap eltérései. | Fejlesztési stratégia |
| 5 | Stratégia és tervjavaslat | D01, L01–L04 | Mentett képességszerepek, összehangolt ciklusok, napok és alternatívák átnézése. | Változtatások elfogadása |
| 6 | Elfogadás és naptár | L05, N01 | Az elfogadott terv kerül a naptárba. Az újraértékelés később is külön jóváhagyható. | Edzés végrehajtása |

### Edzés utáni követés

| Lépés | Feladat | Kapcsolódó funkció | Ellenőrizendő eredmény | Következő hely |
|---|---|---|---|---|
| 1 | Edzésadatok átvétele | A04, E01–E03 | Saját edzés megnyitása a naptárból vagy listából. | Saját visszajelzés |
| 2 | Visszajelzés | E05 | Edzés utáni vagy másnap reggeli megfigyelés mentése. | Tanulási kapcsolat |
| 3 | Kapcsolat ellenőrzése | E06 | Szükség esetén terv–teljesítés bizonyíték áttekintése és rögzítése. | Személyes válaszadatok |
| 4 | Áttekintés és új terv | R01, L01 | Bekötött adatok olvasása; ettől még nincs automatikus személyes dózismodell. | Újraértékelés |

### Célmérés

| Lépés | Feladat | Kapcsolódó funkció | Ellenőrizendő eredmény | Következő hely |
|---|---|---|---|---|
| 1 | Képességszerep | D01 | Kijelölt ciklus és mentett képességcél. | Mérési protokoll |
| 2 | Előre rögzített mérés | D02 | Mutató, körülmények, időablak és értékelési szabály. | Mérési eredmények |
| 3 | Tényleges eredmény | D03 | Konkrét időpont és mért érték. | Célértékelés |
| 4 | Változás értékelése | D04 | A megőrzött protokoll és összevethető eredmények alapján. | Következő tervezési felülvizsgálat |

## Rendszerezendő pontok

Az észlelt jelenlegi helyzet külön oszlopban szerepel a később eldöntendő felületi kérdéstől. Ezek még nem elfogadott új menücsoportok.

| ID | Érintett funkciók | Jelenlegi helyzet | Következmény | Eldöntendő kérdés |
|---|---|---|---|---|
| U01 | A01 | Almenük csak az aktív főcsoport alatt láthatók. | Másik főcsoportból a következő funkció nem látható közvetlenül. | Állandó folyamatbelépő vagy következő lépés helyének eldöntése. |
| U02 | P01, I01, G01, D02 | Több külön felület nevében szerepel felmérés vagy mérés. | A háttéradat, a jártasság, a tényleges próba és a ciklusmérés könnyen összekeverhető. | Egyértelmű felhasználói megnevezések és kapcsolódó belépők. |
| U03 | I06, G01 | Forrásegyeztetés, átnézés és helyi szerkesztés külön állapot. | Egy kitöltöttnek látszó lap mellett az indítás még feltételhez kötött lehet. | A konkrét teendő és az indítás állapotának közös megjelenítése. |
| U04 | T01–T04, N02 | Általános órarend, régebbi heti megállapodás, napi naptár és kivétel is elérhető. | Nehezen látszik, melyik változtatja a szokásos hetet és melyik csak egy napot. | Egy közös időbeosztási belépő és látható hatókör. |
| U05 | C05, L01 | A tervezési folyamat és a Ciklusok oldal részben ugyanazokat az elemeket ágyazza be. | A ciklusszerkezet és a következő konkrét edzés terve összemosódik. | Szerkezet és napi terv munkafeladatának elhelyezése. |
| U06 | P03–P04, I05, G03, D03 | Eredmény több helyen rögzíthető, eltérő céllal és adattal. | Nem magától értetődő, hogy egy most elvégzett sorozat adata a vezetett alkalomhoz tartozik. | Egységes eredménybelépő és visszahivatkozás a mérés céljára. |
| U07 | A03–A04, I06, G07 | Frissítés lehet helyi újraolvasás, Polar-átvétel vagy új források átvétele. | Az azonosnak ható frissítés gombok eltérő műveletet jelentenek. | Műveletet megnevező címkék és következmények. |
| U08 | E01, N01 | A naptár mellett külön Edzéslista oldal van, Coach címmel. | Ugyanaz az edzés több eltérő nevű belépőn kereshető. | Közös naplóbelépő vagy név és szerep tisztázása. |
| U09 | S01–S03 | Előkészített modulok teljes értékű főmenüpontként jelennek meg. | A menü mérete nagyobb a ténylegesen használható funkciókénál. | Előkészített funkciók láthatósága és jelölése. |
| U10 | E04, G03, G07 | Böngészőlapi jelölés és szerverre mentett mérés egyaránt létezik. | A felhasználó nem feltétlenül tudja, melyik adat érhető el másik eszközön. | Mentési helyzet és tartósság érthető megjelenítése. |
| U11 | I02, L01 | 14 sportági profilhoz jelenleg jóval szűkebb automatikus mintatervezés tartozik. | A sportág kiválaszthatósága teljes sportági edzéstervezést ígérhet. | Profilkezelés és tényleges tervtámogatás külön jelölése. |

## Technikai visszakeresés

A hivatkozások a projekt gyökeréhez viszonyított forrásfájlok. A leltár a webfelületet fedi le; a csak háttér-API-n elérhető kísérleti és diagnosztikai végpontokat nem sorolja sportolói menüfunkcióként.

| Funkció | Forrásfájl |
|---|---|
| A01 | `apps/web/src/components/ui/app-shell.tsx` |
| A02 | `apps/web/src/components/ui/theme-control.tsx` |
| A03 | `apps/web/src/components/ui/data-connections-control.tsx` |
| A04 | `apps/web/src/components/ui/data-connections-control.tsx` |
| P01 | `apps/web/src/components/athlete-setup/profile-form.tsx` |
| P02 | `apps/web/src/components/athlete-setup/profile-form.tsx` |
| P03 | `apps/web/src/components/athlete-setup/history-form.tsx` |
| P04 | `apps/web/src/components/athlete-setup/history-form.tsx` |
| V01 | `apps/web/src/components/training-options/location-editor.tsx` |
| V02 | `apps/web/src/components/training-options/strength-equipment.tsx` |
| V03 | `apps/web/src/lib/training-options/strength-catalog.ts` |
| V04 | `apps/web/src/components/training-options/exercise-confirmations.tsx` |
| T01 | `apps/web/src/components/training-options/schedule-editor.tsx` |
| T02 | `apps/web/src/components/training-options/current-week.tsx` |
| T03 | `apps/web/src/components/training-options/current-week.tsx` |
| T04 | `apps/web/src/components/athlete-setup/workspace.tsx` |
| I01 | `apps/web/src/components/initial-assessment/editor.tsx` |
| I02 | `apps/web/src/components/initial-assessment/editor.tsx` |
| I03 | `apps/web/src/components/initial-assessment/editor.tsx` |
| I04 | `apps/web/src/lib/guided-strength/recommendations.ts` |
| I05 | `apps/web/src/components/initial-assessment/editor.tsx` |
| I06 | `apps/web/src/components/initial-assessment/workspace.tsx` |
| G01 | `apps/web/src/components/guided-strength/preparation.tsx` |
| G02 | `apps/web/src/components/guided-strength/calibration-movement.tsx` |
| G03 | `apps/web/src/components/guided-strength/calibration-movement.tsx` |
| G04 | `apps/web/src/components/guided-strength/calibration-movement.tsx` |
| G05 | `apps/web/src/components/guided-strength/preparation.tsx` |
| G06 | `apps/web/src/components/guided-strength/workspace.tsx` |
| G07 | `apps/web/src/components/guided-strength/workspace.tsx` |
| C01 | `apps/web/src/components/planning-cycles/workspace.tsx` |
| C02 | `apps/web/src/components/planning-cycles/competition-editor.tsx` |
| C03 | `apps/web/src/components/planning-cycles/workspace.tsx` |
| C04 | `apps/web/src/components/planning-cycles/program-details.tsx` |
| C05 | `apps/web/src/components/training-planning/journey.tsx` |
| D01 | `apps/web/src/components/planning-goals/macro-form.tsx` |
| D02 | `apps/web/src/components/planning-goals/protocol-form.tsx` |
| D03 | `apps/web/src/components/planning-goals/measurement-form.tsx` |
| D04 | `apps/web/src/components/planning-goals/workspace.tsx` |
| L01 | `apps/web/src/components/planning-cycles/training-plan.tsx` |
| L02 | `apps/web/src/components/planning-cycles/mesocycle-summary.tsx` |
| L03 | `apps/api/app/services/training_strength_assessment.py` |
| L04 | `apps/web/src/components/planning-cycles/plan-output.tsx` |
| L05 | `apps/web/src/components/planning-cycles/training-plan.tsx` |
| N01 | `apps/web/src/components/calendar/workspace.tsx` |
| N02 | `apps/web/src/components/calendar/quick-editor.tsx` |
| N03 | `apps/web/src/components/calendar/editable-slot.tsx` |
| N04 | `apps/web/src/components/calendar/move-editor.tsx` |
| N05 | `apps/web/src/components/calendar/workspace.tsx` |
| N06 | `apps/web/src/components/calendar/duration-details.tsx` |
| E01 | `apps/web/src/app/coach/page.tsx` |
| E02 | `apps/web/src/components/session-analysis/explorer.tsx` |
| E03 | `apps/web/src/components/session-analysis/sections.tsx` |
| E04 | `apps/web/src/components/session-analysis/plan-boundaries.tsx` |
| E05 | `apps/web/src/components/session-analysis/feedback.tsx` |
| E06 | `apps/web/src/components/session-analysis/learning-status.tsx` |
| E07 | `apps/web/src/app/training-periods/[id]/page.tsx` |
| R01 | `apps/web/src/components/personal-response/workspace.tsx` |
| S01 | `apps/web/src/app/nutrition/page.tsx` |
| S02 | `apps/web/src/app/shopping/page.tsx` |
| S03 | `apps/web/src/app/settings/page.tsx` |
