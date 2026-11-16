# C21.10.14 — Az edzésalternatívák hibás elutasításának javítása

A C21.10.13-ban az erősítő változatok ellenőrzése egy újonnan beolvasott teljesítés után elutasíthatta az egyébként érvényes teljes tervválaszt. A naptári számláló továbbra is mutatta a legutóbbi felülvizsgálat változatait, de a megnyitott listán az „Az erősítő munkamennyiség vagy naplóforrás nem ellenőrizhető.” üzenet jelent meg.

## Ok és javítás

A szerver az elfogadott mezociklushoz megőrzi a korábbi időtartam-referenciát a `calibration_review.inputs` alatt. A napi lehetőségeket, saját gyakorlatreferenciákat, naplózott munkasorozatokat és aktuális terhelési keretet ettől függetlenül frissen ellenőrzi. A frontend új erősítő ellenőrzője a referenciában szereplő edzésazonosítókat és időadatokat tévesen mindig az aktuális előzményekből számolta újra. Új import után ezért eltérés keletkezett.

A javítás a megőrzött időtartam-referenciát a hozzá tartozó, megőrzött időpont adataiból ellenőrzi. A gyakorlatok alkalmassága, terhelése, sorozatszáma, helyszíne és az aktuális napló továbbra is a friss forrásból származik. A tulajdonos, hash, időhatár és konkrét dózis ellenőrzése megmarad. Az újonnan importált előzményt nem lehet a régi hivatkozás mögé behelyettesíteni.

A betöltési hibánál a felület külön elmagyarázza, hogy a korábbi jelzés a legutóbbi terv változatait számolja, és a jelenleg választható lista ellenőrzése nem sikerült. Így a betöltési hiba elkülönül a ténylegesen üres listától.

## Használat

Frontendfrissítés és böngésző-újratöltés után nyisd meg újra az edzést és az **Alternatív edzések** részt. Szükség esetén az **Alternatívák friss ellenőrzése** kéri az aktuális listát. Az **Ezt választom helyette** előnézetet készít; a naptár az összes érintett változás megtekintése, külön megerősítés és **Edzéscsere mentése** után változik. A felméréseket nem kell újramenteni, és a javításhoz nem kell a teljes edzéstervet újragenerálni.

## Ellenőrzés

- Két valódi, elkülönített HTTP-adatbázisos eset: egy későbbi import mellett megmaradó ciklusreferencia és új, aktuális sorozatnapló a korábbi kiindulópont mellett. A választás mentés előtt nem módosítja a naptárt; elfogadáskor pontosan egy edzés váltja fel a kiválasztott nap korábbi edzését.
- Öt új frontendteszt a tényleges API-válaszokkal: referencia-ellenőrzés, napi lista, választás, friss napló figyelembevétele és hamisított referencia elutasítása. A hiba a javítás előtt ugyanazzal a magyar üzenettel reprodukálható volt.
- A teljes frontendkészlet, típusgenerálás, TypeScript, érintett ESLint és production build ellenőrzött.
- FastAPI + React StrictMode/JSDOM próba: listabetöltés, hibás lekérés magyarázata, nincs automatikus naptárírás, napi kiválasztás, előnézet és külön jóváhagyott csere. Ez nem natív Windows- vagy natív böngészős vizuális próba.

A futó API-kód és az adatbázisséma nem változik. A C21.10.13-as terv- és dózisszerződések változatlanok. A kiadás nem módosít súlyt, ismétlést vagy sorozatszámot.
