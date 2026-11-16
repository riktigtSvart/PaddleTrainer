# C21.2 — Naptár és almenük

A frissítés C21 vagy C21.1 után alkalmazható. A backend, az adatbázis és a mentett edzések adatformátuma nem változik.

## Felület

- A bal oldali aktív főmenü alatt nyílnak meg az almenük. A tervezési munkalap hat lépése innen is elérhető; a lépések közötti váltás megőrzi a beírt, még nem mentett adatokat.
- A naptár almenüjébe került az edzésnapló és a személyes válaszadatok. A naptár fölötti külön hivatkozássor megszűnt.
- Az 1 nap / 1 hét / 4 hét / Áttekintés közvetlen gomb. A naptárrétegek jelölőnégyzetei állandó, többoszlopos blokkban látszanak.
- Az 1 napos, 1 hetes és 4 hetes rács a vezérlők után megmaradó képernyőmagassághoz igazodik, átméretezéskor újraszámolva. Nincs saját belső görgetősávja. A tevékenységlista alatta, a fő tartalom görgetésével érhető el. Nagyon alacsony ablakban 230 px marad a rács legkisebb magassága, ezért ilyenkor külső görgetésre szükség lehet.
- A négyhetes nézet a cellába férő eseményeket mutatja. A további elemek számát külön gomb jelzi; ezzel a teljes nap nyitható meg. A napgomb hozzáférhető neve az összes látható réteg eseményszámát tartalmazza.
- Keskeny képernyőn a „Menü mérete” gombbal az almenüket is tartalmazó oldalsáv nyitható meg.

## Idősávkezelés

| Művelet | Elérés |
| --- | --- |
| Új idősáv | Dupla kattintás a nap üres részén. Órás nézetben a kattintás helyének megfelelő, ötperces lépésre igazított kezdés kerül az új szerkesztőbe. |
| Új idősáv, szerkesztés, elhagyás | Jobb kattintással nyíló helyi menü. |
| Billentyűzet | A naposzlop fókuszba helyezése után Enter, Szóköz vagy helyimenü-billentyű; a menüben fel/le, Home/End és Escape. |
| Meglévő idősáv | A korábbi kattintásos szerkesztés, húzás és átméretezés megmarad. |

A helyi menüben az elhagyás előbb a törlés előnézetét nyitja meg. A végleges mentéshez külön gomb tartozik. Edzés vagy teljesítés helyi menüjéből az adatlap nyitható meg; ez a művelet nem törli az edzést.

## Visszavonás és Újra

A két gomb a legutóbbi támogatott napirendi módosítást vagy edzésáthelyezést kezeli. A visszaállítás is előnézetből jóváhagyott új revízió. Az Újra gomb a legutóbb visszavont módosítást alkalmazza újból; új szerkesztés vagy eltérő aktuális mentés után a régi visszavonás nem használható. A böngészőben tárolt előzmény újranyitás után is ellenőrzött marad. A függő kérések pontos bájtjai, tulajdonosa és visszaküldési módja megmaradnak.

## Ellenőrzés

`python tools/run_c21_2_checks.py` futtatja a teljes frontend regressziót, a Next route típusgenerálását, a TypeScriptet, az érintett felület lintjét és a production buildet. Nem igényel új függőséget vagy adatbázis-migrációt.

A fejlesztés során a valódi API-val végigfutott az idősáv elhagyása → mentése → visszavonása → felület újranyitása → újbóli alkalmazása, továbbá a tervezett edzés áthelyezése → visszavonása → újranyitása → újbóli alkalmazása. A navigáció és az idősávkezelés DOM-eseményei is ellenőrzöttek. A helyi előnézet böngészős megnyitását a futtatókörnyezet biztonsági szabálya blokkolta, ezért valódi képernyőképes elrendezés-ellenőrzés nem készült.
