# P2.4C18.1 – Az edzéstervezés adatkapcsolata

Kiinduló commit: `cba7c5d61638729e1ce1caa6a6294919a522faf5`.

## Mit találtunk a forrásban?

| Terület | A C17 végén meglévő működés | A tényleges tervkészítéshez hiányzó kapcsolat |
| --- | --- | --- |
| Ciklusok és versenyek | Valós makro-/mezociklusok, módosítható határok, változatolt versenyprofilok | A napok és célok közös tervezési bemenete |
| Képességcélok és mérések | Külön C1–C3 regisztráció, explicit fejlesztési/fenntartási szerepek | A programhoz tartozó legújabb célváltozatok kiválasztása |
| Profil és lehetőségek | Változatolt sportmúlt, korlátok, napi idősávok, naptárszabályok | A tervezőhöz jutó idősávokból elveszett a sport-, intenzitás- és eszközkorlát |
| Teljesítések és visszajelzések | Polar-adatok, felülvizsgált kapcsolatok, korrekcióbiztos saját érzetek | Közös beolvasás a ciklussal és az aktuális időlehetőségekkel |
| Döntési motor | Auditálható edzéscsalád-választás, belépési és jogosultsági határok | Nincs bekötött heti tervgenerátor vagy személyes dózisválasztás |
| Terv mentése | Tervátvétel, változatok és végrehajtási kapcsolatok | Generált, ellenőrzött tervjelölt bekötése a meglévő írási útra |

A `planning/application/create_microcycle.py` és több korai orkestrációs fájl még üres. A `make_minimal_planner_decision` / `make_auditable_planner_run` edzéscsalád-műveletek között dönt, nem adagolt heti tervet gyárt. A C5 cikluslétrehozás naptári szerkezetet készít. A C12/C14 személyes bemeneti/asszociációs réteg önmagában nem jogosít személyre szabott terhelés előírására.

## Ennek a lépésnek az eredménye

Új, csak olvasó végpont:

`GET /api/v1/planning/cycles/programs/{program_id}/planning-inputs?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`

A konfigurált tulajdonos már meglévő felhasználóját használja, nem hoz létre felhasználót vagy edzést. A kezdőnap a sportoló helyi mai napja vagy későbbi nap; a teljes időszak 1–28 nap. Alapérték: hét nap. Historikus `as_of` nincs: a módosítható alkalmazásadatok mai olvasatáról nem állítunk utólagos ismeretelérhetőséget.

Egy olvasási tranzakcióban összeállítja:

- az ellenőrzött programot, a legfrissebb verseny- és ciklushatár-változatot, a tényleges időszaksorok egyezésével;
- a jelenlegi profil pontos hivatkozását, a sportmúltat, személyes korlátokat és a kézzel megadott adatokat;
- a legújabb, tartósan elérhető és visszajátszható makrociklus-célokat és mezociklus-protokollokat;
- naponta a hozzá tartozó mezociklust és az explicit képességszerepeket; a verseny kvalitatív képességigényéből nem talál ki célprioritást;
- a naptári és kézi időlehetőségeket, rögzített elfoglaltságokkal csökkentett intervallumokat, sport-, intenzitás-, eszköz- és helykorlátokkal;
- a meglévő edzésterveket sporttal és blokkokkal, a menetrendi időbecslést az előírt dózistól elkülönítve;
- a sportoló előző 14 napja és a mai nap ismert teljesítéseit, regenerációs rekordjait és a legújabb, a tudásidőpontban ismert visszajelzés-változatait.

Az edzéscím és a párosított alkalmazás-ID nem válik hitelesített végrehajtássá. Az előzmény csak a tárolt rekordokat jelenti, nem igazolt teljes adatlefedettséget. A friss profil és a ciklus létrehozásakor rögzített sportolói állapot külön fogalom; a ciklus eredeti rögzített tartalma megmarad.

A visszajelzés korrekciója felülírja a korábbi saját értéket az összeállításban, de nem a történetben. A hiányzó mérés null marad, a nulla ismert érték. A lebegőpontos forrásértékek a keresztplatformos hash miatt decimális szövegként szerepelnek. Nem történik átlagos sportmúltból dózisbecslés, klinikai minősítés vagy személyes modellillesztés.

## Időkeretek és állapotok

Az idősávok megosztott forráskereteit megőrizzük. Két átfedő lehetőség, két napra átnyúló ablak, illetve egy elfoglaltsággal kettévágott ablak kerete nem adható össze automatikusan. A napi maximum külön mező. Az `opportunities` nem terhelési ajánlás és nem automatikusan szabadnak tekintett nap.

- `declared_unavailable`: kifejezetten nincs megadott edzésidő; ez önmagában nem hiba vagy hiányosság.
- `opportunities`: van ismert, használható forrás-idősáv.
- `blocked`: a megadott idősávot ismert rögzített korlát foglalja el.
- `unknown`: az információ hiányos vagy időzóna-felülvizsgálat kell.

A hiánylista tájékoztatás, nem új globális belépési tilalom. Nem tettük kötelezővé a nemet, születési dátumot vagy minden nap edzéslehetőségét. Az eltérő időzónát, megváltozott célforrás-pillanatképet és meglévő tervütközést külön jelezzük.

A forráscsomag hash-elt jelenlegi előnézet, nem tartós döntési bizonyíték. PostgreSQL alapértelmezett izoláció mellett egy tranzakció sem állítja, hogy minden módosítható rekord ugyanazon fizikai pillanatból származik: `mutable_source_semantics=current_read_span`. A későbbi tervíró számára a hivatkozásokat és forrástartalmat újra kell ellenőrizni, majd az alkalmazott csomagot auditálhatóan rögzíteni.

## Felület és hatáskör

**Felkészülés → meglévő felkészülés kiválasztása → Edzéstervezés · bemeneti adatok.** A lenyitható rész alapból zárt. A gomb csak GET-kérést indít. Napokat, időlehetőségeket, képességszerepeket és az átvett előzmények darabszámát mutatja. Korábbi válasz nem írhatja felül az újabb dátumválasztást; a program vagy ismert ciklus-/versenyváltozat cseréjekor az előnézet törlődik.

A válasz hash-e, tulajdonosa, programhivatkozása, időzónája, teljes napi listája és a hamis tervezési/írási jogosultságok a böngészőben is ellenőrzöttek. Nincs automatikus lekérdezés, POST, adatfrissítés, modellfrissítés, edzéslétrehozás vagy tervmódosítás.

## Következő lépések az edzéstervig

1. **C18.2 – Célvezérelt jelöltek:** a valóban kijelölt képességszerepek és sport-/eszközkorlátok bekötése az edzéscsalád-választáshoz; forrásolt tudományos alapértelmezések, külön jelölt személyes bizonyíték. A meglévő belépési és jogosultsági határok megmaradnak.
2. **Dózis és heti elosztás:** megalapozott kezdőterhelés, visszatérés, meglévő terhelések és regeneráció figyelembevétele; napi keretek és pihenőnapok tiszteletben tartása. A menetrendi időbecslés nem edzésdózis.
3. **Felülvizsgálható tervjelölt:** a meglévő változatolt tervírási útra kötés; naptárba mentés, visszavonhatóság és pontos döntési források.
4. **Célhoz kötött visszamérés:** felmérések és megfelelően összehasonlítható edzésadatok, majd bizonyítékhoz kötött, ellenőrizhető személyes módosítások és rugalmas mezociklushatárok.

Ez a lépés az adatkapcsolatot készíti el. A `workout_generator_connected`, `dose_policy_connected`, `personal_model_applied`, `planning_authorized`, `workouts_created` és `workouts_changed` továbbra is false.
