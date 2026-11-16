# C20.7.1 – saját testsúlyos felmérés és funkcióleltár

2026. november 7. Alap: C20.7.

## Felmérési cél

A saját testsúlyos ismétléses felmérés az előre kiválasztott, ismert gyakorlatváltozatban gyűjt teljesítményreferenciát. Nem választat terhelést egy tízes célismétlésszámhoz. A 19 érintett kártya `target_repetitions` értéke `null`. A megállási szabály és az első megfigyelés 12 ismétléses korlátja megmarad.

Ha a sportoló a korlátnál áll meg, az elvégzett ismétlés és a megadott tartalék a tényleges adat. Ez nem maximális ismétléskapacitás. Kevés ismétlés vagy tényleges nulla is rögzíthető. A már elvégzett, a tervezett határnál nagyobb eredmény megőrzése is változatlanul támogatott.

A saját testsúlyos ismételhetőségi mód ugyanahhoz az ismert változathoz ad utasítást. A súlyozott ismétléses, kontrollált, kitartási, cipelési és robbanékony alapfelmérési kártyák tartalma változatlan.

## Eredménybevitel

A saját testsúlyos ismétléses és kitartási gyakorlatok alapértelmezett adatbevitele a „Saját testsúly · külső súly nélkül” állapotot mutatja. Nem kér testtömeg-kilogramm választást. A ténylegesen más terheléssel elvégzett próba adatbeviteli lehetősége lenyitható marad.

A felmérési korlátnál befejezett saját testsúlyos ismétléses eredményhez rövid értelmezés jelenik meg: a maximális ismétlésszám ebből még nem ismert. A rögzített eredményt ez nem módosítja.

## Változatok és megőrzés

A C20.7-ben kiadott `strength_calibration_protocols_v0_3.json` és böngészős párja változatlan marad. Az új kártyák külön `v0_3_1` fájlban vannak; a bank tartalmi verziója `2026-11-07.2`. Az adatmodell változatlan `strength-calibration-v0.3`, a két támogatott kártyabankot a saját tartalmi lenyomat különbözteti meg.

- Az új szerverkontextus az új bankot kínálja.
- Az olvasó mindkét ismert bank pontos tartalmát ellenőrzi.
- Korábban áttekintett, még függő indítás az eredeti bankkal is végrehajtható, ha minden egyéb aktuális előfeltétel teljesül.
- A megkezdett alkalom és annak további mentései a kezdetkor rögzített bankhoz és utasításhoz tartoznak.
- Az aktív utasításmegjelenítés közvetlenül a rögzített lépéseket használja. Ismételhetőségi módban sem írja felül őket az új bank szövegével.
- Ismeretlen vagy tartalmilag módosított bankot a szerver és a böngésző elutasít.

A saját referencia és a következő edzés céladagjának számítása ettől nem változik. Az adatbázishoz nincs migráció, és nincs új alkalmazásfüggőség.

## A felület rendezésének előkészítése

A `p2_4c20_7_1_function_inventory.md` a jelenlegi sportolói webfelület 60 funkcióegységét, 17 oldalát, négy felhasználói folyamatát és 11 rendszerezendő pontját írja le. A működő, részleges és előkészített részek külön jelöltek. Minden funkcióhoz tartozik forrásfájl, előfeltétel, kimenet és következő lépés.

A kiadási csomag szerkeszthető Excel-leltárt is tartalmaz. A Funkciók lap E–H oszlopai a későbbi csoport, név, prioritás és saját megjegyzés számára üresek. Ez a kiadás a meglévő menüszerkezetet nem rendezi át.

## Ellenőrzés

`python tools/run_c20_7_1_checks.py --build`

A teljes backend planning regresszió 2061, a frontend regresszió 1181 tesztből áll. Az új lefedettség a két bank közötti kompatibilitást, az új és korábbi indításokat, mentést, újrapróbálást, befagyasztott ismételhetőségi utasításokat és a saját testsúlyos adatbevitelt ellenőrzi.
