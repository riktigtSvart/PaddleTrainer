# C21.10.21 – Óra:perc:másodperc és összekapcsolt résztáv/pihenő

## Szerkesztés

A sajátedzés-szerkesztő minden időtartamát `HH:MM:SS` alakban lehet megadni: teljes edzésidő, egy ismétlés ideje, köztes pihenő, erősítő sorozatok közötti pihenő és időtartás. Például `00:00:45`, `00:01:30`, `01:15:00`. Ez időtartammező, nem napszaki idő: a `24:00:00` is megadható ott, ahol a korábbi határ 24 óra volt. A munkaszakaszok másodpercnyi pontossággal rögzíthetők, tizedesperces átszámítás nélkül.

Az üres opcionális mező nem nulla. A még gépelt vagy hibás alak (például `00:` vagy `00:01:60`) megmarad a mezőben, de nem menthető véletlenül nulla időként. A teljes edzésidő továbbra is **egy perc és 24 óra közötti** lehet: `00:01:00`–`24:00:00`. A különböző gyakorlati mezők korábbi alsó és felső határai nem változnak.

## Egy blokk: munka és köztes pihenő

Egy szakasznál megadható az ismétlésszám és a **Pihenő az ismétlések között**. A `3 × 00:12:00 / 00:02:00` jelentése:

1. munka `00:12:00`;
2. pihenő `00:02:00`;
3. munka `00:12:00`;
4. pihenő `00:02:00`;
5. munka `00:12:00`.

Összesen `00:40:00`. Az utolsó ismétlés után nincs automatikus pihenő. A szerkesztő azonnal megmutatja a köztes pihenők számát és a blokk összes idejét. A bemelegítés, levezetés és esetleges külön, utolsó ismétlés utáni pihenő külön szakaszként hozzáadható.

Ha egy ismétlés van, nincs köztes pihenő. A `00:00:00` pihenő megszakítás nélküli ismétlést jelent. Csak távolsággal megadott munkánál a munka idejét továbbra sem találjuk ki; az ismert pihenőidő beleszámít a teljes idő alsó határába.

A teljes idő automatikus emelése az `ismétlések × munkaidő + (ismétlések − 1) × pihenő` összeggel számol. A nagyobb, külön megadott teljes keretet továbbra is megtartja. Az ismert naptári időablak vizsgálata megmarad, új háttértervezés vagy adatlekérés nélkül.

## Megjelenítés és régi adatok

A naptári időtartamok, a saját edzés részletei, a teljes edzésadatlap számított időmezői és az automatikus edzésutasítások strukturált időtartamai is `HH:MM:SS` formátumot használnak. A rögzített eredeti címek, leírások és felmérési forrásszövegek változatlanok; a napszaki naptártengely nem időtartammező.

A korábban külön felvett `3 × 12 perc munka` és `3 × 2 perc pihenő` nem változik át magától két pihenővé: az eredetileg megadott 42 perc és sorrend megmarad. Az új párosításhoz a munka szakaszánál kell megadni a köztes pihenőt; a már külön szereplő pihenőt ilyenkor felhasználói szerkesztéssel lehet elhagyni. Korábbi mentett edzéseket és bizonylatokat a frissítés nem ír át.

## Tárolás és ellenőrzés

Az API továbbra is egész másodperceket fogad, a felület alakítja át a `HH:MM:SS` bevitelt. A recept új, opcionális `recovery_duration_sec` mezője az ismétlések közötti pihenő. A tényleges edzésblokkok helyes munka–pihenő sorrendben, az utolsó pihenő nélkül mentődnek; a szerkesztő receptje egyetlen csoportosított szakasz marad. A recept visszanyitható, módosítható és másolható. A kibontás legfeljebb 1000 tényleges blokkot készíthet egy alkalomhoz, hogy egy véletlen többszörözés ne hozzon létre korlátlan adatmennyiséget.

A korábbi bizonylatok olvasása a hiányzó új mezőt értelmezi üresként, de az eredeti JSON-t és tartalmi lenyomatot változatlanul hagyja. Az idempotens újrapróbálás régi bizonylattal is működik; új, eltérő pihenő nem írható bele egy már elmentett kérésazonosítóval. A lezárt és teljesített edzések védelme megmarad. Nincs adatbázis-migráció.

Az új tesztek valódi API-válaszokon ellenőrzik a 3 munka / 2 pihenő sorrendet, a pontos másodperceket, az 1 ismétlést és a nulla pihenőt, a módosítást/másolást, a régi külön pihenők változatlanságát és egy tényleges, a változtatás előtt rögzített bizonylat bájtonkénti megőrzését. A React StrictMode + FastAPI próba a részben beírt mezőt, az érvénytelen alak miatti írásmentes elutasítást, a mentést és a másodpercnyi részleteket is végigpróbálja.

```powershell
& .\.venv\Scripts\python.exe .\tools\run_c21_10_21_checks.py
```

Ebben a frissítésben az API is változik: a normál kaput kell futtatni, majd az API-t és a frontendet egyaránt újraindítani.
