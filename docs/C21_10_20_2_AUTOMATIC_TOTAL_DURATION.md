# C21.10.20.2 – Saját edzés teljes idejének automatikus igazítása

Ha a megadott edzésszakaszok összes ideje nagyobb a teljes edzésidőnél, a szerkesztő automatikusan megemeli a teljes időt. Az összesítés az egyes szakaszok ismétlésszámát is figyelembe veszi. Példa: 10 perc bemelegítés + 3 × 12 perc futás + 2 × 2 perc pihenő + 5 perc levezetés = **55 perc**. Az 53 perces teljes idő ekkor 55 percre változik.

A módosítás azonnal látszik a teljes edzésidő mezőjében, rövid tájékoztatással. A mentés és a mező elhagyása is elvégzi az ellenőrzést, ezért Enterrel vagy előzetes fókuszváltás nélkül is a helyes összidő kerül a kérésbe. Ehhez nem kell még egyszer megnyomni a Mentés gombot.

- A korábban megadott nagyobb teljes időt megtartjuk: abban külön meg nem nevezett pihenő, átállás vagy időalap nélkül megadott rész is lehet.
- A szakaszok időtartama és ismétlése, a gyakorlatok, súlyok és sorozatok változatlanok maradnak. A javítás a teljes időt igazítja hozzájuk.
- Ismeretlen idejű, például csak távolsággal megadott részhez nem találunk ki időt. Az ismert időtartamok összege a teljes idő alsó határa.
- Az érvénytelen szakaszértékek és a 24 órát meghaladó összes idő továbbra is javítást igényelnek.

## Az ismert időablak figyelembevétele

A szerkesztő a naptár már betöltött napirendi adatait használja; a számolás nem indít új hálózati kérést, tervezést vagy Polar-lekérést.

Az automatikus emelésnél ellenőrizzük az adott kezdéstől hátralévő, egybefüggő időt, az időablak perckeretét, a napi keretet és az ismert sportág-/helyszínválasztást. Külön ablakok idejét nem adjuk össze, és az elfoglaltsággal megszakított részeken nem nyújtjuk át a munkát. Éjfélen átnyúló ablak és óraátállítás is kezelhető; az ismétlődő helyi időt továbbra is egyértelműsíteni kell.

Ha például 55 percnyi szakaszhoz a választott kezdéstől már csak 50 perc marad, nem emeljük át a teljes időt ezen a korláton. A jelzés konkrétan kiírja a szükséges és a rendelkezésre álló időt. Korábbi kezdést választva vagy rövidítve a szakaszokat ismét használható az automatikus igazítás. A heti ismétlések közül a betöltött dátumokra ismert kereteket is figyelembe vesszük.

A nem betöltött vagy ismeretlen napi keret nem jelent nulla elérhető időt; ilyenkor a saját terv korábbi szabad szerkeszthetősége marad érvényben. A betöltött lehetőségek ellenőrzése nem általános, friss szerveroldali jogosultsági vagy tervezési felülvizsgálat. A meglévő naptári ütközésjelzések továbbra is használhatók.

## Ellenőrzés

A változás csak frontendkódot, frontendteszteket és a frontend-lint fájllistáját érinti. Nincs backend- vagy adatbázis-változás. A C21.10.20 meglévő kapuja a `--frontend-only` kapcsolóval futtatható.

A tesztek ellenőrzik az ismétlésekkel számolt 53 → 55 perces igazítást, a nagyobb kézi keret megőrzését, a pontos másodperceket, az ismeretlen adatokat, az időablak hátralévő részét, a kereteket, az egymást kizáró lehetőségeket, az éjszakai ablakot és az óraátállítást. Valódi FastAPI + React StrictMode próbában a mentett edzés teljes ideje 3300 másodperc, a szakaszok ismétlései változatlanok. A túl rövid ismert ablak megakadályozza az elégtelen idővel történő küldést; korábbi kezdéssel a mentés sikerül.
