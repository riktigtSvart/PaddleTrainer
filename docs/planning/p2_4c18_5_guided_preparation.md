# C18.5 – Vezetett felkészülés, heti megállapodás és távbecslés

A felmérés és a tervkészítés mutatja a mentett kiindulópontot, az elérhető időt,
az eszközöket, a felhasználható előzményeket és az elakadás konkrét okát.
A mentett állapot különbözik az éppen szerkesztett válaszoktól. A korábbi
felmérés, naptár és auditált tervváltozat továbbra is olvasható.

## A felhasználó útja

1. **Rólad:** életkor, célsport, sportmúlt, részvételi keret, eszközök. A mentés
   lehet részleges; a felület jelzi a kezdőtervhez még szükséges adatokat.
   A ténylegesen hozzáférhető kajak, kajakergométer vagy kézisúlyzó gombbal is
   kiválasztható. A mentés után látszik a következő lépés.
2. **Mikor érsz rá:** a szokásos napok és helyi időpontok egyszer megadhatók.
   Az üres záródátum módosításig tartó heti ismétlődést jelent. Ez elérhető idő,
   nem edzéselőírás. Sportági és terhelési specializáció hiányában az új
   lehetőség általános, a profil eszközeit is használja.
3. **Előzmények:** a kiválasztott mérések kiegészíthetik a felmérést. Az
   adatbázisban rögzített teljesítések a naptári időbecslésbe közvetlenül is
   bekerülnek. Minden kezdőmintához nem szükséges teljes mérési panel.
4. **Terv és áttekintés:** a kiválasztott programnál külön ellenőrzés mutatja
   a profilt, az időlehetőségeket, az eszközöket, a meglévő edzések időigényét,
   valamint a mezociklusokat és célokat. Az elakadás napjai és konkrét
   kiválasztási okai együtt megtekinthetők.

Az egyes napok kivételei és a speciális időablakok a Napirendben
szerkeszthetők. A részletes időszaki naptár külön, opcionális szakasz.
A rögzített elfoglaltság és az elérhetetlennek jelölt nap felülírja a heti
lehetőséget. Az átfedő lehetőségek időkerete nem adódik össze.

A régi, ismeretlen sportági vagy terhelési beállítású heti szabály
általánosítása külön áttekintést és mentést kap. A módosítás a következő
érintett jövőbeli alkalomtól érvényes. A korábbi napok, a kifejezett
korlátok és minden napi kivétel megmarad. A kifejezetten ismeretlennek
jelölt régi adatot nem változtatja meg automatikus migráció.

## Távból becsült idő

Az új, verziózott számítás:

`T(D) = T0 * (D / D0)^k`, ahol `k = 1 + log2(1 + p / 100)`.

Az alapértelmezett `p = 5` esetén a kétszeres távhoz `2 * 1,05 * T0` idő
tartozik. Egy 5 km / 25 perces forrásból például 10 km-re 52 perc 30 másodperc
a középbecslés. Ez a hatványfüggvény tetszőleges köztes távarányra is
alkalmazható a megadott határok között.

- Azonos sportágú, az időpontig ismert és teljesített saját edzésekből dolgozik.
- Az utolsó 90 napból legfeljebb 12 megfigyelést vizsgál, determinisztikus
  sorrenddel és a kiugró időértékek jelölt kizárásával.
- A forrás- és céltáv aránya legfeljebb kétszeres lehet mindkét irányban.
  A referencia eltelt ideje legalább öt perc. A 42 km → 50 m típusú
  átszámítás nem kap becslést.
- Csak folytonos, strukturált távú terveket kezel: üres blokktár vagy
  távolságokkal megadott, lapos bemelegítés/főrész/levezetés.
  Összetett intervallumtervhez nem kölcsönöz egész edzésből származó sebességet.
- Az eltelt idő a pihenőket is tartalmazza; ennek forrása külön látható.
- A 0–20% közötti egész százalék a profilban módosítható. A mentett beállítás
  a profil célsportjára vonatkozik, a profilváltozat hivatkozásával. A többi
  sportág az általános 5%-os feltételezést használja. Egy később ismertté vált
  profilbeállítás nem válik korábbi becslési időpontnál ismertté.
- A paraméter nincs automatikusan személyre illesztve. A körülmények és az
  intenzitás összehasonlíthatósága nincs igazolva. A ±5%-os egyéni pontosságot
  nem állítjuk. A megfigyelések szóródásával és a távaránnyal szélesedő sáv
  tervezési tájékozódás, nem kalibrált valószínűségi intervallum.

A forrásban megadott időtartam – a nulla érték is – elsőbbséget kap. A
becslés nem írja át az importált tervet, a mért teljesítést vagy a blokkokat.
A naptár és az ütközésvizsgálat ugyanazt a becslést használja. Az edzéstervező
a felső időértékkel tartalékol a meglévő tervekhez. A változatlan becslés
újraszámításának időbélyege önmagában nem hoz létre új tervrevíziót.

## A továbbra is érvényes tervezési keret

A `training-plan-policy-v0.2` a meglévő kezdőszabályt tartja: maximum
3 alkalom / 180 perc gördülő hét napban, legalább 36 óra kezdési időközzel.
A felület ezt elkülönítve mutatja a sportoló megadott rendelkezésre állásától.
A több rendelkezésre álló idő és a hosszabb távra készülő időbecslés nem
jelent magasabb edzésadag automatikus engedélyezését.

A hiányzó szinkronizálás továbbra sem bizonyít kihagyást. Kimaradt edzés
nem indít automatikus bepótlást. A terv elfogadásához továbbra is kifejezett
jóváhagyás szükséges. Az általános kezdőkorlát személyre szabott
edzéstervezési szabállyal történő felváltását ez a csomag nem végzi el.

## Ellenőrzés

- Teljes tervezési tesztcsomag: 1809 sikeres backendteszt.
- Teljes frontendteszt-csomag: 865 sikeres teszt.
- TypeScript és ESLint ellenőrzés.
- Valós Python HTTP-végpontokat és izolált SQLite-adatbázist használó DOM
  interakció: React Strict Mode, hat ismételt renderelés, előnézet
  érvénytelenítése szerkesztéskor, elveszett mentési válasz, pontosan azonos
  újraküldés, egyetlen létrejövő heti szabály, megmaradó visszavonási adat.
- Hónapokkal későbbi heti ismétlődés, helyi napi kivétel, korábbi profil
  olvashatósága, távhatárok és sportági elkülönítés.

A kiadási `next build` ebben a futtatókörnyezetben az
`ENOENT: uv_resident_set_memory` környezeti hibán állt meg. A helyi
ellenőrzéshez a `python tools/run_c18_5_checks.py --build` a tényleges
kiadási fordítást is lefuttatja, és hibánál megáll.

## Szakmai kiindulópont

- Peter S. Riegel: [Athletic Records and Human Endurance](https://www.nku.edu/~longa/classes/mat375/days/docs/CrossCountry/riegel.pdf), American Scientist, 1981.
- Andrew J. Vickers és Emily A. Vertosick: [An empirical study of race times in recreational endurance runners](https://pmc.ncbi.nlm.nih.gov/articles/PMC5000509/), 2016.

A publikációk a hatványfüggvényes becslés kiindulópontját és a
populációk/távtartományok közti alkalmazhatóság korlátait támasztják alá.
Az 5%-os távduplázási feltételezés, a kétszeres távarány és a kijelzett
tervezési sáv itt kifejezett termékbeállítás; nem személyre kalibrált
kutatási eredmény.
