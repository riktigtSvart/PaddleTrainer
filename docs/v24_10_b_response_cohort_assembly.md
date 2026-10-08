# V24.10-B — forráshoz kötött kohorszindex

Alap: `08cfb5ddfb6f318b5be0081557f914bf92ca4ce7` (V24.10-A).
Migrációs head: `d83b9c61f204`, változatlan.

Elkészült a kiválasztott teljes edzések forrásellenőrzése és az ellenőrzött
taghivatkozásokat összesítő index. Új API-végpont, adatbázistábla, migráció vagy
függőség nincs. Az időrendi felosztás ellenőrzése a V24.10-C feladata.

## Ellenőrzési sorrend

`app.services.response_cohort_assembly.assemble_response_cohort(db, manifest,
user_id=...)` a V24.10-A szigorú manifestjét újra validálja. A `user_id` a
megbízható szerveroldali hívótól származik; a manifest sportolóazonosítója
elvárt érték, nem felhasználóválasztó vagy jogosultságigazolás.

1. A végrehajtási tagkorlát és az elvárt tulajdonos ellenőrzése.
2. Létező, tulajdonoshoz tartozó Polar-kapcsolat és `training_sessions:read`
   jogosultság. Nincs más sportolóhoz vagy kapcsolathoz visszaesés.
3. Minden kiválasztott pillanatkép tulajdonos/edzés/környezeti bizonyíték
   SQL-kapcsolata és elvárt metadata-pinje. Ez teljes pillanatképek betöltése
   nélkül, még a Polar-kérések előtt történik.
4. Egyenként a V24.9 tényleges adatbázissor-, mérési érték-, szegmens-FK- és
   döntésilánc-ellenőrzése, a pin ismételt ellenőrzésével. Nem kizárólag JSON-ban
   megadott `verified` állításokat vagy egyező hash-eket fogadunk el.
5. A manifest `route_date` szerinti aktuális Polar `routes` és `samples` lekérés;
   a konkrét edzés pontosan egy egyezése. Aktuális, tulajdonoshoz és forráshoz
   kötött HR-óra- és szenzornyilatkozat-igazolások betöltése.
6. Teljes V24.9 replay előállítása, mindig `split_manifest=None` értékkel.
   A mentett környezeti bemenet és az aktuális Polar-/HR-bizonyítékok egyezése,
   majd ugyanaz az adatbázis-ellenőrzési proveniencia és csomaglenyomat, mint a
   meglévő `/response-dataset/replay` API teljes, `UNASSIGNED` válaszában.
7. Teljes tartalmi hash, belső HR-rács-, ablak-, útvonal-, sor- és
   előzményhivatkozás-ellenőrzés. Egyezés a manifest
   `expected_unassigned_replay_package_hash` értékével.
8. Rövid tagindex és összesítés. Kért besorolás kizárólag az index
   `requested_split` metadata mezőjében jelenik meg; a tag alapcsomagját,
   előzményeit, HR-helyeit vagy hash-ét nem módosítja.

A vizsgálat a tagokat a futás során egyenként ellenőrzi; nem állít minden
külső szolgáltatásra kiterjedő, egyetlen pillanatban érvényes tranzakciót.
A szolgáltatás nem hoz létre edzést, pillanatképet vagy tudományos bizonyítékot,
és környezeti szolgáltatót nem hív. A meglévő Polar tokenkezelő a lejárt
hitelesítési tokent frissítheti és a kapcsolatban mentheti. A
`science_storage_writes=0` a tudományos adatokra vonatkozik.

## Az index jelentése

Sikeres forrásellenőrzés:
`SOURCE_VERIFIED_COHORT_INDEX_WITH_LIMITATIONS`;
`claim_scope=SELECTED_MEMBER_SOURCE_BINDING_AND_PAYLOAD_INTEGRITY_ONLY`.

Az index tartalmazza a kéréslenyomatot, a tagok csoportazonosítóit, a kiválasztott
pillanatkép/környezeti bizonyíték/forrás/HR-bizonyíték/csomag lenyomatait,
darabszámokat, jellemzőnkénti hiányösszesítést, HR-ablakállapotokat,
ismeretlen kezdeti állapotot és cenzúrázott előzmény/recovery határokat jelző
darabszámokat, valamint a forráshoz kötött útvonal-gyakorlat kezdéseket.
A teljes adatok az eredeti, saját hash-sel ellenőrizhető tagcsomagokban maradnak.

A `cohort_index_hash` a teljes sikeres index SHA-256 lenyomata, a saját
hash-mezője nélkül. A JSON kulcsrendezése, ASCII escape-je és kompakt
formátuma megegyezik a V24.9 hash-szabályával. A tagok sorrendje kanonikus
edzésazonosító-sorrend, **nem időrend**. Nincs hash-t változtató futásidő vagy
aktuális ellenőrzési időbélyeg. Változatlan kérés és ellenőrzött források
változatlan indexet adnak; a kért besorolás az index hash-ét megváltoztatja.

Ha egy tag hibás, hiányzik, megváltozott, vagy a teljes kérés túllépi a
végrehajtási korlátot: `WITHHELD`, `source_evidence_verified=false`,
`verified_member_count=0`, `members=[]`, `totals=null`, `cohort_index_hash=null`.
Nincs részleges siker, tagkihagyás, új pillanatképválasztás vagy automatikus
környezeti újralekérés. A hibás tag kanonikus indexe és rögzített hibakódja
korlátozott diagnosztika; nyers források, titkos tokenek és más tulajdonos
adatai nem kerülnek a hibakimenetbe.

A `verify_cohort_index_integrity()` és a
`check_response_dataset_integrity()` egy kapott JSON hash-ét és belső
következetességét ellenőrzik. **Ezek nem igazolják újra az adatbázist, a
tulajdonost, az aktuális forrást vagy a mérési minőséget.** Ilyen igazolást csak
a tényleges összeállító futása adhat ki. Egy kliens által újraszámolt hash és
`source_evidence_verified=true` mező önmagában nem forrásbizonyíték.

## Végrehajtási korlátok

| Határ | Érték |
| --- | --- |
| Manifest formai korlát, változatlan | 100 tag |
| Egy B összeállítás támogatott korlátja | 20 tag |
| Teljes összeállítási időkeret | 120 másodperc |
| Egy mentett pillanatkép, V24.9 alapján | 64 MiB |
| Egy kiválasztott aktuális Polar-forrás | 16 MiB |
| Egy teljes újraelőállított csomag | 64 MiB |
| Megfigyelések egy tagban | 100 000 |
| HR-helyek egy tagban | 200 000 |
| Útvonalak egy tagban | 256 |
| Teljes sikeres index | 1 MiB |

A feldolgozás szekvenciális. A tag teljes adatai csak az adott tag vizsgálatánál
szükségesek; nem épül kohorszméretű HR-/megfigyelési tömb. A JSON-mérethatár
ellenőrzése nem hoz létre egy második teljes JSON-karakterláncot.

Ezek támogatott bemeneti/eredményméret-korlátok, nem az operációs rendszer
által kikényszerített processz-memóriahatárok. Az adatbázis/HTTP-kliens egy
válaszát már a saját betöltése során materializálja; a környezeti replay korábbi
validálója is használ átmeneti másolatokat. Az időkeret az `await` pontoknál
megszakítja a várakozást, szinkron számítási lépések között pedig ellenőrizhető;
nem tud futó szinkron Python-kódot tetszőleges utasításnál megszakítani.
Nagyobb vagy lassabb kérésnél kisebb, külön kiválasztás szükséges, nincs
automatikus részleges eredmény. Külön indexek nem helyettesítik a későbbi teljes
kohorsz időrendi/felosztási ellenőrzését.

## Önálló parancs, meglévő helyi konfigurációval

`tools/build_response_cohort_index.py` két műveletet támogat:

```text
PYTHONPATH=apps/api python tools/build_response_cohort_index.py prepare --member 2026-09-30 response_dataset_replay_1.json --manifest-id control-b --output request.json
PYTHONPATH=apps/api python tools/build_response_cohort_index.py verify request.json --output cohort_index.json
```

További teljes edzéshez a `--member ROUTE_DATE FULL_REPLAY` ismételhető.
A `prepare` csak teljes, hash- és hivatkozásellenőrzött, `UNASSIGNED` helyi
replay-csomagból készít elvárt pineket; nem hív adatbázist vagy szolgáltatót,
és `source_evidence_verified=false` eredményt ad. A közölt pinek később a
valódi adatbázissal és Polar-forrással egyeztetendők. A `verify` a projekt
meglévő `.env`/környezeti beállításai alapján az **ott konfigurált, már létező
demo-felhasználót** keresi ki, nem a manifestből választja a futtató tulajdonost.
Hiányzó felhasználót nem hoz létre. Ez a korábbi demo-auth modell marad;
többfelhasználós éles jogosultsági rendszer nincs bevezetve.

Az API-t nem kell újraindítani a parancshoz; az adatbázis és a tulajdonos Polar-
kapcsolata szükséges. Új kimeneti fájlt kizárólag sikeres indexhez ír; korábbi
fájlt nem ír felül. Visszatartott vagy hibás eredménynél nem nulla a kilépési
kód. A bemeneti JSON UTF-8 BOM-mal is olvasható; duplikált kulcs és nem véges
szám elutasítandó. Az A rész szintetikus példái nem élő B kérések.

A ZIP önálló PowerShell szövegblokkot ad a korábban elmentett valódi V24.9
teljes replay kiválasztására, két ismételt összeállításra és hibás pin-próbára.
Nem kell `.ps1` fájlt futtatni vagy ExecutionPolicy-t módosítani.

## Tudományos határok és ellenőrzés

`chronological_cohort_order_verified=false`, `split_assignment_persisted=false`,
`training_authorized=false`, `numeric_output_authorized=false`.
A tényleges teljes edzésintervallum, edzések közti másolat/újraimport,
TRAIN–VALIDATION–TEST sorrend, átfedés és teljes felosztás ellenőrzése C-ben jön.
A `route_date` lekérési segédérték marad. Útvonal-kezdések önmagukban még nem
bizonyítják a teljes edzésintervallumot vagy a kohorsz időrendjét.

Nincs fix HR-eltolás, fiziológiai késés becslése, fáradtságpontszám, imputáció,
modellillesztés vagy helyi áramlási sebesség becslése vízállásból/vízhozamból.
Az exportóra-eltérés nem élettani késés. A HR külön célmintasorozat marad;
a hiányos HR-szakasz terhelési előzménye és a cenzúrázott határok megmaradnak.
A forrásellenőrzés nem igazolja a szenzor azonosságát vagy mérési minőségét.

A tesztek tényleges SQLite-sorokat és kapcsolatokat ellenőriznek szintetikus
Polar-válaszokkal, több teljes edzéssel, illetve negatív pin/tulajdonos/forrás/
HR-bizonyíték/FK/döntésilánc/tartalmi-hivatkozás/időkeret esetekkel. Az eredeti
V24.9 API-val azonos teljes replay-hash külön regresszió. A felhasználói
PostgreSQL/Polar élő próba ettől külön ellenőrzés; egy valódi kontrollteszt
nem jelent már teljes, élő több-edzéses kohorszértékelést.
