# C21.8.1 – Felmérésmentés és közvetlen visszajelzés

A kérdéssor hat kitöltött lépése és a használható referenciák száma nem igazolja a szervermentést. Korábban egy helyi ellenőrzési vagy szerverhiba csak a hosszú kérdőív tetején látszott. A blokk alján kattintó felhasználó így nem kapott látható magyarázatot a megakadásra.

A mentés gombjánál most az eredeti művelet állapota jelenik meg: folyamatban, ellenőrzött siker, el sem indult kérés, szerver által elutasított kérés vagy még bizonytalan eredmény. A sikerjelzés csak a tartós bizonylat ellenőrzése után jelenik meg. További szerkesztéskor jelzi, hogy az új változtatás még mentetlen.

## Dátumegyeztetés

Reprodukált eset: a helyi piszkozatban korábbinál későbbre módosított felmérési dátum maradt, miközben a szerverre már ennél is újabb erőfelmérési eredmény került. A C21.8 összeolvasztása a helyi dátumot és a szerver új sorozatait együtt tartotta meg. A hat kérdéscsoport késznek látszott, de a mentés jogosan elutasította a felmérés dátuma utáni teljesítést.

A kifejezett frissforrás-átvétel most megtartja az újabb szerveren mentett felmérési dátumot. A gyakorlatok és sportreferenciák saját teljesítési dátumai változatlanok. Nem keletkezik kitalált mai mérés, és a későbbre beírt saját felmérési dátum sem gördül vissza. A változatlan backend továbbra is ellenőrzi a dátumokat és a forráshivatkozásokat.

A C21.8-ban már eltárolt, dátumütközés miatt érvénytelen helyi piszkozat is újranyitható, ha a dátum a saját, ellenőrzött mentett felmérés dátumával helyreállítható. A teljes eredeti piszkozat-ellenőrzés ilyenkor újra lefut; idegen tulajdonost, hibás megfigyelést vagy hiányzó mentett bizonyítékot ez nem enged át. A helyreállított válaszoknál új átnézést kérünk, és nem indul automatikus mentés. A függő POST bájtjaihoz ez a helyreállítás nem nyúl.

Külön hibás, hiányzó vagy jövőbeli felmérési dátumnál a kliens még POST előtt megáll, és a gomb mellett mutatja a konkrét problémát. A „Felmérés dátumának ellenőrzése” gomb az 1. lépést nyitja meg és oda viszi a fókuszt. A mérések megmaradnak.

## Függő mentés

Az ismeretlen kimenetelű kérés eredeti bájtjai megmaradnak. A blokk mentési helyén is megjelenik az „Azonos mentés ellenőrzése” gomb; ez nem készít másik kérelmet. Újranyitáskor nem indul automatikus POST. Biztos szerverelutasítás után ugyanitt készíthető elő a friss adatokkal az új mentés, új átnézéshez kötve.

A backend, az adatbázisséma, a függő kérés formátuma és a bizonylat hash-/tulajdonos-/kérésellenőrzése nem változik. Mentési siker után továbbra is külön bekapcsológomb indítja az automatikus tervezést.

## Ellenőrzés

- Frontendregresszió: **1312 sikeres**.
- Next útvonaltípusok, TypeScript, ESLint, production build: sikeres.
- Valós API + React DOM próba: régebbi szerkesztett dátum és újabb mentett eredmény összeolvasztása, megjegyzések és referenciák megőrzése, sikeres mentés.
- Külön újranyitási próba: a korábbi verzió által már eltárolt hibás dátumú piszkozat visszaállítása, új átnézés és mentés, eredményvesztés és automatikus POST nélkül.
- Ugyanebben: mentést megelőző dátumhiba a látható gomb mellett, közvetlen dátumjavítás; elveszett POST-válasz és újranyitás után pontosan azonos bájtokkal újrapróbálás; valódi 409 forrásütközés után új mentés előkészítése és sikeres lezárás.
- A teljes C21.8 tervezési útvonal ismételt valós API/DOM próbája: sporteredmények mentése, kérdéssor aktualizálása, vezetett alkalom eredményeinek átvétele és kifejezett bekapcsolásra ténylegesen létrejövő edzések.

A változatlan backend 2140 tesztes regresszióját a C21.8-ban már ellenőriztük. Ennél a kizárólag frontendjavításnál nem ismételtük meg a teljes backendtesztcsomagot. A frissítő alapértelmezett tesztkapuja a frontend ellenőrzéseit futtatja; a `--with-backend` opcióval külön kérhető a teljes backendregresszió is.

A felületi ellenőrzés funkcionális DOM-próba volt valós API-val. Natív böngészős képi ellenőrzés ebben a környezetben nem történt.
