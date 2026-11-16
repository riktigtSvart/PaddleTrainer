# C21.10.2 — adott napi edzésalternatívák és tervezett fő cél

Az edzésablak alternatívák gombja korábban a teljes időszak tervezőjét ágyazta be. Annak aktív napja a mai nap volt, így egy későbbi edzés megnyitásakor másik napra mutatott, és a csere nem volt átlátható.

Az új választó a megnyitott edzés azonosítóját, napját, elfogadott jelöltjét és aktuális tartalmi lenyomatát használja. Kizárólag ehhez a naphoz tartozó támogatott változatokat sorol fel: sportág, helyszín, idő, időtartam, fő cél és végrehajtási utasítás. Az eredeti edzést külön jelöli. A választás teljes időszakra számított előnézetet készít; mentés előtt az összes érintett nap változása látható. Az edzéscsere a meglévő, tulajdonoshoz és forrásverzióhoz kötött, idempotens elfogadási művelettel történik. Megnyitáskor és függő kérés visszaállításakor nincs automatikus POST.

## Naptári jelzés

- `↔ 2`: két másik jelölt a legutóbbi felülvizsgálatban.
- `↔ 0`: a legutóbbi felülvizsgálatban nem volt másik jelölt.
- `↔ ?`: friss ellenőrzés szükséges.

A jelzés a napi, heti és négyhetes nézetben is megjelenik a saját, még cserélhető jövőbeli edzéseken. Nem jelent előre garantált időjárási vagy rendelkezésre állási megfelelést. A friss ellenőrzés és a mentés újra ellenőrzi a feltételeket. A kötött, importált, szerkesztett vagy már teljesített előírást nem teszi automatikusan cserélhetővé.

## Fő cél és kompatibilitás

A `calendar-training-plan-v0.1` olvasási vetület visszakeresi a saját edzés elfogadásának bizonylatát és az abban hivatkozott, változatlan tervezési javaslatot. Innen származik a képességkulcs, a mezociklus és a képesség szerepe. Meglévő edzéseknél is működik, adatbázis-migráció és új felmérés nélkül. A célra nem következtetünk az edzés címéből vagy sportágából. Megváltoztatott előírás nem kapja meg automatikusan a régi célját; a teljesítési státusz önmagában nem törli az eredeti cél ismeretét.

A külön megadott, nem üres naptári céljelölés elsőbbséget élvez. A jelölés törlése visszaállítja a tervező szerinti célt. A céljelölés szerkesztése az edzés előírását nem változtatja meg. A régi, vetület nélküli naptári válasz továbbra is olvasható. A `WorkoutOut` és a mentett edzéslenyomat nem változik, így a korábbi elfogadások változatlanul ellenőrizhetők.

A tervstátusz lekérdezése a legutóbbi, adott tulajdonoshoz és felkészüléshez tartozó felülvizsgálatot és elfogadást olvassa; a teljes korábbi tervezési történetet nem tölti le minden edzésablak megnyitásához.

## Ellenőrzés

`python tools/run_c21_10_2_checks.py` futtatja a teljes backend tervezési regressziót, az összes frontend tesztet, a Next típusgenerálást, TypeScriptet, az érintett fájlok lintjét és a production buildet.

Új tényleges HTTP-próbák ellenőrzik a korábban elfogadott sorok célját írás nélkül, egy későbbi nap cseréjét plusz alkalom nélkül, és a módosított, importált, teljesített edzések kezelését. A frontend ellenőrzi a naphoz és lenyomathoz kötést, a vetületet, a nulla/ismeretlen jelzést, a kézi céljelölést és az összes naptári nézetet.

Fejlesztői folyamatpróba valódi FastAPI és React StrictMode/JSDOM között: későbbi nap megnyitása, választás, teljes változási előnézet, átnézés jelölése, tényleges elfogadás, elveszett válasz, újranyitás automatikus újraküldés nélkül, majd a byte szerint azonos kérés kézi folytatása. Natív böngészős vizuális ellenőrzés nem történt.
