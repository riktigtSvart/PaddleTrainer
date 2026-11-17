# C21.11 – Többnapos étrend és bevásárlólista

Első használható receptalapú táplálkozási modul a C21.10.21.1 után. A Táplálkozási opciók oldal és a Bevásárlás oldal ugyanazt a mentett étrendet és listát használja. A fejléc kosárikonja és a táplálkozási almenü közvetlen belépést ad.

## Használat

1. Válassz vegyes, halat engedő húsmentes, vegetáriánus vagy vegán étrendet.
2. Nézd át az allergéneket. A „Még nem néztem át” nem jelent allergénmentességet. Külön választható a „Nincs kizárandó allergén”, vagy megjelölhetők a kizárandó csoportok. Az összetevőnkénti kerülés ettől függetlenül állítható.
3. Add meg az ételenkénti legnagyobb elkészítési időt, a napi három vagy négy étkezést, az első napot, az 1–14 napos időszakot és az 1–8 főt.
4. Az **Étrend összeállítása** helyben készít tervezetet. A 28 receptből csak az étrendnek, az allergén- és alapanyagkizárásnak, az étkezéstípusnak és az időkeretnek megfelelő kerülhet bele. Ha nincs megfelelő recept, a rendszer jelzi, és nem lazítja fel a kizárásokat.
5. A napok kártyáin másik megfelelő étel és 0,5 / 1 / 1,5 / 2 adagszorzó választható. A szorzó személyenként értendő; az alapanyagok a teljes létszám mennyiségét mutatják. Az elkészítés és az alapanyaglista külön lenyitható.
6. A **Bevásárlólista** azonos alapanyagonként összevonja a teljes időszak szükségletét. Az otthoni készletet ugyanabban a mértékegységben vonja le, és a vásárolandó mennyiség legalább nulla. A darabos alapanyagok beszerzési mennyisége az összesítés és levonás után felfelé kerekül.
7. A készlet és a beszerzési pipák a **Módosítások mentése** gombbal együtt megőrizhetők. A lista másolható és nyomtatható. Az étrend módosítása törli a korábbi beszerzési pipákat; a készletadatokat megtartja.

Az étrend összeállítása, a nézetváltás, az ételcsere, az adagszorzás és a listaszámítás nem kér új hálózati adatot. A betöltés és a kifejezett mentés használja a helyi API-t.

A mennyiségeknél a megnevezett állapot számít: például száraz rizs, nyers hús vagy lecsöpögtetett hüvelyes. A bevásárlólista alapanyagmennyiségeket ad; nem bolti csomagméretet, árat vagy garantált készletet. A romlandó alapanyagoknál a tárolás, a fagyasztás és a csomagolás felhasználhatósági ideje külön figyelmet igényel.

## Az első változat határa

A 37 alapanyag és a 28 saját recept kiinduló adagokat ad. Ez szerkeszthető mintaétrend, nem személyes energiaszükségletből számított sportétrend vagy hiánytalan mikrotápanyag-ellátás igazolása. A testsúlycél és a testtömeg-előzmény továbbra is elérhető a táplálkozási oldalon; a mennyiségek még nem igazodnak automatikusan a céltömeghez vagy az edzésnap terheléséhez.

A szűrés a recept alapanyagadatait használja. A konkrét csomagolt termék összetevőit és a nyomokban jelenlévő allergéneket a címkén kell ellenőrizni. A receptkészlet általános háttérforrásai:

- WHO: [Healthy diet](https://www.who.int/news-room/fact-sheets/detail/healthy-diet), ellenőrizve 2026. november 16-án.
- EFSA: [Food allergens](https://www.efsa.europa.eu/enIE/safe2eat/food-allergens), az EU-ban jelölt 14 allergéncsoport és a címkeellenőrzés háttere.

Étkezési napló, személyes kalória-/makrotápanyag-cél, bolti kínálat és ároptimalizálás külön következő bővítés. A mentett étrend nem bizonyítja, hogy az étkezések megtörténtek. Jelenleg az aktuális étrend szerkeszthető; korábbi verziói az audit-előzményben megmaradnak, külön történeti böngészőfelület még nincs.

## Tárolás és ellenőrzés

- `GET /api/v1/planning/nutrition`: az alkalmazásban beállított saját fiók aktuális állapota és a verziózott receptkészlet.
- `POST /api/v1/planning/nutrition`: zárt kérés az étrendi preferenciákkal, az explicit ételválasztásokkal, a készlettel és a beszerzési jelölésekkel. Nincs szabad tulajdonos-paraméter.
- A meglévő `/api/goal-workflow/nutrition` proxy csak a pontos GET/POST útvonalat engedi, az eredeti origin-, JSON-, méret- és credentialvédelemmel.
- A szerver a vásárlási mennyiségeket függetlenül újraszámolja. A kliens ugyanezt a verziózott receptkészletből ellenőrzi, a teljes külső válasz újrahashelése önmagában nem tesz érvényessé megváltoztatott adagokat vagy listát.
- A készlet és mennyiségek tizedes szövegek. A Python Decimal, a kliens fix ezredes aritmetikát használ; a különböző alapanyagokat vagy mértékegységeket nem mossa össze.
- A `nutrition_workspace` auditfajta egy tranzakcióban menti a teljes állapotot, tulajdonoshoz és előző verzióhoz kötve. Nem kell új adatbázistábla vagy migráció. Meglévő mérést, testsúlycélt, edzést vagy tényleges étkezési adatot nem módosít.
- A böngésző a bizonytalan mentés teljes eredeti kérését őrzi. Elveszett válasz után ugyanaz az azonosító és kérés ellenőrizhető újra, új étrendpéldány nélkül. A korábbi kérés megismétlése nem állítja vissza egy későbbi verzió adatait.
- Másik ablakból érkező módosításnál a régi mentés elutasított, a piszkozat megmarad. Kifejezett gombbal átvehető a friss állapot a piszkozat megtartásával, majd az átnézett módosítás újra menthető.
- A félbehagyott tizedes mennyiség a mezőben marad, a táblázat használható marad; a mentés és az export a mennyiség befejezéséig tiltott.
- A `nutrition_catalog_v0_1.json` kiadott, rögzített receptverzió. Későbbi katalógusbővítéshez új verzió és a régi verzió visszaolvashatósága szükséges; a kiadott alapanyagokat vagy mennyiségeket nem szabad észrevétlenül átírni.

## Validálás

`python tools/run_c21_11_checks.py`: 65 releváns backendteszt (a korábbi közös testtömeg- és célszolgáltatással), 1895 frontendteszt, Next típuskészítés, TypeScript, ESLint és éles build.

Külön valódi FastAPI + React StrictMode próba végigment az allergénlista átnézésén, a vegán/gluténszűrésen, a háromnapos kétfős összeállításon, helyi ételcserén és adagszorzáson, a félbehagyott tizedes bevitel megtartásán, a készlet és a pipák mentésén, másik oldalon történő újranyitáson, az elveszett válasz pontos újrapróbálásán és a másik ablakból érkező változás kezelésén. Natív Windows- és képi böngészőpróba nem történt ebben a környezetben.
