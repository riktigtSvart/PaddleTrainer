# C20.6.3 — A kezdeti válaszok mentése a vezetett felmérésen belül

A C20.6.2 felhasználói képein a fekvenyomás és több másik gyakorlat már kijelölhető. Két közös indítási feltétel hiányzik: a mentett kezdeti felmérés forrásai elavultak, az átnézése pedig nincs mentve. A képeken nincs megkezdett alkalom vagy sorozateredmény; az előkészítő lapon eddig csak másik oldalra vezető hivatkozásokkal lehetett a kezdeti válaszokat rendezni. A csatolt C20.6.2 tesztkapu sikeres, HTTP-mentési hiba a képekből és a naplóból nem igazolható.

## Felhasználói folyamat

A vezetett felmérés előkészítésénél új gomb: **Kezdeti válaszok ellenőrzése és mentése itt**. Az eredeti, teljes kezdeti felmérő szerkesztő nyílik meg ugyanazon az oldalon, a 6. összegző lépésnél. A többi lépés is nyitható, a saját válaszok és a helyi piszkozat betöltési szabályai megmaradnak.

Ha a forrás vagy a mentési alap megváltozott, a felhasználó először a **Friss források és mentési alap átvétele** gombbal veszi át az aktuális forrást. Ez csak olvasás és a helyi mentési alap frissítése; nem indul POST, és az átnézés nem lesz automatikusan igaz. A válaszok megmaradnak.

Az összegzésben az explicit átnézés után a **Kezdeti válaszok mentése** gombbal menthető a válaszsor. Ehhez nem kell korábbi sorozateredmény vagy mind az öt mozgásminta kitöltése. A részleges kérdőív és az adott felmérőalkalom indíthatósága külön tulajdonság: a backend már korábban is külön kezelte ezeket. A beágyazott mentéshez az átnézés szükséges; az önálló felmérőoldalon továbbra is menthető részleges, még nem átnézett adat is.

A mentés ellenőrzött bizonylata után a vezetett állapot automatikusan újraolvasódik. Csak a továbbra is elérhető, egymástól eltérő mozgásmintájú gyakorlatok maradnak kijelölve. Ha a közös feltételek rendeződtek, a szerkesztő bezárul és az előkészítés folytatható. A felmérőalkalom indítása továbbra is külön kattintás. Más fennmaradó feltétel esetén a szerkesztő nyitva marad, az aktuális okok láthatók. Nyitott kezdeti szerkesztő mellett nem indítható alkalom; a **Vissza a gyakorlatválasztáshoz** gomb megőrzi a helyi piszkozatot.

A kezdeti szerkesztő az indítási akadályok megszűnése után is megnyitható. Így egy elveszett, de a szerveren már sikeres mentési válasz után is elérhető a függő kérés pontos újrapróbálása.

## Megvalósítás

- `AssessmentWorkspace` új opcionális beágyazott módot, kezdő lépést és kizárólag ellenőrzött mentés után hívott `onCommitted` visszahívást kapott. A korábbi `onSaved` használat változatlan.
- A beágyazott mód elhagyja a más oldalakra továbblépést kínáló panelek megjelenítését. A mentési gomb mellett konkrét szöveg jelzi, ha előbb forrásátvétel, átnézés vagy függő mentés rendezése szükséges.
- `GuidedWorkspace` megtartja az előkészítés saját helyszínét, kijelöléseit, naplózási módját és nyilatkozatát; mentés után újraolvassa és ellenőrzi a vezetett állapotot.
- Az indíthatóság olvasásának hibája nem változtatja a már ellenőrzött kezdeti mentést ismeretlen eredményűvé. A felület jelzi a tartós mentést, és kézi szerverfrissítést kínál.
- Nem változott API-végpont, kérés- vagy bizonylatformátum, tárolási kulcs, backend tervezési szabály, adatbázis vagy függőség.

## Ellenőrzés

Az új API-esetek a tényleges HTTP-kapcsolaton reprodukálják a két közös akadályt. Az elavult forrással küldött mentést és a feltételek előtti indítást a backend elutasítja. A friss forráshoz tartozó, átnézett válaszok elmentése az eredeti gyakorlatokat és a nulla sorozatreferenciát megtartva teszi indíthatóvá az első alkalmat. A forrásátvétel önmagában nem állítja igazra az átnézést, és az átnézés nem tesz ismertté egy ismeretlen gyakorlatot.

Az új szintetikus frontend fixture valódi API-válaszokat tartalmaz: blokkolt állapot, mentési kérés és bizonylat, rendezett állapot, explicit indítás és aktív állapot. A böngészős szerződésolvasók mindet a rendes hash- és forrásellenőrzéssel olvassák.

A tényleges React komponensek JSDOM-kattintási próbája végigmegy a kijelölés → helyben megnyitás → forrásátvétel → átnézés → mentés → automatikus frissítés → külön indítás folyamaton. Vizsgált az elveszett válasz, a már sikeres szervermentés elveszett válasza, a hibás bizonylat, az újracsatolás és byte-azonos újrapróbálás, a helyi tárolás hibája és az indíthatóság utólagos frissítési hibája. Korábbi sorozat nélkül, részleges kérdéssorral is kipróbált az indítás. A korábbi kezdeti, vezetett és előkészítési kattintási próbák is újrafutottak.

Teljes képernyőképes böngészőellenőrzés nem készült. A módosítás a meglévő panel- és gombstílusokat használja; új CSS nincs. A teljes automatikus ellenőrzés parancsa: `python tools/run_c20_6_3_checks.py --build`.
