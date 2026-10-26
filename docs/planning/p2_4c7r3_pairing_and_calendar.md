# P2.4C7R3 – Polar-tervkapcsolatok és olvasható rövid edzések

Az explicit adatkapcsolati frissítés az importok után egyszer összerendeli a
sportoló tárolt Polar-teljesítéseit a pontosan hivatkozott tervvel. A naptár
rövid, nulla hosszú és ismeretlen végidejű edzésjelölései legalább 32 CSS-pixel
magasak. Az időadatok változatlanok.

## Összerendelés

A forrás a WorkoutSession.raw_data.trainingTarget.id és a sportolóhoz tartozó
PlannedWorkout.polar_target_id egyezése. A korábban tárolt teljesítésekre is
kiterjed, ezért nem függ az új import visszamenőleges időablakától.
A naptári részletes nézet a teljesítésnél megmutatja a kapcsolódó tervet, a
tervnél pedig felsorolja a látható időszakba eső kapcsolódó teljesítéseket.

- Egyetlen saját terv egyezésénél az üres kapcsolat PROVIDER_EXACT eredettel
  kitöltődik. Az írás feltétele továbbra is az üres kapcsolati mező.
- A meglévő kapcsolat és annak eredete megmarad. Eltérő kapcsolat vagy több
  azonos Polar-azonosítójú saját terv külön ellenőrzendő eredmény.
- Más sportoló és más szolgáltató rekordjai nem érintettek. Időpont, név,
  időtartam vagy sportág alapján nem történik találgatás.
- A terv tartalma, státusza, revíziója és az autoritatív előforduláskapcsolatok
  nem változnak. A forrás szerinti kapcsolat önmagában nem nevez ki tervrevíziót
  és nem ad új tervezési vagy adaptációs jogosultságot.

A C7-folyamat új frissítéskor, legalább egy sikeres import után futtatja ezt.
A GET és a már létező kérés azonos UUID-val történő visszaolvasása nem párosít.
Az egyeztetés egyszer, az összes kért importkísérlet után történik, ezért az
újonnan átvett tervek is rendelkezésre állnak. A számlálók az utolsó sikeresen
importált adatfajta eredményében szerepelnek opcionális pairing objektumként:
linked, already_linked, unmatched, missing_reference, conflicts, ambiguous.

Az új kapcsolatok a teljes tárolt saját Polar-állományra vonatkoznak, nem az
éppen letöltött rekordok darabszámát jelentik. Kivétel vagy időtúllépés nem
igazol teljes sikert; a már mentett importadatokat az eredmény megőrzi.

## Kihagyások és visszafelé olvasható eredmények

Az opcionális skip_reasons darabszámai összeadva pontosan a skipped értékét
adják. A most ismert okok: protected_plan, invalid_record, missing_target_id,
missing_session_id, missing_start. Az ismeretlen későbbi okkód is látható marad.

Csak védett/kézi tervek esetén DATA_SYNC_PROTECTED_PLANS_SKIPPED, hiányos
forrásadatok esetén DATA_SYNC_SOURCE_RECORDS_SKIPPED jelzi a részleges importot.
Kapcsolati ütközés/többértelműség: DATA_SYNC_PAIRING_REVIEW_REQUIRED; technikai
párosítási hiba: DATA_SYNC_PAIRING_FAILED. A korábbi általános üzenetből már
nem következtetünk védett terv jelenlétére.

A régi auditrekordok változatlanul, eredeti hashükkel olvashatók; az opcionális
új mezők hiánya nem válik nulla darabszámmá. Az új részleteket is lefedi a
meglévő tartalomhash és a kliens commitigazolás-ellenőrzése. Nincs migráció és
nincs új csomagfüggőség. Részleges eredmény továbbra sem írja felül az utolsó
teljesen sikeres frissítés időpontját.

## Naptári megjelenítés

A kezdési pont a valós óra szerinti helyén marad. Az edzés magassága a valós
időarányos magasság és 32 CSS-pixel közül a nagyobb. A felirat, tooltip és
részletes ablak az eredeti időtartamot és időpontokat tartalmazza. Nagyított,
ismert végidejű eseménynél a jobb oldali kis jel a tényleges végpont helyét
mutatja. Ismeretlen végidőnél nem keletkezik kitalált időtartam vagy végpont.

A naptári óraskála a képernyő magasságához igazodik. A CSS arányosan rajzol,
a sávelosztás ResizeObserverrel a rács tényleges magasságát használja.
Kezdeti mérés előtt a legkisebb megengedett óraskálával foglal helyet.
A sávok a nagyított blokkok látható ütközéseit is kezelik, a képernyő felső
órájánál levágott eseményeket beleértve. Az eredeti időszegmensek nem módosulnak.
Az utolsó látható perc minimum magasságának külön hely marad a rács alatt.
Az edzéslehetőségek hátterének magassága továbbra is időarányos.

## Ellenőrzés

A backendkapu valódi HTTP/domain/repository/import kódot futtat eldobható
SQLite-adatokkal és szintetikus Polar-válaszokkal. A frontendkapu az összes
meglévő tesztet, a teljes TypeScript-ellenőrzést, az érintett TypeScript/TSX és
tesztfájlok ESLintjét és a production buildet tartalmazza. A telepítő megőrzi
a Windows asyncio belső socketpair működését a hálózati tesztvédelem mellett.
A konkrét eredmények a csomag VALIDATION.json fájljában szerepelnek.
