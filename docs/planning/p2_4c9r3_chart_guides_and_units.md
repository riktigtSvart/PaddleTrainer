# P2.4C9R3 – Grafikonbeosztás, pulzuszónák és sebességegységek

A részletező a tárolt mintasorok mellé kerek értékű, sűrűbb vízszintes beosztást
és közös idővonalakat rajzol. Az iram beosztása továbbra is perc:másodperc/km.
A kurzor és a minták forrásindexe, a hiányok, az időbeli felbontás és a nagyítás
nem változik a megjelenítési egységek váltásakor.

## Sebesség

Az edzés fejlécében a **Sebesség egysége** mező `km/h`, `m/s` vagy `knots` lehet.
Az átlag, maximum, grafikonbeosztás, kurzor és mintatáblázat együtt vált.
A böngésző megjegyzi a választást; tiltott tárhely mellett az aktuális látogatás
alatt használható. A tárolt forrásadat km/h marad. Az átszámítás osztói rendre
1, 3,6 és 1,852. A nulla továbbra is nulla, a hiányzó adat továbbra is hiányzik.
Az iram mindig a forrássebességből számolt perc/km, egységváltástól függetlenül.

## Pulzus és tervcél

A Polar edzéshez tárolt `exercises[].zones[]` / `ZONE_TYPE_HEART_RATE` csoportjának
öt, forrásbeli sorrendű zónája jelenik meg, az eredeti `lowerLimit` és
`higherLimit` értékekkel, bpm egységben. A megjelenítés az adott edzésrész saját
pillanatképét használja, így több részt tartalmazó edzésben sem keveri őket.
A részletező megadja a pontos forrásútvonalat is. Hiányos, átfedő, átrendezett
vagy többértelmű definícióból nem nevez el Z1–Z5 zónákat.

A kapcsolt terv levélblokkjaiban megadott `HEART_RATE_ZONES` / `HR_ZONE` célok
Z1–Z5 számai ezekhez a határokhoz kapcsolódnak. A `HR_BPM` cél közvetlen bpm
határként használható. A százalékos vagy szabad szöveges cél nem lesz automatikus
zónahatár. A vezérlőben a konkrét tervezett blokk választható; alapból az első
használható WORK blokk, ennek hiányában az első cél látszik. A szülő ismétlődő
konténer nem jelenik meg még egy független célként.

A zónák halvány háttérsávok; a kiválasztott cél erősebb sávot, szaggatott
határvonalakat és külön bpm-feliratokat kap. A skála a mért minták és a választott
cél határait is tartalmazza. A cél kikapcsolható, a zónák megmaradnak.
Ez vizuális referencia: nem minősíti a teljesítést, nem állítja, hogy a blokk
mikor történt meg a mintasorban, és nem számít időt a célzónában.

## Zónák letöltése és kompatibilitás

A normál `session_details` szinkron most `statistics`, `samples`, `zones`
funkciókat kér egy napra. A korábbi, két funkcióra érvényes tartós lekérési
jelölők továbbra is ellenőrizhetők, de egy új kérés egyszer felfrissíti őket a
bővített körre. A korábbi kérésazonosító ismétlése a régi, változatlan nyugtát
adja, adatátvétel nélkül. Az új jelölő ugyanazt a forrásverziót újra felhasználja.
Az ötnapos adagkorlát és a legutóbbival kezdődő folytatás megmarad.

A native nézetben korábban tárolt zónák hozzáadódnak a preferált mintanézethez;
eltérő meglévő adat felülírása helyett továbbra is forrásütközés keletkezik.
A korábbi natív nyers adatok megmaradnak. A mért idő, táv, kalória és párosítás
nem változik. A részletek olvasása és az egységváltás nem indít szolgáltatói kérést.

Ha a zónahatár nincs az edzéshez tárolva, a bpm-beosztás továbbra is használható;
a Z2–Z3 cél számai látszanak, de nem készül hozzá életkorból, elért maximumból
vagy általános százalékokból kitalált bpm-sáv. A felső Polar-szinkron kéri le
a zónákat; a szolgáltató által nem visszaadott határokat nem pótoljuk.

A `session-analysis-v0.1` olvasási szerződés kiegészül az edzésrészenkénti,
null értékű vagy pontosan ellenőrizhető `heart_rate_zones` adattal. A régebbi,
e mező nélküli olvasási válaszok továbbra is elfogadottak. A régi tartós
szinkronkérések és nyugták sémája és bájtjai változatlanok.

## Ellenőrzés

- 293 backendteszt: a teljes korábbi szinkron-, naptár- és adatmegőrzési kapu,
  valamint valódi olvasás, pontos zónahatárok, külön edzésrészek, ismeretlen és
  hibás definíciók, korábbi marker frissítése, régi nyugta ismétlése.
- 462 frontendteszt: szerződés, kerek érték- és időbeosztás, bpm-cél, hiányzó
  határok, egységváltás, nulla/hiány, iram, nagyításhatárok és véges szélsőértékek.
- Next typegen, teljes TypeScript, módosított kódra ESLint és production build.
- A külön DOM-próba a tényleges React-vezérlőket, a zárt átjárókat és az izolált
  FastAPI/SQLite rendszert használja helyettesített Polarral. Ez nem natív
  böngésző-, Windows- vagy élő Polar-ellenőrzés.

API-referencia (ellenőrizve: 2026-10-27):
https://www.polar.com/polar-api-v4/#list-user-training-sessions
https://www.polar.com/polar-api-v4/#domainstrainingsessionzones
https://www.polar.com/polar-api-v4/#trainingsessionzone
