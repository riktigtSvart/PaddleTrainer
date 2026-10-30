# P2.4C14 — személyes tapasztalatok leíró áttekintése

A **Fejlődés → Személyes tapasztalat** nézet (`/personal-response`) a C12
személyes bemeneteit jeleníti meg. A C13 által bekötött teljesítésekre és a
kiválasztott visszajelzési változatokra épül. A Célok és mérések nézet külön
fülön megmarad. Nincs új menüpont a fő navigációban.

## A felhasználó számára

- Összesített edzés-, visszajelzési alkalom-, számszerű és meg nem adott
  válaszszám. Egy visszajelzés öt válasza nem öt független edzés.
- Az öt saját 0–10 pontos mutató: érzékelt terhelés, fáradtság,
  izomfájdalom, regeneráltság, energiaszint.
- Külön környezet minden sportág, válaszidőzítés, mutató és mértékegység
  szerint. Az edzés utáni válasz nem olvad össze a másnap reggelivel.
- Pontdiagram az időben, illetve az ismert edzésidőhöz kapcsolva. Vízszintes
  segédvonalak, megmaradó nullák, egérrel/billentyűzettel elérhető
  pontfeliratok és az edzésekre vezető hivatkozások.
- A hiányzó érték nem nulla. Nincs interpoláció, regressziós vonal,
  korrelációs együttható, változásból következtetett fittség vagy hatásállítás.
- A táblázatban megfigyelési idő, adatként való elérhetőség, párosítható
  edzésidő és a köztes terhelések ismert/hiányzó kontextusa szerepel.
- A dátumok a profil időzónájában jelennek meg. Az alapnézet a legutóbbi
  90×24 órát kéri; egyedi, legfeljebb 366 napos naptári időszak is kérhető.

A nézet csak a már bekötött válaszokat mutatja. Az üres állapot nem állítja,
hogy nem történt edzés vagy nincs még bekötetlen visszajelzés. A napirendhez
vezet, az edzés saját Tanulási kapcsolat részének ellenőrzését javasolva.
Az Adatok újraolvasása kizárólag GET; nem kapcsol be bizonyítékot, nem fagyaszt
forrást és nem indít szolgáltatói szinkronizálást.

## Kétféle idő megőrzése és a korábbi dátumhiba javítása

A meglévő `GET /planning/calendar/learning-inputs` válasz additív mezői:
`timezone_name`, `response_window_end_at`, `selection_scope=response_observed_at`.
A séma változatlanul `feedback-personal-inputs-v0.1`.

A korábbi egyedi múltbeli dátumkérés a múltbeli időablak végét `as_of`-ként,
a mostani időt pedig információs cutoffként adta a történeti összesítőnek.
Ez megsértette a `cutoff <= as_of` invariánst, így egy érvényes időszak is
hibára futhatott.

Most az összesítés állapotideje és cutoffja egyaránt a kérés rögzített mostani
időpontja. A válaszok megfigyelési dátumablaka külön szűrő. Először a cutoff
szerint kiválasztjuk a legutolsó ismert visszajelzési változatot; csak utána
szűrünk a megfigyelési dátumára. A szűrés nem éleszthet fel lecserélt értéket.
Az utólag bekötött régi válasz így megjelenhet egy régi naptári nézetben, de a
valós későbbi elérhetőségi ideje megmarad. Ez jelenlegi tudás szerinti
visszatekintés, nem korábbi információs állapot újrajátszása.

A múltbeli zárónap utáni helyi éjfél kizáró határ. A mostani időre vágott
ablaknál a cutoffval egyező pillanat megengedett. A jövőben kezdődő kérés
422. Az időablak végét az alkalmazási összesítő opcionális
`observation_end_at` argumentuma kezeli; a korábbi hívók alapműködése marad.
Az edzésbizonyítékok megmaradnak az időbeli kapcsolódás és a köztes terhelések
értékeléséhez; a visszajelzések szűrése nem törli a tartós bizonyítékokat.

## Adathatárok és ellenőrizhetőség

A kliens azonos sportolót, támogatott sémát, ismert időzónát, időrendet,
forrás- és megfigyelésreferenciákat, pontos kontextusokat, mértékegységeket,
párszámokat és a magasabb következtetési jogosultságok hamis értékét kéri.
A tartalmi hash-eket referenciaegyezésként ellenőrzi; nem állítja az összes
belső domainobjektum kriptográfiai újraellenőrzését a böngészőben. A források
tartalmi hash-ellenőrzése a meglévő szerveroldali bizonyítéklánc része.

Tízezernél több megfigyelést a nézet nem fogad el észrevétlen csonkítással.
Kontextusonként 500 pont fölött rövidebb ablakot kér a grafikonhoz; az összes
adat a 25 soros lapozható táblázatban marad. Ismeretlen korlátozási kód
szövegként, escape-elve látszik. Hiba nem változhat üres, sikeres eredménnyé.

Nincs migráció, új függőség, modellillesztés, személyes hatásbecslés,
automatikus terhelés- vagy tervmódosítás. A részleges/hiányzó lefedettség
látható marad. A hosszabb edzésidő önmagában nem élettani terhelési mérték.

## Validáció

Izolált Python HTTP-tesztek ellenőrzik az írásmentes beolvasást, a profil
időzónáját, a múltbeli dátumszűrést később megismert adatokkal, a lecserélt
válaszok kizárását és a hibás/jövőbeli ablakokat. A frontend ugyanazokat a
valódi, szintetikus Python HTTP-válaszokat olvassa fixture-ként. A szerződés-,
SSR- és DOM-próbák a nullát/hiányt, kontextusokat, pontfeliratokat,
edzéshivatkozásokat, kizárólagos GET-forgalmat, betöltési hibákat és megszakított
kéréseket is fedik. Nincs élő szolgáltatói vagy alkalmazásadatbázis-hozzáférés.
