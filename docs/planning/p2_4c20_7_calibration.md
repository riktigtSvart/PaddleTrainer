# C20.7 — Sportági ajánlás, felmérési utasítás és tartós eredmény

## A sportoló folyamata

A `/strength-assessment` oldalon megmarad a helyszín és az ismert gyakorlatok kiválasztása. A területekhez sportági ajánlás és indoklás kapcsolódik. A fő sportág vezeti a sorrendet, a kiegészítő sportágak is szerepet kapnak. Az ajánló a mentett jártasságot, panaszmentességet, helyszíni lehetőséget és korábbi referenciát használja; nem állít személyes izomgyengeséget egy hiányzó mérésből. Nem választ automatikusan gyakorlatot a sportoló helyett. A szöveges cél látható körülmény, nem géppel értelmezett képességdiagnózis.

Az első alkalomra 1–2 gyakorlat is elegendő. A kiválasztott gyakorlatok hétlépéses felmérési menete indítás előtt is megnyitható. Az indítás és a rövid bemelegítés után a konkrét utasítás és az eredménymezők együtt jelennek meg. A sportolónak nem kell külön referenciasorozat-gombbal előkeresnie az űrlapot.

Egy próba eredménye az **Elvégzett próba rögzítése és mentése** gombbal kerül tartós ellenőrzőpontba. Ugyanitt adható meg újabb, már elvégzett próba. A protokoll előírhat két próbát, miközben a tárolás megőrzi a tényleges többletadatot is. Egy korábban elvégzett 23-as sorozat nem alakul át 12-vé. A be nem fejezett űrlapértékek piszkozatként megőrizhetők, és lezárás előtt elvégzettként rögzítendők vagy elvetendők.

A felmérés szüneteltethető, újratöltés után folytatható. A már mentett eredmények az oldalon külön megnyithatók. Az órás felvétel a teljes alkalomhoz kapcsolódik; a gyakorlatok adatait mindkét naplózási módban a sportoló adja meg. A lezárás frissíti a mentett kiindulóadatokat, így a következő alkalom nem az előző, elavult mentési alapra indul.

## Lefedettség

A korábban egyeztetett v0.3 gyűjtemény 120 katalógusbejegyzése közül 115 erősítő jellegű gyakorlat választható az öt meglévő terület alatt. Az öt ergométer külön sportági protokollhoz tartozik, és nem kap általános erőfelmérési sorozatot. A meglévő lista első elemei és a sportoló választásai megmaradnak; a lista további eszköz- és gyakorlatváltozatokkal bővül.

| Mérési típus | Rögzített eredmény |
|---|---|
| Súlyos vagy saját testsúlyos dinamikus gyakorlat | Tényleges ismétlés, terhelés vagy változat, tartalék |
| Rásegítés vagy szalag | A segítség vagy szalag azonosítása és a tényleges teljesítés |
| Kitartás | Tényleges másodperc, változat és befejezési ok |
| Cipelés | Ténylegesen mért táv és menetidő, hordott tömeg, körülmények |
| Dobás és ugrás | Különálló próbák; csak valóban mért táv, magasság vagy megnevezett szenzoradat |
| Kontrollált gyakorlat vagy rövid lendítés | Végrehajtási referencia; nem automatikus maximális erő- vagy teljesítményérték |

Gyakorlatonkénti beállítás, saját mérési oldal, a befejezés oka és a tényleges pihenő külön adat. A pihenőmérő a valóban eltelt időt csak kifejezett beírással adja át; az előírt időt nem másolja be megfigyelésként. A hiányzó érték null marad, a valódi nulla külön érték.

A tárcsasúlyos gép bal, jobb vagy közös tüskéjére tett tömegek külön rögzíthetők. A gép ismeretlen üres ellenállását nem adjuk hozzá. A rúdvégből végzett gyakorlat rúdja és tárcsái szintén külön adatok. Ezek nem válnak általános, eszközök között átvihető kilogrammterheléssé.

## Verziózás és megőrzés

- A korábbi `guided-strength-session-v0.1` kérések és nyugták adatszerkezete változatlan marad.
- Az új alkalom `guided-strength-session-v0.2`, `strength-calibration-v0.3` protokollhivatkozással.
- Az első mentés befagyasztja a kiválasztott gyakorlatok pontos protokollját. Aktív alkalom közben a protokoll és a mérési cél nem cserélhető le.
- Egy alkalomhoz több mérési próba, egy próbához saját azonosító, sorszám, dátum és oldal tartozik.
- A normális erőkifejtés és a 0–1 jelzett ismétléstartalék önmagában nem jelöl egészségi állapotromlást. A panasz és a kontrollromlás külön megállási ok.
- A nyers mérések az alkalom verziózott, tulajdonoshoz kötött naplójában maradnak. Az ismétléses és tartásos adatok a kezdeti felmérésbe is átkerülhetnek; külön oldal vagy beállítás külön bejegyzést kap.
- A lezárás egy tranzakcióban rögzíti az alkalmat, az edzésnapló-kapcsolatot és az alkalmazható felmérési adatokat. Hiba esetén visszagörget, azonos kérés újrapróbálásakor nem hoz létre új alkalmat.
- A függő kérés pontos bájtjai megmaradnak. Újratöltés nem küld újra automatikusan.
- Az előzményolvasás egyetlen, kötött `GET .../guided-strength/revisions/{request_uuid}` művelet, a konfigurált sportoló nevében.

Pusztán bővülő gyakorlatjegyzék mellett a változatlan, áttekintett válaszok újragépelése nem szükséges. Ehhez a profil-, helyszín-, katalógus-, időzóna- és programforrásnak egyeznie kell; a régi sportmodulok és területjelentések nem változhatnak, a gyakorlatlisták csak bővülhetnek. A felmérés tényleges lezárása már a friss forrásokra kötött új változatot menti. Valódi profil- vagy helyszínváltozás továbbra is ellenőrzést igényel.

## Az ismételt sorozatok módja

Már ismert terheléshez külön választható az **Ismételt sorozatok megfigyelése**. Ez a v0.3 anyagban egyeztetett második lépcső: legfeljebb nyolc ismétlés, körülbelül legalább három ismétlésnyi tartalék, két azonos feladat és három perc célpihenő. A tényleges értékek megmaradnak. Kitartásra, cipelésre és robbanékony próbára ez a dinamikus menet nem alkalmazható.

A megfigyelt két sorozat nem bizonyít maximális vagy optimális sorozatszámot. Nincs automatikus kapacitásgörbe, erőállóképességi minősítés vagy regenerációs modell.

## A tervező kapcsolata

A felmérősorozat és a következő edzésadag külön adat. Az új kalibrálásból a következő, nyílt kezdő termékszabály készíthet javaslatot:

1. Dinamikus, az adott helyszínen ismert és panaszmentes gyakorlat, egyértelmű oldal és terhelés.
2. Legalább négy tényleges, stabil ismétlés, legalább két jelzett ismétlésnyi tartalékkal és ismert, megfelelő befejezési okkal.
3. Gyakorlat-/oldalreferenciánként **egy** kezdő sorozat, ugyanazzal a terheléssel; az ismétléscél a megfigyeltnél kettővel kevesebb, legfeljebb nyolc.
4. A következő edzésen a cél legalább három szabályos ismétlésnyi tartalék és három perc pihenő; a sportoló korábban megállhat. A tervezett tartalék nem válik visszamenőleg mért tartalékká.

A tervező az eredeti mérést és a levezetését is befagyasztja. A böngésző ellenőrzi a tulajdonost, a pontos forrást, az időbeli határt és a levezetést. Egy utólag megemelt ismétlésszám vagy elhagyott mérési bizonyíték nem fogadható el pusztán újraszámolt külső hash-sel.

Ez **felülvizsgálható kezdő alkalmazásszabály**, nem személyre illesztett fiziológiai modell. Nincs automatikus súlyemelés, hozzáadott sorozat, 1RM-becslés vagy teljes fejlesztési eredményre vonatkozó állítás. A meglévő cél-, időkeret-, helyszín- és állapotfeltételek továbbra is érvényesek; az új edzésterv külön áttekinthető és elfogadható.

Az ismeretlen tartalék, a hiányos beállítás vagy egy kontrollált végrehajtási próba továbbra is menthető, miközben nem válik ebből a kezdő szabályból automatikus edzésadaggá. A rúdvég- és az eszközváltozattól függő speciális referencia is megmarad; ezekből ez a változat nem készít általánosított kezdő terhelést.

## Ellenőrzés

- Valódi HTTP-tesztek: indítás korábbi referencia nélkül, több próba, 23 ismétlés, ismeretlen tartalék és valódi nulla, panasz elkülönítése, tranzakciós visszagörgetés, azonos újrapróbálás, saját előzmények és tervezőforrás.
- A natív mérési egységek és a tervezett határokat meghaladó tényleges adatok külön ellenőrzöttek.
- A Python által előállított új nyugtákat és tervezési javaslatot a böngésző szerződésellenőrzője is elfogadja; módosított források és tervezett ismétlések elutasítandók.
- A DOM-próba végigjárja a választást, a bemelegítést, a közvetlen adatbevitelt, az ellenőrzőpontot, az újratöltést, a második próbát, a lezárást, a bizonytalan mentés pontos újrapróbálását és az előzmények megnyitását.
- A teljes kapu: `python tools/run_c20_7_checks.py --build`.

A termékprotokoll szakmai támpontjai és saját korlátai a korábban átadott v0.3 gyűjteményben szerepelnek. A szoftvertesztek a megvalósítást ellenőrzik; nem jelentenek klinikai vagy sportélettani validálást.
