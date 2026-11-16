# C20.6.1 — A felmérés előkészítése és a közös indítási feltételek

## Kiváltó probléma

A C20.6 a gyakorlat `ready` értékét az összes közös és gyakorlatonkénti feltételből számolta, a jelölőnégyzetet ezzel tiltotta. A kártya viszont csak az adott gyakorlat saját `issues` listáját mutatta. Például egy hiányzó fő/kiegészítő erősítési szerep minden gyakorlatot szürkévé tett, de a megfelelően ismert és felszerelt gyakorlatok mellett nem látszott indok. A mezők előkészítési és tényleges eredménybeviteli szerepe, valamint az óra szerepe is félreérthető maradt.

A felhasználói képen a letiltott, saját hibajelzés nélküli elemek ezt az állapotot mutatták. A képről a konkrét közös előfeltétel nem állapítható meg; a javítás az aktuális, ellenőrzött szerverválaszból írja ki azt. Nem feltételezi, hogy az érintett sportoló profilja vagy sportági szerepe hiányos.

## Javított viselkedés

- A jelölőnégyzet az **előkészítéshez történő választást** jelenti. Az ismert, panaszmentes és helyben felszerelt gyakorlat közös indítási hiány mellett is kiválasztható.
- Az **indítás** továbbra is tiltott, amíg bármely közös feltétel hiányzik. A backend ellenőrzése és a `ready` jelentése változatlan. A nyilatkozat kipipálása sem kerüli meg az ellenőrzést.
- A „Mi hiányzik még az indításhoz?” blokk a tényleges mentett sportági szerepet, a hiányzó tapasztalat/gyakoriság választ, az ismeretlen vagy szükséges segítséget, a profil aktuális keretét, illetve az át nem vett forrásokat és hiányzó átnézést nevezi meg.
- A javítási hivatkozás a kezdeti felmérés megfelelő 1–6. lépését nyitja meg (`?step=N`), vagy a személyes profilhoz/helyszínekhez vezet. Nem ment automatikusan választ és nem állítja át a sportoló állapotát.
- Az `OPEN_WITH_CONSTRAINTS` profilnál a szöveg megmondja, hogy az általános felmérő az alkalmazkodást igénylő kereteket még nem kezeli. Nem javasol valótlan profilválaszt a kapu megkerülésére.
- A felszerelési és jártassági hiány az adott gyakorlatot továbbra is kizárja. Azonos mozgásmintából választott másik gyakorlat mellett a letiltás külön indoklást kap.
- Frissítéskor a továbbra is megfelelő kiválasztások megmaradnak; a már nem létező, nem megfelelő vagy ismétlődő minták kiesnek. Nem erősítő alapértelmezett helyszín helyett valódi erősítő helyszín jelenik meg.

## Az óra és a kézi adatbevitel

Az előkészítő oldal kifejezetten elmagyarázza, hogy **a sorozateredményeket mindkét módban a felhasználó írja be**. A gyakorlat, az ismétlésszám, a használt súly, a tartalék és a kivitelezés nem az órából származik. Az eredménymezők a felmérés explicit indítása és a bemelegítési lépés után nyílnak meg.

A választó új neve „Az egész edzés naplózása”. A két változat:

1. „Meglévő vagy órával rögzített edzéshez kapcsolom”: a lezáráskor egy saját, ténylegesen rögzített teljes erőedzéshez kapcsolódnak a kézi sorozateredmények.
2. „Új edzésnapló-bejegyzést készítek kézzel”: a tényleges időszak és a másik felvétel hiányának áttekintése után egyszer jön létre új bejegyzés.

Ez nem új rögzítési mód: a korábbi `device/manual` parancsok és immutable bizonylatok maradnak érvényesek. A felület nem vár gyakorlatfelismerést vagy ismétlésszámlálást az órától. A valós edzés egyszer szerepel az edzésnaplóban.

A felmérés lehet egy szokásos erősítő edzés elejének része. Nem igényel külön edzésnapot. Ha ugyanabban az edzésben további munka is történik, a naplóba a teljes edzés valódi időszaka kerüljön, illetve a már meglévő felvétel kapcsolódjon hozzá; ne keletkezzen mellette második bejegyzés ugyanarra az edzésre. Az erőfelmérési sorozatokat és az egész edzés időtartamát továbbra is külön kezeli a rendszer.

## Ellenőrzés és kompatibilitás

A négy új tulajdonoshoz kötött HTTP-próba valódi mentett kérdőívben változtatja a sportági szerepet, a szükséges segítséget, az átnézést és az állapotváltozás válaszát. Az egyénileg megfelelő gyakorlatok mellett is 409-cel elutasított marad az indítás. Nem jön létre aktivitás vagy új alkalom.

A valódi Python-válaszokból származó `guided-preparation.json` a közös szerephiányos és az explicit helyreállított változatot tartalmazza. A 13 új frontendteszt ellenőrzi a választás/indítás különbségét, a pontos hibamagyarázatokat, a saját kizáró okokat, az órás és kézi magyarázatot, a lépéshivatkozást és a frissítés utáni kiválasztást.

Tényleges React DOM-próba mutatja, hogy közös hiánynál pipálható a két megfelelő gyakorlat, de a nyilatkozat után sem indulhat felmérés. A külön mentett korrekciót követő explicit frissítés megtartja a pipákat és engedélyezi az indítást. A `?step=3` a tényleges sportági szerep szerkesztőjét nyitja, POST nélkül. A C20.6 teljes felmérési, szüneteltetési, tizedesrögzítési és bizonytalan POST-újrapróbálási DOM-próbája is változatlanul sikeres az új feliratokkal.

Teljes kapu: `python tools/run_c20_6_1_checks.py --build`. Nincs adatbázis-migráció, új függőség vagy automatikus módosítás a sportoló mentett adataiban. A javítás C20.6-ra telepíthető.
