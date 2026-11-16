# C21.10.6 — felmérések megőrzése és használható kezdőminták

## Időpont és megfigyelt teljesítmény

A C21.10.5 forrásellenőrzése túl szigorú volt: a heti órarend megváltozása új felmérési forrásnak számított. A C21.10.6-ban az időablak, annak érvényessége, a napi eltérés, az időszaki helyszíni korlátozás és az edzéskeret változása megőrzi a korábbi gyakorlat- és sorozatmegfigyelést. A tervező a pillanatnyilag mentett lehetőségeket ettől függetlenül ellenőrzi: egy megszüntetett időablakba nem kerülhet új edzés.

Nem írjuk át a régi felmérés bizonylatát vagy hashét. A szerver a hitelesített közvetlen előzményláncon megkeresi a felmérés által ténylegesen hivatkozott, szakmailag azonos helyszíni/eszközadatokat. Fontos, hogy ne egy még régebbi, azonos tartalmú forrást válasszon: a korábbi felmérés pontos hivatkozását tartja meg. A helyszín azonosítója, sportjai, felszerelése és archiválása továbbra is számít. A koordináta, terület, napfénybeállítás és medencehossz a jelenlegi korlátokhoz tartozik, nem módosítja az erőfelmérés sorozatát.

A sportelőélet és a szabadidő frissítése szintén nem törli az erőreferenciát. Az egészségi, mozgást érintő, részvételi, kihagyásra vonatkozó és testadatok változása továbbra is felülvizsgálatot válthat ki. A felmérés régi profilja és a pillanatnyi mentett profil külön ellenőrizhető bizonylattal szerepel a tervben; azonos hivatkozás alatt nem lehet adatot cserélni. A katalógus és a felmérési regiszter történeti hashét nem változtatjuk meg.

## Úszás a már megadott jártasság alapján

Ha nincs külön úszási beállítás, a tervező felhasználja a mentett, jelenleg űzött fő vagy kiegészítő úszást, amennyiben a jártasság **önálló** vagy **rutinos**. A kiegészítő sportnak az aktuális fő sportot kell támogatnia, ha ez meg van adva. A „Kajak-Kenu / Kajak” hierarchikus megnevezés is felismerhető. A puszta szabadidős versenyzési szint, régi kezdési év, inaktív sport vagy tanuló jártasság nem helyettesíti az önálló úszástudást. A külön megadott „nem tudok önállóan úszni” válasz elsőbbséget kap.

Az új minta időalapú: könnyű bemelegítés, saját, kényelmes szakaszokkal és szükség szerinti pihenővel végzett főrész, majd levezetés. Nem ír elő kötelező megállást minden 50 méternél. Ha az úszásnem pontosan felismerhető, azt használja; „Vegyes” vagy hiányzó megnevezés esetén **választott, ismert úszásnem** szerepel. Nem feltételez gyorsúszást vagy mind a négy úszásnem ismeretét.

A minta valódi, az adott helyszínen megadott medencét igényel. Pontos medencehossz ehhez az időalapú kezdéshez nem kötelező; a távolságra/hosszakra épülő korábbi minták ellenőrzése megmarad. A friss saját időtartam-adat használható; ennek hiányában 20 perces, pihenőkkel együtt értendő kezdő időkeret készül. A jártasságból nem számolunk tempót, pulzust vagy folyamatosan leúszható távot. A részletes, külön úszási beállítás továbbra is megadható.

## Erőnléti kezdés számszerű referencia nélkül

Meglévő, használható sorozat esetén a korábbi, pontosan forráshoz kötött erősítő utasítás marad elsődleges. Hiányzó felmérés vagy használható sorozatok hiányában egészségi akadályt nem jelző felnőtt profilhoz külön **bevezető erőnléti gyakorlás** is választható:

- 5 perc könnyű séta és átmozgatás;
- kényelmes részleges guggolás, külső teher nélküli csípőhajlítás és álló lapockazárás; gyakorlatonként egy sorozat, legfeljebb 5 könnyű ismétlés, 1–2 perc pihenővel;
- 5 perc levezetés; a teljes 20 perc felső időkeret, nem kitöltendő kvóta.

Ismeretlen vagy bizonytalan mozdulat kihagyható; panasz esetén az utasítás megállást vagy könnyű sétát kér. Nem készül kitalált kilogramm, becsült 1RM, automatikus terhelésemelés vagy mértnek állított sorozat. A bizonylat külön jelzi a termékből származó alapbeállítást és az előkészítő célt. Ez nem igazolja a maximáliserő-fejlesztés dózisának elégségességét. A szükséges felügyelet, jelzett panasz, valódi állapot-/forrásváltozás, át nem nézett felmérés, sportági tiltás, elégtelen idő és terhelési keret továbbra is akadály marad.

Szakmai háttér: [ACSM 2026 állásfoglalás](https://pmc.ncbi.nlm.nih.gov/articles/PMC12965823/), [hivatalos összefoglaló](https://acsm.org/resistance-training-guidelines-update-2026/). Az összegzett vizsgálatok egészséges felnőtteknél többféle ellenállásos edzéssel, saját testsúllyal is mutatnak alkalmazkodást. A fenti 1×legfeljebb 5 ismétléses bevezető keret alkalmazásbeállítás; a közlemény nem igazolja ezt személyre szabott optimális dózisként. Az úszási jártasság és teljesítmény különbségéhez: [Swim England felnőtt úszási keret](https://www.swimming.org/swimengland/adult-swimming-awards/).

## Megjelenítés és verziók

A hosszú célhiány-lista és kizárási diagnosztika a **Miért ezek az edzések?** alapból összecsukott részbe kerül. Az adatok továbbra is megtekinthetők. A felmérés sportági kártyája az úszást is támogatott kezdőmintaként jelzi; nem mutat többé elavult „nincs bekötve” szöveget erre a sportágra.

A szabályverzió `training-plan-policy-v0.11`, a családregiszter új változata `workout_family_registry_v0.3`. A korábbi regiszterfüggvények változatlan történeti hashét megőrizzük. Az úszási új utasítás `swimming-prescription-v0.2`, a bevezető erőnléti minta `introductory-strength-v0.1` / `training-prescription-v0.5`. A böngésző ezek forrásait, konkrét utasításait és alapbeállításait is újraszámolja; a korábban mentett verziókat továbbra is olvassa.

Nincs új függőség vagy adatbázis-migráció. Ez a csomag nem készít még teljes mintakönyvtárat minden anaerob, sprint-, robbanékonysági vagy erő-állóképességi célhoz. A korábbi adagolási, pihenő-, napfény-, felszerelési és terhelési szabályok megmaradnak; egy valóban alkalmatlan lehetőséghez nem állítunk elő félrevezető teljesítési tervet.

## Ellenőrzés

A `tools/run_c21_10_6_checks.py` teljes backend-tervezési és frontend-regressziót, Next típusgenerálást, TypeScript-ellenőrzést, ESLintet és production buildet futtat. Az új API-próbák valós mentés/felülvizsgálat/elfogadás útvonalon ellenőrzik az időpont-áthelyezést, a régi felmérési hivatkozás változatlanságát, az úszási jártasság felhasználását, a medencehossz nélküli időalapú mintát, a referencia nélküli kezdést és az ismételt tervezés változatlanságát. A frontend a valódi API-bizonylatokat és a meghamisított változatok elutasítását is vizsgálja. A csomag README-je tartalmazza a tényleges futtatási eredményeket és a telepítést.
