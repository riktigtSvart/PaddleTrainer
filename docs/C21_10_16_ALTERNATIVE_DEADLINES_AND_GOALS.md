# C21.10.16 — Változatonkénti lejárat és célilleszkedés

## Az alternatíva nem a javasolt kezdéskor jár le

Minden ellenőrzött változat saját utolsó lehetséges kezdést kap. Ennek alapja a tényleges, összefüggő időablak vége mínusz az adott edzés teljes előírt időtartama, beleértve a bemelegítést, pihenőket és levezetést. Ha például az ablak 10:00-kor zár, a 60 perces változat 09:00-ig, a 20 perces változat 09:40-ig kezdhető el. A korábbi 08:00-s javasolt kezdés elmúlása önmagában nem zárja le egyik lehetőséget sem.

A napfénykorlátot sportáganként és helyszínenként, a meglévő koordináták/terület és biztonsági időráhagyások alapján alkalmazzuk. Egy elfoglaltság által kettévágott időablakot nem egyesítünk. Éjfél után nem kezdünk visszamenőleg az előző napra edzést; a helyi nap határát időzónával és óraátállítással számoljuk. Az időablak miatti utolsó kezdés még megengedett, a következő pillanat már lejárt. A helyi nap vége kizáró határ.

A nyitott listából a lejárt változatok másodperces időellenőrzéssel eltűnnek, a darabszámok és a még elérhető ajánlás követik ezt. A naptár újratöltött számlálója is csak a megmaradt változatokat számolja. A rögzített felülvizsgálati bizonyítékokat nem töröljük: a korábbi javaslat története megmarad. Az idő múlása önmagában nem írja át a naptárban lévő edzést.

## Új kezdés, változatlan edzés

Ha a javasolt kezdés már elmúlt, de az edzés még belefér, a kiválasztás új kezdési idővel készít előnézetet. A 15 perces általános előkészítési idő nem zárhatja ki a manuális aznapi csere utolsó, még használható perceit: ilyenkor a javasolt kezdést az utolsó lehetséges kezdéshez igazítjuk.

A konkrét kiválasztás megőrzi az időtartamot és az edzés teljes fizikai előírását. Egy lejárt 60 perces edzést nem alakítunk észrevétlenül 20 percessé. Az új rövidebb változat külön, friss ellenőrzésben megjelenő lehetőség lehet. Súly, sorozat, ismétlés, tartás, pihenő, előírt tartalék vagy fő cél változásakor új változatot kell áttekinteni.

Ha az előnézet konkrét kezdése közben elmúlt, **Kezdés frissítése** kérhető. A lejárat nem jelent automatikus naptári mentést. A végleges mentés mindig frissen, tulajdonosi zárolás alatt ellenőrzi a teljesítéseket, a többi edzést, az alkalmasságot és a terhelési kereteket. Egy nem kiválasztott változat lejárata önmagában nem akadályozza az egyébként változatlan, még érvényes és frissen újraellenőrzött naptári módosítás elfogadását. Forrásváltozás, megváltozott edzés, dózis vagy módosításlista ezt a kivételt nem használhatja.

A mai edzéshez megmarad az **A mai edzést még nem kezdtem el** megerősítés. Elkezdett/teljesített, kapcsolt, jóváhagyott vagy átírt edzés nem válik cserélhetővé. Ha már nincs megfelelő változat, az eredeti terv megmarad. A friss kézi keresés az adott nap lejárt korábbi választásához sem ragaszkodik.

## Fő cél, alcél, fenntartás

Az alternatívák a meglévő két tartalmi csoporton belül célbesorolást is kapnak:

- **Fő célt fejlesztő edzés** — a mezociklus mentett kiemelt céljához rendelt minta.
- **Alcélt fejlesztő edzés** — mentett másodlagos fejlesztési célt szolgál.
- **Fenntartó edzés** — mentett fenntartási célt szolgál.

A besorolás az adott naphoz/mezociklushoz mentett képességszerepből származik; a sportág neve önmagában nem határozza meg. A felület jelzi, ha a csere megőrzi az eredeti edzés célját, vagy másik célt szolgál. Eltéréskor megmutatja, hány másik javasolt edzés képviseli az eredeti célt a vizsgált terv adott mezociklusában. Ez az előírt célok képviselete; nem felméréssel bizonyított képességjavulás vagy a teljes fejlesztési szükséglet lefedettsége.

Ha az ajánlott változat lejár, a megmaradt listában új ajánlás jelenik meg, a fő-, másodlagos és fenntartási célok sorrendjében, azon belül az eredeti cél megőrzését előnyben részesítve. A friss szerverellenőrzés a teljes időszak céljait, többi edzését és korlátait is újraszámolja. A naptári terv csak az előnézet külön jóváhagyása után változik.

## Az időjárás határa

Automatikus időjárási adatforrás még nincs bekötve. A lejárati adat kifejezetten `weather_evaluated: false`; ebből nem állítjuk, hogy a szél, zivatar vagy vízi körülmények megfelelőek. Az ismert napfény- és naptári időkorlátok működnek, az időjárási ellenőrzés külön későbbi integrációt igényel.

## Szerződés és ellenőrzés

A válasz új, opcionális `training-alternative-availability-v0.1` része jelöltenként tartalmazza az összefüggő ablakot, a teljes időigényt, a helyi nap végét, a lejáratot és annak határszabályát, a határ okát, illetve a mentett cél szerepét. A frontend ezeket a rögzített bemenetekből és a meglévő napfényszámításból újraszámolja. A külső hash újraszámítása önmagában nem tehet érvényessé hamis lejáratot vagy célbesorolást. A régi felülvizsgálatok olvashatók maradnak; ismeretlen lejáratnál friss ellenőrzést kérünk, nem találunk ki határidőt a régi kezdésből.

Az adatbázisséma változatlan; migráció és új felmérés nem szükséges. Mindkét szerverfolyamat frissítése/újraindítása kell. Az új részletes lejárati adatokhoz az **Alternatívák friss ellenőrzése** gombot használd.

A `tools/run_c21_10_16_checks.py` az új lejárati, célbesorolási és az előző aznapi csereteszteket, a releváns frontendkészletet, TypeScriptet, lintet és production buildet futtatja. A teljes készletek `--full-backend`, illetve `--full-frontend` kapcsolóval kérhetők. A valódi API + React StrictMode/JSDOM próba ellenőrzi az időzített listaszűrést, az új ajánlást, a célcímkéket, a változatlan dózisú új időpontot és a külön jóváhagyott mentést. Natív Windows- és natív böngészős vizuális próba nem történt.
