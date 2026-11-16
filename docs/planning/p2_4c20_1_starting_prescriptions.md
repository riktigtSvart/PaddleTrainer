# C20.1 — Személyes kezdő időkeretek és futóváltozat

A C20.0 teljesítés-egyeztetésére épülő következő lépés. A tervező már nem kizárólag 30/60 perces rögzített minták közül választ: az ismert időablakhoz, napi és gördülő heti korlátokhoz, valamint az adott sportág saját rögzített előzményeihez igazítja az időtartamot. A terv továbbra is előnézet; edzést csak az ellenőrzött változat kifejezett elfogadása hoz létre vagy módosít.

## Bekötött változatok

| Család | Támogatott idő | Saját referencia | Intenzitás / tartalom |
| --- | --- | --- | --- |
| Könnyű technikai kajak | 20–45 perc | Az utolsó legfeljebb három érvényes kajakteljesítés; ezek nélkül legfeljebb 30 perc általános kezdőváltozat | Könnyű, beszélgetős RPE 2–3; ismert technikai fókusz |
| Hosszabb könnyű kajak | 60–75 perc | Legfeljebb három, egyenként legalább 60 perces saját kajakteljesítés | Könnyű RPE 2–3; általános aerob támogatás |
| Erőreferencia | 20–30 perces helyfoglalás | Legfeljebb három saját erőedzés, a legrövidebb legalább 20 perc | Két ismert gyakorlat, 2 × 6 ismétlés/gyakorlat, RIR 3–4; nincs kitalált kilogramm vagy súlyemelés |
| Könnyű aerob futás | 20–45 perc | Legfeljebb három saját futóteljesítés, a legrövidebb legalább 20 perc | Beszélgetős RPE 2–3; általános aerob támogatás, nem kajaktechnika vagy célzott VO₂-max edzés |

Az érvényes referencia saját, befejezett, ismert pozitív időtartamú edzés az elmúlt 56 napból. A befejezés nem lehet jövőbeli; az aktív idő nem haladhatja meg a kezdés és befejezés közti eltelt időt. A nulla, hiányzó, hibás, jövőbeli, idegen sportolói vagy túl régi adat nem használható időtartam-referenciaként. Más sportág teljesítési idejét nem másoljuk át.

Az időtartam felső korlátja a legutóbbi legfeljebb három megfelelő saját teljesítés **legrövidebb** ideje. Ezt metszi az időablak, a napi és heti keret, valamint a család termékoldali felső határa; lefelé öt percre kerekítünk. A támogatott minimum alatti saját előzményt nem helyettesítjük hosszabb kezdőmintával. Egy változatlan, továbbra is megfelelő korábbi időtartamot megtartunk. A bemelegítés, főrész és levezetés összege pontosan az edzés ideje. Az erőedzés főrésze pihenőkkel együtt értendő időkeret; az ismétlésszámot nem növeljük a rendelkezésre álló idővel.

A 20 perces rövidített formák és az 56 nap / utolsó három teljesítés szabály termékoldali, átlátható kezdőszabályok. Nem személyre validált dózisoptimumok vagy bizonyított fiziológiai modellek. Pulzus-, sebesség-, távolság- vagy 1RM-küszöböt a teljesítés időtartamából nem állítunk elő.

## A gördülő heti keret alapja

Az utolsó két lezárt naptári hét mindegyikéhez ellenőrzött, teljes dátumlefedésű, kihagyás és hiba nélküli edzésimport szükséges. Az importnak az adott hét vége után kell indulnia. A más adatkészletet érintő hiba nem érvényteleníti az önmagában teljes edzésimportot. A korábbi, ellenőrzött hét nem helyettesíthet egy újabb hiányos hetet.

Mindkét héten szükséges pozitív időtartamú edzés és a program fő sportágának jelenléte. Bármely rögzített edzés ismeretlen vagy hibás időtartama az adott hetet hiányossá teszi. A nem lefedett hét ideje `null`, a bizonyítottan üres hét ideje nulla. Ezek egyike sem szolgáltat alapot magasabb személyes kerethez.

Ha mindkét hét használható, a két hét **kisebb** edzésszámát és összidejét vesszük, legfeljebb 7 alkalommal és 10 080 perccel, majd metsszük a sportoló által megadott heti korlátokkal. Ellenőrzött előzmények nélkül megmarad az általános, legfeljebb 3 alkalom / 180 perc kezdőszabály; hiányzó heti profilkorlátoknál 2 alkalom / 90 perc. Ez nem automatikus progresszió. A kezdési időpontok között továbbra is 36 óra marad; a sportáganként eltérő ciklusbeli elosztás a következő fejlesztés része.

## Felület és szerződések

- Az edzéskártyákon látszik az időtartam és az intenzitás alapja, a rövidítés, valamint a saját forrásedzésekre mutató hivatkozások.
- A személyes heti keretnél a két felhasznált hét edzésszáma és ideje is látható.
- A kizárólag időköz vagy heti keret miatt kihagyott, egyébként használható nap „Pihenőnap”.
- A helyszíni hibajelzések csak az ott releváns sportágra vonatkoznak. A futás nem kér hajót vagy kézisúlyzót.
- A helyszín és általános órarend ellenőrző linkjei a megfelelő Edzési lehetőségek oldalakra vezetnek.
- A privát tervfelülvizsgálat 56 napot olvas; a nyilvános `planning-inputs` végpont változatlanul 14 napos előzményt és legfeljebb 28 tervezési napot szolgál ki. A regenerációs visszajelzések ablaka is 14 nap marad.
- `training-preparation-v0.2` és `training-prescriptions-v0.1` adja a kezdőkeret és jelöltenkénti dózis forrásait. A böngésző újraszámolja a referencia-korlátot és a heti keretet, ellenőrzi a szinkronforrásokat és a blokkok idejét. A régi, v0.1-es mentett értékelések olvashatók maradnak.
- A szabályverzió `training-plan-policy-v0.5`. A korábbi változatlan 30/60 perces jelöltek megőrzik a tartalmi azonosítójukat, ha továbbra is illeszkednek. Az új és eltérő idejű formák `template_version=v0.2` jelölést kapnak.
- A későbbi teljesítés továbbra is felülírja a korábbi, szinkronnal igazolt rögzítési hiányt. A C20.0 forrásvédelmei és a mentés előtti újraellenőrzés megmaradnak. A megegyező lefedést igazoló új szinkron önmagában nem gyárt új tervverziót.

Nincs adatbázis-migráció, új külső szolgáltatás vagy automatikus edzésterv-írás. A tesztadatok mesterségesek. Ez a lépés nem teljes szezonoptimalizáló: a képességfejlesztések mezocikluson belüli elosztása, terhelési hullámzása, összetett edzései és teljes céllefedése további feladat.

## Ellenőrzés

`python tools/run_c20_1_checks.py --build`

A kapu a teljes backend planning regressziót, minden frontend tesztet, Next útvonaltípus-generálást, TypeScriptet, az érintett frontendfájlok ESLint-ellenőrzését és kérésre a production buildet futtatja. A backendteszteket három, egymást nem átfedő folyamatba osztja, minden összegyűjtött fájlt egyszer futtat, és az XML-eredmények tesztszámát is ellenőrzi; a puszta nulla kilépési kód befejezett eredmény nélkül nem elég. Célzott HTTP/SQLite tesztek fedik az otthoni futást, időablakhoz igazítást, sportághelyes referenciákat, rövid saját előzményt, hiányos adatot, az 56/14 napos szerződéshatárt, a bizonyított heti keretet és az elfogadás utáni ismétlés változatlanságát. Valódi backendválaszokból generált böngészőtesztek ellenőrzik a forrásadatok és dózisok manipulálásának elutasítását, a visszamenőleges kompatibilitást és a megjelenített magyarázatokat.

Általános szakmai háttér az egyéni előzményekhez és célokhoz igazításhoz: [ACSM 2011, PMID 21694556](https://pubmed.ncbi.nlm.nih.gov/21694556/), [ACSM 2009, PMID 19204579](https://pubmed.ncbi.nlm.nih.gov/19204579/). Ezek nem validálják a fenti konkrét termékalgoritmust vagy annak számszerű határait.
