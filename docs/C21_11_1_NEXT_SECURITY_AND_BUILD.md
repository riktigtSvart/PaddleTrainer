# C21.11.1 – Next.js 16.4.2 → 16.4.6 és ellenőrzött production build

A javítás pontosan a Next.js 16.4.6-os verzióját telepíti, és ehhez igazítja az eslint-config-next csomagot. Az eredeti npm és caret verziópolitika megmarad, a lockfile a konkrét 16.4.6-os csomagokat rögzíti. A Next config az eredeti beállítások megtartásával `experimental.agentUpgrade: "security"` értéket kap.

## A hiányzó build oka

A beküldött naplóban a 65 backend- és 1895 frontendteszt sikeres. Az éles fordításnál azonban a frissítési segéd indult el. A segéd coding agent hiányában a vágólapra másolta az útmutatót, és a parancs nulla kilépési kóddal fejeződött be, miközben nem készült indítható build. A régi tesztkapu csak a kilépési kódot vizsgálta, ezért tévesen adott sikeres eredményt.

A `tools/build_web_production.py` a build gyermekfolyamatában `CI=1` értéket használ. Nem kapcsolja ki tartósan a security frissítési politikát, és a szülő környezetét sem módosítja. Indulás előtt csak a korábbi generált `.next/BUILD_ID` készenléti jelölőt távolítja el; az adatbázist, `.env` fájlokat és a build gyorsítótárát nem törli.

A sikerhez a nulla kilépési kódon túl friss, nem üres BUILD_ID, öt olvasható JSON-manifeszt és az app-paths-manifest által megnevezett tényleges alkalmazásmodulok szükségesek. A korábbi marker nem tehet sikeressé egy no-op vagy megszakított buildet. A Windows és POSIX útvonal-elválasztók is támogatottak.

## Ellenőrzések

- A helyben elérhető forrásmásolaton 1856 frontendteszt sikeres az új függőségekkel; TypeScript és a módosított Next config ESLint-ellenőrzése is sikeres.
- 13 külön buildőr-teszt ellenőrzi többek között a nullás, de build nélküli kilépést, a régi markert, a hiányzó vagy sérült manifesztet, a hiányzó alkalmazásmodult, az egész marker értékének megengedett ismétlődését és a Windows útvonalakat.
- Az új verzióval valódi production build készült; a production szerver elindult, a `/nutrition` és `/shopping` oldalak HTTP 200 választ adtak.
- Az `npm audit --omit=dev --json` a helyi ellenőrzéskor nulla ismert production sérülékenységet jelzett. Ez az ellenőrzés időpontjára vonatkozó eredmény, nem általános biztonsági garancia.
- 6 külön Git-próba ellenőrzi a duplikált verzió, másik ág, másik piszkos munkafa felismerését, valamint a nem commitolt források másolását az eredeti munkafájlok és HEAD megváltoztatása nélkül.

Az itt elérhető forrásmásolat korábbi a felhasználó C21.11-es munkapéldányánál; ezért a mellékelt futtató a Windows-munkapéldányból készít másolatot, és ott az összes aktuális frontendtesztet is lefuttatja. A már sikeres backendteszteket nem ismétli meg: a frissítés nem módosít API- vagy adatbázislogikát.

## Duplikáció, munkafa és útmutatók

A megadott Windows Temp-útvonalak ebben a Linux-környezetben nem elérhetők. A telepített Next.js csomag `lib/upgrade/shared.md` és `same-major.md` útmutatói alapján történt a munka. Ez azonos főverzión belüli frissítés; codemod vagy főverzió-migráció nem futott.

A helyi másolatban nincs Git-metaadat, így helyben nem jöhetett létre Git-commit vagy PR. A GitHub CLI PR-lekérdezése bejelentkezés hiányában nem volt elérhető. Az ellenőrzések nem találtak helyben már elkezdett 16.4.6-os frissítést.

A Windowsos futtató ismét ellenőrzi az aktuális manifestet és telepített verziót, a meglévő munkafákat, az elérhető helyi és távoli commitokat, valamint — ha elérhető — a GitHub nyitott PR-jeit. Egyenértékű munkánál megáll, és nem készít második frissítést. Sikertelen vagy nem elérhető ellenőrzésnél megnevezi a hiányt, és folytatja.

Git-repónál alapértelmezésben külön munkafát hoz létre. A korábbi nem commitolt, követett módosítások és a kijelölt forrásmappák új fájljai is átkerülnek oda; az eredeti munkafájlok és HEAD változatlanok. A helyi frontend-környezetfájlt és szükséges npm-konfigurációt tartalmuk kiírása nélkül másolja, a már meglévő Python-környezethez linket készít. A függőségeket a munkafában saját `npm ci` telepíti.

Sikeres teljes frontendkapu után csak a verziófrissítéshez tartozó fájlokat commitolja. Egy még nem követett, korábbi C21.11-es kapufájlt nem csatol automatikusan a verziócommitba. A korábbi fejlesztések másolt piszkozatai külön maradnak. PR-t nem publikál.

## Gyors, célzott újraépítés

Ha a függőségek már telepítve vannak, a `python tools/run_c21_11_checks.py --build-only` csak a buildőr-teszteket és az éles buildet futtatja. Siker esetén **C21.11.1 BUILD OK** jelenik meg. Ez nem állítja, hogy az összes regresszió ugyanebben a futásban ismét lefutott.

Források: [Next.js agentUpgrade](https://nextjs.org/docs/app/api-reference/config/next-config-js/agentUpgrade), [Next.js kiadások](https://github.com/vercel/next.js/releases), valamint a telepített verzióhoz mellékelt útmutatók.
