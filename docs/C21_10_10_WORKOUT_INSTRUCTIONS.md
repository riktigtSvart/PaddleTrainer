# C21.10.10 — naptári hétkezdés és konkrét edzésutasítások

A C21.10.9 forrásaira épül. Nincs új függőség vagy adatbázis-migráció.

## Naptári hétkezdés

A naptár felső sorának **Hét kezdete** választója két módot kínál:

- **Hétfő**: a megszokott naptári hét.
- **Mikrociklus kezdőnapja**: a kiválasztott naphoz tartozó mentett mezociklus kezdőnapjának megfelelő hétköznap. A jelenlegi tervező ettől a dátumtól hétnapos mikrociklusokat képez; az utolsó blokk rövidebb lehet.

A kapcsoló a naptári elrendezést módosítja. A ciklusok dátumait, az edzéseket és a felméréseket nem írja át. A napi nézetben letiltott, mert ott nincs heti oszloprend. A heti, négyhetes és görgethető áttekintő nézet dátumai és napfejlécei együtt fordulnak el. Az áttekintés 28 napos szakaszai folyamatosak maradnak.

A beállítás a korábbi `calendar-visibility-v0.1` böngészőtárhely-adatok opcionális `weekStart` mezője. Sportolónként és nézetenként külön tárolódik. A régi rétegkapcsolók és a mikrociklusszínek megmaradnak; a hétkezdés régi adatoknál hétfő. Hiányzó vagy átfedő mezociklus esetén a felület ezt jelzi, és átmenetileg hétfővel rajzol. Az eredeti választást megőrzi.

## Edzés lépésről lépésre

A támogatott automatikus futó-, kajak-, úszó- és erősítő edzésekhez három rész jelenik meg:

1. Bemelegítés és gimnasztika: könnyű kezdés, sportághoz választott átmozgatás, ismert sportmozgás előkészítése, külön időkeretekkel.
2. Főrész: az eredeti sportági utasítás, erősítésnél a mentett saját gyakorlatok táblázata.
3. Levezetés: a meglévő ötpereces szakasz, benne választható kétperces nyújtással. A nyújtás a levezetés utolsó két percét helyettesíti, nincs hozzáadott edzésidő.

A gimnasztika ebben a kiadásban a bemelegítés része; a nyújtás külön megnyitható, mozgástartományt célzó rész. Önálló GYMNASTICS/STRETCHING edzésalkalom automatikus kiosztása nem került be. A sorok általános termékminták, nem személyesen felmért mozgáskorrekciók vagy bizonyított regenerációs kezelések. Az ismeretlen, kellemetlen vagy az adott helyszínen nem kivitelezhető részt ki lehet hagyni. Úszásnál a bemelegítés az ismert úszásnemben történik, a választható szárazföldi nyújtás csak a víz elhagyása után, stabil talajon.

Az utasítás a naptárból megnyitott edzésablakban, a teljes edzésadatlapon, valamint a tervező kiválasztott és alternatív edzéseinél érhető el.

## Saját terhelések és ismétléstartalék

A táblázat gyakorlatonként és sorozatonként mutatja a rögzített ismétlést vagy tartásidőt, a saját súlyt és annak értelmét (például kézenkénti kg), a referencia tartalékát, a pihenőt, a mérés dátumát és az ismert gépbeállítást.

A korábban ellenőrzött `assessed-strength-dose-v0.1` előírás változatlan: legfeljebb két gyakorlat, gyakorlatonként legfeljebb két mentett sorozat, legalább három ismétlésnyi tartalék, a megadott két- vagy háromperces pihenővel. A megjelenített ismétlésszám felső cél; a felhasználó korábban megállhat, ha a tartalék vagy a kontroll romlik. Az időkeretet nem kell kitölteni, a pihenőt emiatt nem szabad rövidíteni.

Új súly, ismétlés, munkasorozat, 1RM-becslés vagy automatikus terhelésemelés nincs. A bemelegítő, külső súly nélküli mozgáspróba előkészítés, nem új munkasorozat. Számszerű saját referencia hiányában a már támogatott, külső súly nélküli bevezető minta jelenik meg, legfeljebb öt könnyű ismétléssel. Ez nem igazolt maximáliserő-fejlesztő dózis.

A felvetett kifáradásig végzett vagy két ismétlésnyi tartalékra célzó felmérési mód nem lett alapértelmezés vagy új adagolási szabály. A meglévő kezdőminta háromismétléses tartalékát ez a megjelenítési frissítés megőrzi. A szakirodalmi összefoglaló alapján a teljes kifáradás nem szükséges minden erőedzéshez; az optimális ismétléstartalékot az egyéni cél és tapasztalat nélkül nem állítjuk be bizonyított személyes értékként.

## Ellenőrizhető adatkapcsolat

A `training-plan-policy-v0.14` eredmény új `instruction_context` mezője csak a tényleges javaslatokhoz tárolja a részleteket. Így a sok, ki nem választott alternatíva nem sokszorozza meg a tárolt magyarázatokat. Az alternatívák utasításai a már ellenőrzött előírásból és ugyanabból a változatozott gyakorlatsorból állnak elő.

A backend és a frontend `training-routines-v0.1` tartalma azonos. A frontend újraszámolja az utasítást, és a felülvizsgálat tartalmi lenyomatának átírása sem tesz elfogadhatóvá hozzáadott időt, új súlyt, új ismétlést vagy hamis regenerációs állítást. A naptári sorok erősítő utasítását az eredeti címhez és leíráshoz is hozzáellenőrzi.

A naptári kivetítés az eredeti, elfogadott felülvizsgálatból dolgozik, a már meglévő tulajdonos-, forráshivatkozás- és előíráshash-ellenőrzések után. A korábbi C21.10.9-es elfogadások is kaphatnak részletes megjelenítést, újramérés és adatátírás nélkül. Kézzel átírt előírás vagy külső import nem örököl hitelesített számszerű utasítást. A felmérések forrásérvényességi szabályai változatlanok.

A teljes edzésadatlap külön, csak olvasó betöltője újraellenőrzi az azonosítót, sportot, időt és leírást. Új edzésre váltáskor nem mutatja a korábbi edzés táblázatát, a későn visszaérő választ figyelmen kívül hagyja. Hálózati hiba esetén újraolvasás kérhető.

## Szakmai háttér és korlát

- ACSM 2026, erőedzés: https://pmc.ncbi.nlm.nih.gov/articles/PMC12965823/
- Nyújtás, mozgástartomány és a bemelegítés eltérő céljai: https://pmc.ncbi.nlm.nih.gov/articles/PMC13423734/

A konkrét rövid átmozgató és nyújtó sor termékbeli kiindulóminta; a hivatkozások nem igazolják annak személyes optimumát vagy sérülésmegelőző hatását. A nyújtásnál nem állítunk regenerációs hatást.

## Ellenőrzés

`tools/run_c21_10_10_checks.py`: teljes backend-tervezési regresszió, teljes frontendtesztkészlet, Next útvonaltípusok, TypeScript, az érintett TS/TSX/MJS fájlok ESLint-ellenőrzése és production build.

Az új API-tesztek ellenőrzik a négy sportág konkrét szakaszait, a teljes és részidők azonosságát, a változatlan felmérési sorozatokat, az új és korábbi elfogadott tervek csak olvasó kivetítését, valamint a megváltoztatott előírások kizárását. A frontendtesztek valódi API-ból exportált adatokon ellenőrzik a régi/új tervek olvasását, a manipulált súly/idő/tartalék elutasítását, a különböző hétkezdéseket, az átfedéses tartalék működését, a régi beállításokat és a táblázatot.

Valódi FastAPI + React StrictMode/JSDOM próba futott a teljes naptárkomponenssel: hétfő/péntek váltás, külön nézetpreferenciák és újranyitás, négyhetes fejléc, összefüggő áttekintő szakaszok, ciklus nélküli dátum és visszatérés, edzésablakból látható saját súly, nyújtó rész, bezárás/fókusz, teljesadatlap-betöltés, hiba utáni újraolvasás és késői válasz kezelése. A próba nem küldött írási kérést; az audit-, edzés- és teljesítéssorok száma változatlan maradt. Natív Chromium vizuális ellenőrzés nem történt.
