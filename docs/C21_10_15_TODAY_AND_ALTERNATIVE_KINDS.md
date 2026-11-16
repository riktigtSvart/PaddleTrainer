# C21.10.15 — Mai edzéscsere, eltérő edzések és időpont/helyszín-változatok

## Miért hiányoztak a mai alternatívák?

A korábbi védelem a tervezett kezdés elmúltával az edzést már nem cserélhetőnek tekintette. Ez nem bizonyítja, hogy az edzés elkezdődött: a reggeli 08:00-s tervről később is dönthet úgy a sportoló, hogy mást szeretne. Az automatikus újratervezésnél továbbra is megmarad ez a védelem; a mai edzés kifejezett felhasználói kérésre cserélhető.

A mai edzés **Alternatív edzések** részében jelöld be: **A mai edzést még nem kezdtem el.** Ezután az **Alternatívák friss ellenőrzése** az adott nap még hátralévő, ténylegesen használható időablakaiban keres. Az **Ezt választom helyette** előnézetet készít; a naptár a változáslista áttekintése, külön megerősítés és **Edzéscsere mentése** után változik.

A befejezett, elkezdett, teljesítéshez kapcsolt, jóváhagyott vagy időközben átírt edzés ettől nem válik cserélhetővé. A megerősítés csak a megnyitott edzésre és az adott helyi napra szól; más napra és automatikus újratervezésre nem öröklődik. A mentés előtt a szerver újra ellenőrzi az aktuális helyzetet. Ha nincs már megfelelő lehetőség mára, a terv megmarad, és a felület elmagyarázza a helyzetet.

Az időablakok, napfény, ismert terhelés, pihenőidők, napi edzésszám és gördülő/cikluskeretek továbbra is számítanak. A mai cseréhez nem szükséges új felmérés vagy a teljes terv újragenerálása.

## Az alternatívák két csoportja

- **Más edzések:** eltérő sportág, fő cél, időtartam, gyakorlatsor vagy előírt munkamennyiség. Egy ilyen edzéshez több időpont és helyszín tartozhat; ezeket a saját **Időpontok és helyszínek** lenyíló részében mutatjuk.
- **Ugyanez az edzés máskor vagy máshol:** a naptárban lévő edzéssel azonos tartalom és előírás, eltérő időponttal/helyszínnel.

Az azonos edzés különböző helyszínei nem növelik a „más edzés” darabszámát. A forrásazonosító, a referenciadátum vagy a számok szöveges formátuma önmagában sem jelent új edzést. A tényleges sorozatszám, súly, ismétlés, tartás, pihenő vagy előírt tartalék eltérése különböző tartalom.

A naptári **↔ N · ◷ M** jelzésben N az eltérő edzések száma, M a jelenlegi edzés további időpont/helyszín-lehetőségeinek száma a legutóbbi ellenőrzésben. A többi edzés saját további időpontjait a megnyitott csoport tartalmazza. Az ismeretlen/frissítendő és a valóban nulla lehetőség külön állapot marad.

## Technikai határ és ellenőrzés

Az új opcionális `same-day-training-replacement-v0.1` kérés mind a felső szinten, mind a rögzített bemeneti pillanatképben szerepel. Az aktuális napot, tulajdonost, tervváltozatot, változatlan sor tartalmát és a tényleges teljesítési kapcsolatokat frissen ellenőrizzük. A választás és az elfogadás megőrzi a kérés hatókörét; az automatikus elfogadás nem használhatja. Ha közben teljesítés érkezik vagy helyi napváltás történik, a korábbi előnézet nem fogadható el.

Az új csoportosítás olvasási célú, nem változtatja a jelöltek dózisát vagy hitelesített forrásait. Az opcionális naptári összesítés a régi válaszokkal együtt olvasható. A policy verziója és az adatbázisséma változatlan. Backend- és frontendfrissítés, mindkét folyamat újraindítása szükséges.

Ellenőrzések: teljes frontend **1736 sikeres teszt**, teljes backend tervezési készlet **2391 sikeres teszt**, majd a végleges új esetcsoport **13 sikeres teszt** (köztük egy további jövőnapi elutasítás). A típusgenerálás, TypeScript, érintett ESLint és production build sikeres. Valódi FastAPI + React StrictMode/JSDOM próba igazolta a lejárt reggeli kezdésű edzés délutáni cseréjét, a csoportosítást, az írásmentes előnézetet és az egyetlen jóváhagyott helyettesítést. Natív Windows- és natív böngészős vizuális próba nem történt.

A `tools/run_c21_10_15_checks.py` alapból az új 13 backendtesztet, az érintett frontendkészletet, típusellenőrzést, lintet és buildet futtatja. `--full-backend` és `--full-frontend` kérhető; `--frontend-only` akkor használható, ha ugyanezekkel a forrásokkal a backend már sikeresen lefutott.
