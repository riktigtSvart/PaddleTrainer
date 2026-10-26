# P2.4C7 — közös adatkapcsolati panel és kézi Polar-frissítés

## Kiindulás

A 2026-10-25-én átadott 935 fájlos C5 + R1 + R2 + C6 munkafa az alap.
`main`, HEAD és a várt `origin/main`:
`3ca1165cc9d21b6b83a3b1e95090261d49524173`.
A meglévő, még nem commitolt változtatásokat a csomag bemenetként kezeli.
Új npm/Python-függőség és új DB-migráció nincs.

## Felület

A közös felső fejléc most a naptáron is megjelenik. A témaváltó mellett minden
oldalon ugyanott található az Adatkapcsolatok ikon. Normál állapotban csak az
ikon és a pipa/óra jel látszik. Futás közben forgó nyíl, figyelmet igénylő
helyzetben felkiáltójel és rövid felirat jelenik meg. A szín kiegészíti a jelet;
az állapot színlátástól függetlenül is megkülönböztethető.

Rámutatásra/fókusznál rövid tájékoztatás, kattintásra kis panel nyílik. A panel
Escape-pel bezárható, a billentyűzetes fókusz visszatér az ikonra. A csökkentett
mozgás rendszerbeállítása leállítja a forgó animációt.

A panel külön mutatja:

- az utolsó, tartósan igazolt sikeres frissítést és annak adatfajtáit;
- a saját adatbázisban található legfrissebb Polar-edzés időpontját;
- a legutóbbi futás állapotát és kibontva az új/frissített/kihagyott darabszámokat.

Régi importokból származó edzések esetén az utolsó szinkron ideje ismeretlen
marad az első C7-futásig. A kapcsolat tokenjének frissítési ideje nem lesz
szinkronidő. Egy ma sikeresen lefutott, de új edzést nem találó lekérés mellett
a legfrissebb edzés dátuma továbbra is régebbi maradhat.

Az ikon és a Kapcsolati állapot újraolvasása csak helyi adatot olvas. A Polarhoz
a Szinkronizálás gomb kapcsolódik. A naptári Nézet frissítése külön helyi
újraolvasás. A szinkron eredménye után a naptár és annak megnyitott napi
állapotnézete automatikusan újraolvassa a saját adatbázist.

## Most átvett adatok

Az első adapter a Polar-edzések alapadatait és a Polar-edzésterveket kezeli.
Az alapértelmezett visszamenőleges időszak 35 nap, a mai napot is beleértve.
Kibontva 7 vagy 89 nap is választható. A tervekhez a következő 30 nap is
hozzátartozik. A kérés indulásakor rögzül az időszak és a sportoló időzónája;
azonos kérés ismétlése később sem választ új dátumokat.

A végdátum a szolgáltatói kérésben kizáró: a mai nap felvételéhez a következő
nap kerül bele. A training-target/calendar-targets hívás dokumentált paraméterei
`fromDate` és `toDate`; a dokumentált `trainingTarget` borítékot és a korábbi
listás alakot is kezeljük. A kliens korábbi hívói továbbra is listát kapnak,
a C7 az eredeti válaszborítékot is megőrzi.

Ez gyors naptári alapadat-frissítés. Nem indítja el a korábbi szolgáltatás
naponkénti mintasor-, statisztika- és terhelésdúsítását. A már eltárolt dúsított
nyers adatok megmaradnak. Az alvás, aktivitás, HRV, egész napos pulzus és egyéb
állapotadatok explicit átvétele továbbra is az R2 profil/Előzmények folyamatban
érhető el. Automatikus induláskori Polar-lekérés ebben a csomagban nincs.

A kapott provider-válaszokat tartalom szerint címezve ProviderDataRecord
rekordok őrzik. A korábbi Polar-terv nyers válasza felülírás előtt külön
forrásrekordba kerül. A hiányzó és nulla értékeket megkülönböztetjük.

A tervverziózásba már beemelt edzéstervek és a más forráshoz tartozó tervek
nem kapnak közvetlen importfelülírást. A kimaradt rekordokat a darabszám és a
részleges eredmény jelzi; a nyers válasz későbbi áttekintéshez megmarad.
A C7 nem indít tervezői döntést, hiteles tervmódosítást vagy automatikus
terv–teljesítés párosítást. Az új, külső Polar-tervek importja a meglévő
PlannedWorkout/WorkoutBlock vetületbe történik.

## Backend és ismétlés

- GET `/api/v1/data-connections/status`: saját, tárolt kapcsolati állapot.
- POST `/api/v1/data-connections/sync`: explicit kérés azonosítóval, providerrel,
  adatfajtákkal, visszamenőleges és előretekintő időszakkal.
- GET `/api/v1/data-connections/runs/{request_id}`: saját korábbi kérés igazolása.
- Zárt frontendútvonal: `/api/data-connections/...`.

A meglévő konfigurált sportolót használjuk; GET miatt nem jön létre felhasználó.
A válaszok `no-store` jelölést kapnak. A kapcsolati állapot titkokat, tokeneket
és upstream hibaszövegeket nem tartalmaz. A proxy csak a felsorolt útvonalakat
engedi, nem továbbít bejövő cookie-t vagy hitelesítési fejlécet. A POST eredetét,
JSON-típusát és a ténylegesen beérkező legfeljebb 16 KiB bájtot ellenőrzi.
A Polar újraengedélyezése külön, felhasználói kattintásra történő teljes
böngészőnavigáció az alkalmazás meglévő OAuth belépési pontjára.

Új, immutable auditfajták: DATA_SYNC_STARTED, DATA_SYNC_SUCCEEDED,
DATA_SYNC_FAILED. A kezdő és befejező rekord teljes tartalomhash-t,
tulajdonost, pontos kérést és egymásra hivatkozást tartalmaz. A foglalás
commitja és visszaolvasása megelőzi a hálózati adatátvételt. A tulajdonosi
sorzár és a tartós foglalás ugyanannál a providernél egyszerre egy C7-futást
enged a tokenfrissítés és az importer belső commitjai között is.

A végrehajtás a POST keretében, legfeljebb 180 másodpercig fut; nem külön
háttérmunkás. A kezdő foglalás 240 másodperces határidőt tartalmaz. Ha a szerver
újraindul vagy a befejezés nem rögzíthető, a határidő után az eredmény
„megszakadt/nem igazolható”. Ez nem igazol teljes sikert és nem állítja, hogy
semmi nem mentődött. Ekkor külön új kérés indítható. A korábbi kérés azonos
UUID-val való ismétlése a régi állapotát adja vissza, nem futtatja újra az importot.

Az azonos UUID eltérő tartalommal vagy providerrel ütközést jelent. A böngésző
sessionStorage-ban őrzi a pontos kérésbájtokat és a tulajdonost. Újratöltéskor
csak az eredményt ellenőrzi; automatikus POST nincs. Elfogadás előtti válaszvesztés
után kizárólag kifejezett, azonos bájtú újraküldés történhet. Commit utáni
válaszvesztés a futás lekérdezésével is feloldható. A kliens a commitigazolást,
azonosságot és a beágyazott szülőhash-t is ellenőrzi.

Részleges vagy sikertelen futás nem cseréli le az utolsó sikeres frissítés idejét.
A már commitolt adatokat nem állítjuk vissza elveszettnek. Ismert nulla darabszám
nulla marad; nem ismert darabszám „ismeretlen”, nem nulla.

A korábbi, külön admin/import végpontok nem válnak ezen a panelen keresztül
elérhetővé. A foglalás az új C7-folyamat futásait koordinálja; a korábbi külön
végpontok kézi, párhuzamos futtatására nem ad globális zárolási ígéretet.

## További szolgáltatók

A registry adja a provider nevét, elérhetőségét, adatfajtáit és kézi frissítési
lehetőségét. A Garmin és Suunto most kifejezetten későbbi integrációként látszik;
nincs hamis kapcsolódási vagy szinkrongombjuk. Bekötésükhöz saját adapter,
engedélyezés és tesztek szükségesek. Az automatikus adatküldésre épülő források
is ugyanebbe az állapotmodellbe illeszthetők a kézi művelet megfelelő jelzésével.

## Ellenőrzés

A hordozható kapu az új és a korábbi backend-/frontendteszteket, Next typegent,
teljes TypeScript-ellenőrzést, az érintett frontendfájlok ESLintjét és production
buildet futtatja. Az integrációs próba valódi React DOM-ot, production Next-proxyt,
valódi HTTP/domain/repository/import kódot használ, elkülönített SQLite-on és
szintetikus Polar-válaszokkal. Nincs éles DB- vagy külső fiókhozzáférés.

A helyi DOM-próba nem valódi böngészős képernyőkép-ellenőrzés. A 175%-os Windows
megjelenítést és a saját Polar-fiókkal történő első explicit szinkront helyben
szükséges kipróbálni. Az aktuális teszteredmény a telepítőcsomag VALIDATION.json
fájljában található.

Elsődleges szolgáltatói forrás: [Polar AccessLink Dynamic API v4](https://www.polar.com/polar-api-v4/),
ellenőrizve: 2026-10-25, Training Sessions és Training targets fejezetek.
