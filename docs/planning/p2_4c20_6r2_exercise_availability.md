# C20.6.2 — Fekvenyomó pad és saját helyszíni gyakorlatmegadás

## Kiváltó probléma

A rúddal végzett fekvenyomás korábbi egyetlen eszközváltozata súlyzórudat, súlytárcsákat, tárcsarögzítőket, külön vízszintes padot és erőkeretet igényelt. A hagyományos, saját rúdtartóval egybeépített fekvenyomó padnak nem volt megfelelő katalóguseleme. Az állítható pad sem helyettesítette a külön vízszintes padot a felszerelési egyezésben. Ez akkor is megakadályozta a gyakorlat felmérését, amikor a sportoló saját tapasztalata szerint a helyszínen elvégezhető volt.

## Eszközkatalógus

Új, saját diagrammal rendelkező elem: **Fekvenyomó pad rúdtartóval** (`bench_press_station`). A „Fekvenyomó pad”, „Fekvenyomópad”, „Fekvenyomó állomás” és „Bench press station” nevek ugyanerre az elemre ismertek fel. A sima vízszintes edzőpad és a hason fekvő mellhezhúzó pad külön eszköz marad.

A `barbell_benchpress` három alternatívát kezel:

1. A korábbi külön vízszintes pad + erőkeret + rúd/tárcsák/rögzítők változat.
2. Fekvenyomó pad saját rúdtartóval + súlyzórúd + súlytárcsák.
3. Állítható edzőpad + erőkeret + rúd/tárcsák/rögzítők.

A csoportok az eszközegyezés termékszabályai, nem műszaki vagy egészségügyi biztonságtanúsítások. Az új katalógus verziója `2026-11-06.1`, azonos `strength-catalog-v0.1` szerkezettel. Korábbi eszközazonosító nem változik. A mentett történelmi felmérés a saját befagyasztott katalógusával marad értelmezve; új alias vagy alternatíva nem írja át visszamenőleg az értékelését.

## Tartós saját helyszíni megadás

Az Edzési lehetőségek / Helyszínek szerkesztőjében, erősítést tartalmazó helyszínnél az eszközkatalógus előtt megjelenik a **Gyakorlat megadása ezen a helyszínen** rész. A sportoló a jelenlegi gyakorlatkatalógusból választ, opcionálisan leírja a helyszíni megoldást, és külön megerősíti a szükséges felszerelés/hely tényleges rendelkezésre állását. A hozzáadás helyi piszkozat; a helyszín explicit mentése teszi tartóssá.

Ez a Location opcionális mezőjében tárolódik:

```json
{
  "exercise_confirmations": [
    {
      "exercise_id": "barbell_benchpress",
      "source_kind": "self_report",
      "note": "Saját fekvenyomó pad, rúd és súlytárcsák"
    }
  ]
}
```

Legfeljebb 128 különböző ismert gyakorlat, legfeljebb 500 karakteres megjegyzéssel tárolható. A modell zárt; nem fogad el tervezési/klinikai jogosultságot állító extra mezőt vagy más forrásfajtát. A mező nem változtatja meg a `resources` listát. Az eszközök alapján ismert és a személy által megadott elérhetőség külön eredet marad.

A mező nélküli régi Location JSON alakját a Pydantic wrap serializer pontosan megtartja. Korábbi kérések/bizonylatok nem kapnak hozzá kitalált üres mezőt; a korábbi hash és az idempotens újrapróbálás érvényes marad. A külön megadás törölhető; a törlés új options-revízió, az előző deklaráció történelmileg megmarad.

Az új olvasási eredmény `exercise_ids` mezője a fizikai eszközegyezés és a saját megadás egyesítése. Olyan helyszínnél, ahol a külön mező szerepel, a `declared_exercise_ids` és `equipment_exercise_ids` külön listák is ellenőrizhetők. Az `equipment_ids` kizárólag ténylegesen megadott eszközből képződik. Üres eszközlistából a saját gyakorlatmegadás nem hoz létre erőkeretet, rudat, súlyt vagy más felszerelést.

## Felmérés és tervezés

Közös, helyszínenként működő elérhetőségi feloldást használ:

- az eszköz/lehetőség kontextus;
- a kezdeti felmérés jártassági választója és összegzése;
- a vezetett felmérőalkalom előkészítése;
- a kezdő erőtervező napi, helyszínspecifikus választása;
- a frontend ellenőrző olvasók és a konkrét erőjavaslat megjelenítése.

A felmérésben és a tervben látszik a **Helyszíni elérhetőség: saját megadás alapján** felirat. A hiányzó felszerelésnél minden eszközváltozat ténylegesen hiányzó elemei név szerint szerepelnek.

A saját megadás csak az eszközegyezés hiányát oldja fel. Az egyénileg rögzített jártasság, a panaszmentesség, a profil és állapot kapui, a valós referenciasorozat, az oldal, a pontos terhelésjelentés, az intenzitás/adatminőség és a tervezési keretek külön ellenőrzöttek. A megadás nem számol 1RM-et, nem tesz hozzá súlyt vagy sorozatot, és nem fogad el automatikusan tervet.

A deklaráció csak a saját, aktív, erősítést támogató helyszínre érvényes. Másik helyszín, globális profilfelszerelés, archivált vagy nem erősítő helyszín nem kölcsönözheti. A tervező a felmérés saját, ellenőrzött options-bizonylatából származó helyszínt vizsgálja, a konkrét napi helyszínazonosítóval.

A helyszín módosítása új forrás: a kezdeti felmérés **Friss források és mentési alap átvétele**, majd áttekintés és mentés szükséges. Az új katalógus hash-e is szándékosan új forrásnak számít. Az eddigi eredmények ettől nem törlődnek. A korábban megnyitott, még el nem fogadott terv új forrás mellett újraértékelendő.

## Ellenőrzés és verzióhatár

A 16 új backendteszt valódi options- és felmérési HTTP-mentést, guided start/finish műveletet, plan review-t és explicit plan acceptance-t fed. Egy tesztben üres eszközlistával, kizárólag két saját helyszíni megadással indul a felmérés; a tényleges 25.000000 kg-os referenciasorozatból változatlan terhelésű fekvenyomás-javaslat készül. Számított felszerelés vagy automatikus edzés nem keletkezik.

A 19 frontendteszt ugyanebből a Python HTTP-folyamatból készült JSON-t használ. Meglévő bizonylatok, konkrét pad-alternatívák, eszközhiányok, a saját eredet megjelenítése, nem létező gyakorlat, idegen helyszín, elhagyott/hozzátett deklaráció, hamis eszközlista és módosított bizonylat külön ellenőrzött. A React DOM-próba a valódi helyszínszerkesztőben keres, választ, nyilatkozik, hozzáad, ment, újranyit és töröl; az eredeti felszerelés, többi helyszín és órarend megmarad.

Teljes kapu: `python tools/run_c20_6_2_checks.py --build`. Nincs új függőség vagy relációs adatbázis-migráció. A korábbi bizonylatok az új verzióban olvashatók. A saját helyszíni megadást tartalmazó új revíziókhoz a C20.6.2 olvasója szükséges: puszta forrás-visszaállítás egy régebbi API-ra nem alakítja vissza ezeket az adatokat. A régi és új API/frontendet együtt kell verziózni.
