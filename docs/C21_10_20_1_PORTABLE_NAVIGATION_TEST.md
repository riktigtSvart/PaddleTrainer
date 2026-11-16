# C21.10.20.1 – Gépfüggetlen nézetváltási ellenőrzés

A C21.10.20 telepítésénél a 162 backendteszt és a sajátedzés-szerkesztő tesztjei sikeresek voltak. A kapu egy korábbi, C21.10.19-ből származó frontendteszt rögzített időhatárán állt meg: a teszt 40 egymás utáni, már betöltött hét/nap nézetváltásra összesen kevesebb mint 1000 ms-ot engedett. Ez a feltétel a párhuzamos tesztfuttatás és a gép terhelése miatt akkor is elbukhatott, ha nem történt új hálózati kérés.

A javítás kizárólag a tesztet és ezt a leírást érinti. Az alkalmazás, a backend, a gyorsítótár és az adatbázis működése változatlan.

Az új ellenőrzés:

- először betölti a tágabb naptári időszakot és a napirendet, pontosan két olvasással;
- ezután hibát dob minden újabb hálózati kísérletnél;
- 40 ismételt hét/nap váltásnál ellenőrzi a kért dátumhatárokat, az edzés- és teljesítésazonosítókat, a napirendi eseményeket és az edzéslehetőségeket;
- végül ismét ellenőrzi, hogy az olvasások száma pontosan kettő maradt;
- az eltelt időt tájékoztató adatként kiírja, de nem használ gépsebességtől függő sikerfeltételt.

A C21.10.20-ra alkalmazott javítás után elegendő:

```powershell
& .\.venv\Scripts\python.exe .\tools\run_c21_10_20_checks.py --frontend-only
```

A korábban sikeres, változatlan backendteszteket nem kell újrafuttatni. A parancs a frontend regresszióit, a Next típuskészítést, a TypeScriptet, az ESLintet és az éles buildet is lefuttatja.
