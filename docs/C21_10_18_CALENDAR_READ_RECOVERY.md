# C21.10.18 — Naptárbetöltés és átmeneti kapcsolati hibák

## A jelentett hiba

A képen megjelenő `502, CALENDAR_API_UNAVAILABLE` a frontend naptári közvetítőjének hibajelzése. A megadott API-napló önmagában nem bizonyítja, hogy időtúllépés vagy más hálózati hiba történt: a korábbi közvetítő ezeket azonos kódra fordította. A Polar-szinkron a napló szerint sikeres volt: 41 meglévő edzés és 47 meglévő cél frissült.

Az ellenőrzés egy tényleges teljesítményhibát talált a C21.10.17-ben: az azonos programhoz tartozó naptári edzésekhez ugyanazt a teljes tervforrást külön-külön olvasta és ellenőrizte vissza. Nézetváltáskor a böngésző megszakítása sem jutott tovább a backend felé indított HTTP-kéréshez.

## Javítás

A naptári lekérdezés az elfogadott tervforrásokat együtt tölti be, és ugyanazt a változatlan rekordot egy kérésen belül egyszer ellenőrzi. A legutóbbi általános felülvizsgálatot programonként egyszer olvassa. A napi alternatíváknál az adott edzésazonosítóhoz és az aktuális előírás lenyomatához tartozó legújabb napi forrás számít; egy másik nap megnyitása nem írja felül ennek állapotát. A sűrű időszakok keresése legfeljebb 100 napi hatókörű csoportokban történik.

Az ellenőrzési állapot kizárólag az aktuális kérés idejére él. Másik kérés a friss adatbázis-állapotból indul. Eltérő rekordtartalom, tulajdonos, verzió, hash vagy tárolási metaadat új ellenőrzést kap. A mentett források, előírt gyakorlatok és célok ellenőrzése megmarad.

A nézetváltáskor megszakított kérés megszakítja a közvetítő kimenő HTTP-kérését is. Ez nem ígér már elindult backendfeladatok kényszerített leállítását. Az időkorlát továbbra is 30 másodperc. A közvetítő külön kezeli a megszakítást (`499`), időtúllépést (`504`) és kapcsolati hibát (`502`); a válasz törzsének letöltési hibáját is kezeli.

A naptár, napirend és ciklusrészletek olvasása átmeneti kapcsolati hiba vagy időtúllépés esetén 350 ms után egyszer automatikusan újrapróbálkozik. A megszakítás az újrapróbálást is leállítja. Kifejezett tárolási/szerződésellenőrzési és konfigurációs hibakódra nincs automatikus ismétlés; a sikeres HTTP-válaszon továbbra is lefut a teljes tartalmi ellenőrzés. A mentések, előnézetek és tervezési POST-kérések nem kapnak automatikus ismétlést ettől a javítástól.

A ciklusrészletek ugyanazt az egyszeri, kérésen belüli forrásellenőrzést használják. Az edzések kiosztása, a sportágak, gyakorlatok, sorozatok és a kattintással kiválasztott edzések megtartása nem változik.

## Mérés és ellenőrzés

Valódi, elfogadott, 24 edzést tartalmazó négyhetes tesztterven:

| Mért adat | C21.10.17 | C21.10.18 |
| --- | ---: | ---: |
| Teljes tervrekord-ellenőrzések | 26 | 2 |
| Ugyanazon rekord ellenőrzéseinek maximuma | 25 | 1 |
| SQL SELECT-kérések | 37 | 15 |
| Mért betöltés a tesztkörnyezetben | 1,45 s | 0,22 s |

A 2 rekord egy elfogadási bizonylat és egy felülvizsgálat. A futási idő környezetfüggő; ez nem Windows-sebességígéret.

A C21.10.17 és C21.10.18 megvalósítását ugyanazon adatbázison, rögzített órával összehasonlítva mind a hét eset pontosan azonos JSON-t adott: elfogadott teljes terv, új általános felülvizsgálat, egy napi forrás, két független napi forrás, elfogadott napi csere, utólag átírt előírás és teljesített edzés.

- Teljes backend tervezési készlet: 2444 sikeres teszt. A célzott készlet 64 tesztje között 13 új olvasási eset szerepel.
- Teljes frontendkészlet: 1796 sikeres teszt, ebből 24 új közvetítő-/újrapróbálási eset.
- Valódi FastAPI + React StrictMode/JSDOM próba: három szimulált átmeneti olvasási hiba automatikus helyreállítása, elhagyott kérés megszakítása, négyhetes nézetre váltás, eltűnő hibajelzés és nulla naptári írás.
- A telepítési kapu típusgenerálást, TypeScriptet, érintett lintet és production buildet is futtat.

Natív Windows- és natív böngészős vizuális próba nem történt. A felhasználó saját adatbázisán a hibát nem reprodukáltuk; a mérés és a helyreállási próba tesztadatbázissal készült.

## Ha újra elakadna

A sikeres naptár-, ciklus- és napirendolvasás válasza `Server-Timing: calendar;dur=...` fejlécet tartalmaz. Öt másodpercnél hosszabb kezelt olvasásról az API naplója `Slow calendar read: endpoint=... duration_ms=... status=...` sort ír. A jelzés nem tartalmaz edzésadatokat. A közvetítő továbbadja az időmérési fejlécet, így a backend ideje külön megvizsgálható a böngésző hálózati paneljén.

Adatbázis-migráció és új felmérés nem szükséges. Telepítéshez mindkét kiszolgálót le kell állítani, a forrásfrissítés és sikeres kapu után mindkettőt újraindítani, majd a böngészőt `Ctrl+Shift+R`-rel frissíteni.
