# P2.4C7R1 — párosítási szöveg és szolgáltatói hibajelzés

A bemenet a 2026-10-25T11:17:30Z időpontban gyűjtött, 949 forrásfájlos C7 munkafa.
A main és a várt origin/main alapja 3ca1165cc9d21b6b83a3b1e95090261d49524173.
A bemeneti 93 nem stage-elt változás a csomag ellenőrzött előzménye.

## Javított viselkedés

Az edzés részletezője eddig minden olyan teljesítést spontánnak nevezett,
amelyhez nem volt tárolt edzéstervkapcsolat. A kapcsolat hiánya ezt nem bizonyítja:
a terv még hiányozhat az importból, vagy a terv–teljesítés párosítása nem történt meg.
Most a szöveg azt mondja, hogy a teljesítés még nincs tervhez párosítva.
A naptár megnyitott részletezője ugyanezt jelzi, ha planned_workout_id nincs.

A szolgáltatói HTTP-hibáknál az új futások megőrzik a pontos státuszt az
error_code mezőben, például DATA_SYNC_PROVIDER_HTTP_400 vagy
DATA_SYNC_PROVIDER_HTTP_500. A 401, 403 és 429 megtartja korábbi külön jelentését
(újraengedélyezés, további hozzáférés, lekérési korlát).
Nem ellenőrizhető vagy hiányzó HTTP-státusz továbbra is a korábbi általános kódot kapja.
A nyers szolgáltatói hibaüzenet, token és hitelesítési fejléc nem kerül a válaszba.

A szinkronpanel kibontott eredménye adatfajtánként is megjeleníti a hiba magyarázatát.
Így a teljesítések sikeres átvétele és a tervek hibája külön olvasható.
A már rögzített korábbi futások változatlan tartalomhash-sel olvashatók maradnak;
a korábbi általános hibakód nem alakul át utólag kitalált HTTP-státusszá.

## Hatókör és következő ellenőrzés

Ez a csomag a fenti igazolt megjelenítési és hibavisszajelzési hibát javítja.
A konkrét éles tervlekérés elutasításának oka még nincs igazolva:
ehhez az érintett /training-target/calendar-targets kérés POLAR STATUS sora,
és szükség esetén a Polar eredeti errorMessage válasza szükséges.
A csomag nem állítja, hogy a Polar-tervek éles átvétele már sikeres.

A dokumentált fromDate és toDate lekérési paraméterek változatlanok.
Nincs találomra bevezetett alternatív paraméternév, dátumtartomány vagy szolgáltatói újrapróbálás.
Elsődleges forrás: https://www.polar.com/polar-api-v4/
Training targets fejezet, ellenőrizve 2026-10-25.

Ez a változás nem hoz létre új terv–teljesítés párosításokat.
A későbbi párosításnál a szolgáltató konkrét trainingTarget.id hivatkozása,
a sportolói tulajdon és az egyértelmű egyezés ellenőrizendő.
A dátum vagy sportág hasonlósága önmagában nem igazol kapcsolatot.
Nincs edzésterv- vagy teljesítési státuszmódosítás, új DB-migráció vagy függőség.

## Ellenőrzés

A célzott backendtesztek a hibás tervlekérés HTTP-státuszának tartós megőrzését,
a sikeresen átvett teljesítések megtartását, az ismétlés idempotenciáját,
a privát szolgáltatói szöveg visszatartását és a régi futások olvashatóságát vizsgálják.
A frontendtesztek a HTTP-kategóriák és a külön engedélyezési/korlátozási üzenetek
jelentését ellenőrzik. A kapu a korábbi backend- és frontendteszteket,
a típusgenerálást, teljes TypeScript-ellenőrzést, az érintett fájlok ESLintjét
és a production buildet futtatja.

A tesztek saját SQLite-adatbázisokat és szintetikus szolgáltatói válaszokat használnak.
Az ellenőrzés nem ér el éles Polar-fiókot vagy alkalmazás-adatbázist.
A részletes eredmények a letölthető csomag VALIDATION.json fájljában vannak.
