# C20.2 — Aktuális és következő mezociklus összehangolása

A C20.1 személyes kezdőkeretére épülő napi tervező már a mentett mezociklusokhoz igazított heti felépítést is készít. A helyszínek, saját referenciák, védett tervek és teljesítések ugyanazok a források maradnak. A képességszerepek a mentett célokból származnak; a ciklushatárokat és a versenydátumokat nem módosítjuk.

## Használat

Az Edzéstervezés utolsó lépésében a **Ciklusok összehangolása** gomb a profil időzónája szerinti mai naptól az aktuális és a következő mentett mezociklus végéig kér új javaslatot. Egyetlen kattintás elindítja az értékelést, és a visszakapott pontos dátumok megjelennek a mezőkben. A régebbi, rövidebb értékelés betöltése nem írja felül a kért tartományt.

A napi naptár fölött látható a két ciklus heti felépítése: mentett fő hangsúlyok, dátumok, rávezető/építő/könnyebb szakasz, felső időkeret, javasolt edzésszám és idő, valamint a külön edzésjavaslattal képviselt célok. A még külön megoldást igénylő fő célok ciklusonként is látszanak. A felső keret a már teljesített és a megőrzött edzésekkel közös; nem kitöltendő kvóta és nem ígéret a fejlődésre.

A gördülő hét, a napi kattintásra teljesen kinyíló alternatívák és a külön naptári elfogadás megmaradnak. Egy másik változat választása a teljes kijelölt időszak javaslatát újraszámolja. A felülvizsgálat és a választás nem alkalmazza automatikusan a naptári változtatásokat.

## Heti felépítés a mentett dátumokból

A mikrociklusok a mezociklus **valódi kezdőnapjától** számított, legfeljebb hét civil napos blokkok. Nem igazítjuk őket hétfőhöz vagy rögzített négyhetes hosszhoz. A maradéknapok külön rövid blokkban megmaradnak; óraátállításkor sem tűnik el vagy duplázódik nap.

Négy teljes hét alapmintája a kezdőkeret 80%, 90%, 100%, majd 70%-a. Például 180 perces alapnál az ötperces lefelé kerekítés után 140, 160, 180 és 125 perc a blokk felső kerete. Ez termékoldali, átlátható kezdőszabály, nem kutatással validált személyes dózisoptimum. A tényleges javaslat ennél kisebb is lehet az előzmény, a helyszín, az időablak, a támogatott minimális edzéshossz vagy a többi edzés miatt.

- Egyetlen rövid blokk egyenletes időkeret marad.
- Két teljes hét építő és könnyebb szakaszt kap.
- Hosszabb ciklusnál a minta ismétlődhet; a legalább négynapos utolsó blokk könnyebb. Közvetlenül előtte nem teszünk még egy teljes könnyebb blokkot pusztán a négyhetes minta ismétlése miatt.
- A rövid maradékblokk időkerete naparányos. A szomszédos napokkal a gördülő hétnapos korlát továbbra is közös.
- Az állóképességi időtartamok a szakasz arányához is igazodnak, a család megengedett minimumán és a saját referencia felső korlátján belül. A minimális támogatott hossz miatt az egyes edzések ideje nem feltétlenül követi pontosan a százalékos mintát.
- Az erőedzés időtartama helyfoglalás. Súlyt, sorozatot, ismétlést, RIR-t vagy intenzitást nem skálázunk a heti százalékkal.

A 36 órás kezdési időköz és az összes gördülő hétnapos ablak ellenőrzése a két mezociklus határán is érvényes. A következő ciklus első napja nem nullázza a terhelési könyvelést. Az ismert tényleges teljesítések, a védett tervek, az időbecslések felső értékei és a saját kihagyott alkalmak kvótavédelme is beleszámítanak. Ismeretlen időtartam nem válik nullává.

## Fontos, ritkán elérhető edzések

A ciklusos mód nem kizárólag időrendben tölti fel a napokat. Az adott blokkban ritkábban elérhető fő képesség lehetőségei előrébb kerülnek, és a különböző, még nem képviselt fő hangsúlyok is elsőbbséget kapnak. Így például a csak vasárnap elérhető erőedzést nem szorítja ki automatikusan egy korábban kényelmesen elhelyezhető futás. A saját választás elsőbbséget kap; minden jelöltnél változatlanul szükséges a sport-, helyszín-, eszköz-, referencia-, idő- és terhelési feltételek teljesülése.

Ez korlátos, determinisztikus kiosztási szabály, nem globális fiziológiai optimalizáló. A nem támogatott képességekhez nem találunk ki edzésmintát. Verseny előtti vagy átvezető szakaszban a korábbi `EVENT_PHASE_REVIEW` felülvizsgálati határ megmarad; ez a kiadás nem köt be új versenycsúcsformát vagy intenzív intervallumcsaládot.

## Rögzített ciklusalap

A könnyebb hét rövidebb edzéseiből nem szabad minden következő ellenőrzéskor újabb, még kisebb kezdőkeretet levezetni. A ciklusos javaslat ezért a kiinduló, változtathatatlan felülvizsgálat saját időtartam-referenciáit és heti kezdőkeretét használja a későbbi választásoknál és újraértékeléseknél.

Az aktuális teljesítések és állapotjelzések ettől még frissen töltődnek és számítanak a terhelési könyvelésben. A jelenlegi profil alacsonyabb heti korlátja felülírja a rögzített felső keretet. A kiinduló adatok javítása vagy törlése esetén a régi alap nem használható tovább: a felület friss ciklusalapot kér. A **Ciklusok összehangolása** gomb mindig kérhet új kiindulópontot a friss forrásokból.

A bizonyíték a teljes eredeti, tulajdonoshoz és programhoz kötött felülvizsgálat. A referencia legfeljebb egy szint mély, nem növekvő hivatkozási lánc. A backend ellenőrzi az eredeti audit meglétét, pontos tartalmát és az alapul vett saját edzések változatlanságát. A böngésző a beágyazott eredeti értékelés tartalomlenyomatát és szerződését is ellenőrzi. A megjelenített forrásedzések és magyarázatok a megfelelő cikluskezdő adatokból származnak.

Azonos döntésű ismételt ellenőrzés önmagában nem gyárt új tervverziót. A háttérfigyelő a később kért, még el nem fogadott hosszabb felülvizsgálatot sem cseréli vissza a régebbi elfogadott rövid ablakra. A kért horizonton túl továbbra sem hosszabbít automatikusan; új edzést csak kifejezett elfogadás hoz létre.

## Szerződések

- Tervezőszabály: `training-plan-policy-v0.6`.
- Összehangolás: `training-mesocycle-coordination-v0.1`, `training-mesocycle-policy-v0.1`.
- A review kérésben opcionális, szigorúan logikai `coordinate_mesocycles` mező szerepelhet. Kifejezett `true` friss ciklusalapot kér. Enélkül a hosszabb új ablak ciklusos, a legfeljebb hétnapos új ablak kompatibilis rövid értékelés; egy meglévő ciklusos folyamat későbbi rövid maradéka megőrzi a módját.
- A mentett felülvizsgálat tartalmazza a módot és az opcionális, egyszintű `calibration_review` forrást. Az elfogadás és a háttérfigyelés megőrzi a módot.
- A böngésző újraszámolja a blokkok dátumait és kereteit, ellenőrzi a kiválasztott edzések blokkhoz rendelését, az állóképességi időtartam-határt, a meglévő terheléssel közös blokk- és gördülő heti korlátokat, valamint az időközt. A régi értékelések továbbra is olvashatók.
- Nincs új végpont, külső szolgáltatás, függőség vagy adatbázis-migráció. A meglévő tulajdonosi határok, pontos kérésismétlés, auditok, eredeti források védelme és tranzakciós elfogadás megmaradnak.

## Ellenőrzés és szakmai határ

`python tools/run_c20_2_checks.py --build`

A teljes tesztkapu 1890 backend- és 950 frontendtesztet futtat, a Next útvonaltípusok, TypeScript, ESLint és kérésre production build mellett. Az új 14 backendteszt valódi HTTP/SQLite tranzakciókkal vizsgálja a dátumokat, közös kereteket, ritka lehetőségeket, stabil ciklusalapot, korrekciót, alacsonyabb profilkorlátot és háttérfigyelést. A 26 új frontendteszt backendből generált mesterséges válaszokkal ellenőrzi az elfogadott és manipulált szerződéseket, forráshatárokat, megjelenítést és a pontos kérést. Külön DOM-interakció igazolja az egykattintásos, pontos kétciklusos kérést és a nyolc heti sor megjelenését elfogadási írás nélkül.

Általános háttér: [García-Pallarés és mtsai., 2010, PMID 20414669](https://pubmed.ncbi.nlm.nih.gov/20414669/) tíz elit kajakosnál vizsgált két periodizációs megközelítést. Ez a szakaszolt felkészülés releváns példája; sem az elit edzésvolumen, sem az eredmények nem másolhatók át a felhasználóra. A fenti százalékok, blokkhosszak, minimumok és kiosztási sorrend saját termékdöntések, nem a tanulmányból származó személyes előírások. A személyes fiziológiai válaszmodell továbbra sincs bekötve.
