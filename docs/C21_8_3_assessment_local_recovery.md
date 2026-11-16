# C21.8.3 – helyi felmérési adatok helyreállítása

A felhasználó C21.8.2 tesztkapuja sikeresen lefutott, de a felület továbbra is régi, 0 használható referenciás adatokat mutatott és letiltotta a szerkesztést. A korábbi javítás nem kezelte a helyreállítás során kiváltott kivételt: a `blocked` állapot tartós maradt, és a szerverfrissítés sem oldotta fel. A hibás helyi mentési kérés ráadásul megakadályozta az önállóan helyreállítható piszkozat beolvasását.

Az új regressziós esetben a szerveren régi augusztusi teljesítések vannak, helyben négy újabb mérés, a helyi felmérési dátum viszont még régi. A függő kérésben ugyanez a dátumütközés szerepel. C21.8.2 alatt ez 0 referenciát és letiltott mezőket eredményezett; a javított felület megtartja a négy új eredményt, engedi a szerkesztést és új, szabályos mentést készít elő.

## Megőrzés és javítás

- A piszkozat és a függő kérés beolvasása külön történik. Egyik hibája nem rejti el a másik ellenőrizhető válaszait.
- A felmérés összegzésének régi vagy hibás dátuma a ténylegesen megadott mérési napok, illetve a szerver helyi napja alapján rendezhető. A mérések dátuma, súlya, ismétlésszáma, oldala és tartaléka nem módosul önkényesen. Az összegzést újra át kell nézni.
- A helyi adatok eredeti szövege külön, ellenőrzött másolatba kerül, mielőtt a normál piszkozatot felváltaná a helyreállított munkapéldány. A másolat kulcsa az eredeti szövegek hashéből származik; azonos eredeti adatot nem írunk újra.
- A helyreállítás alatt beírt további változtatások újranyitáskor is megmaradnak. A régi hibás kérés nem állíthatja vissza föléjük a korábbi értékeket.
- Ellenőrizhetetlen vagy másik sportolóhoz tartozó adatok nem kerülnek hiteles mentett adatként a munkapéldányba. Az eredeti helyi szöveg ettől még megőrizhető; a hiteles szerveradatok szerkesztése elérhető marad.

A mezőket egy helyi helyreállítási hiba többé nem tiltja le. A mentés előkészítése megőrzi az eredeti adatokat, beolvassa az aktuális mentési alapot, és az összegzéshez vezet. POST csak a külön átnézett mentésre indul. Egy érvényes, de bizonytalan régi kérés továbbra is pontosan az eredeti tartalmával ellenőrizhető. Az olvashatatlan régi kérés helyett kizárólag a felhasználó helyreállítási művelete után készülhet új kérés, az eredeti külön másolatának megőrzésével.

Ha a külön másolat nem tárolható, a normál helyi adatokat nem írjuk felül. A munkapéldány szerkeszthető marad, és a helyreállítási panel JSON-letöltést is biztosít az eredeti szövegekkel és az aktuális válaszokkal.

## Egy közös szerkesztő

A tervezési oldal gyakorlati felméréséből a kérdéssor meglévő szerkesztőjére térünk vissza. Nem nyílik meg egy második, ugyanazt a helyi piszkozatot író példány. A gyakorlatválasztást és a naplózás módját megtartjuk; visszatéréskor az aktuális szerveradatok alapján ellenőrizzük a választások alkalmazhatóságát. Az aktuális állapotról szóló nyilatkozatot ismét meg kell erősíteni.

A vezetett felmérés saját hibás helyi állapotához is külön, látható helyreállítási művelet tartozik. A korábbi szövegek másolatának ellenőrzött tárolása után a mentett alkalom megnyitható, vagy aktív mentett alkalom hiányában új készíthető elő.

## Ellenőrzés

- 1351 frontendteszt, Next route-típusok, TypeScript, ESLint és production build.
- Az eredeti hibát előállító React DOM + valódi FastAPI tesztkliens: régi szerveradat, négy újabb helyi eredmény, hibás függő kérés; a mezők szerkesztése, újranyitás a helyreállítás előtt, eredeti szövegek megőrzése, új mentés előkészítése, tartós mentés és ismételt újranyitás.
- A teljes tervezési felületben kifejezetten megadott, tervezéshez használható végrehajtási adatokkal az automatikus tervezés indítása tényleges tervezett edzéseket hozott létre.
- Hibás vezetettfelmérés-állapot megőrzése és helyreállítása után az alkalmazás felületéről új alkalom indult. A kérdéssorhoz visszalépéskor egyetlen szerkesztő maradt, a kiválasztott gyakorlatok megmaradtak.

A referencia rögzítettsége és az edzéstervben használhatósága eltérő feltétel. A tervező a végrehajtás oldalát, a terhelés értelmezését és a tartalékot is ellenőrzi. A javítás nem talál ki hiányzó teljesítményt, nem módosítja a tervezési szabályokat és nem kapcsolja be önállóan a tervezést.

A vizsgálat a hibás állapotot reprodukáló tesztadatbázissal és DOM-folyamatokkal készült. A felhasználó helyi adatbázisát és böngészőtárát nem olvastuk; natív böngészős képernyőképes ellenőrzés nem készült.

## Telepítés

C21.8.2 szükséges. Csak a frontend változik; nincs új függőség vagy adatbázis-migráció. A backend változatlan, a frissítés tesztkapuja alapértelmezetten a frontend ellenőrzéseit futtatja. A korábban sikeresen lefutott backend-kör ismétlése opcionális a `--with-backend` kapcsolóval.
