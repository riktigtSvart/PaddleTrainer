# C21.10.8 — erőreferenciák és mikrocikluson belüli elosztás

A C21.10.7-re készült backend- és frontendfrissítés. Nincs új függőség vagy adatbázis-migráció. A naptár színei, kapcsolói és ciklusablaka megmaradnak.

## Mi akadályozta az erősítést?

A felmérés forrásellenőrzése a teljes helyszínlistát összevetette a korábbival. Emiatt egy új, a mérésekben nem használt uszoda is forrásváltozásnak számított. A javítás a mentett gyakorlatreferenciákban ténylegesen hivatkozott erősítőhelyszínek azonosítóját, aktív állapotát, erősítésre való elérhetőségét, felszerelését és külön megerősített gyakorlatainak listáját ellenőrzi. A felszerelés és a helyszínlista sorrendje, megjelenítési neve, más sportágak, időpontok, koordináták és egyéb helyszínek módosítása önmagában nem érvényteleníti a megfigyelést.

Az eredeti felmérés, hash és forrásnyugta változatlan. Az aktuális forrás külön igazolható nyugtával kerül a tervezési felülvizsgálatba. A szerver és a böngésző önállóan újraszámolja az összehasonlítást; a szerver által küldött `reusable` jelző önmagában nem bizonyíték. A böngésző ellenőrzi a tulajdonost, az időbeli elérhetőséget és a tényleges felmérésből származó helyszínazonosítókat is.

Tényleges felszerelésváltozás, használt helyszín törlése/archiválása, egészségi vagy mozgást érintő profilváltozás, katalógus- és szabályváltozás továbbra is felülvizsgálatot igényel. A korábban hivatkozott felkészülések módosítása eltér egy új, a régieket változatlanul hagyó célkitűzés hozzáadásától. A konkrét felkészülés és sportági szerep illeszkedését külön is ellenőrizzük.

Valódi eltérés esetén az erőfelmérési összegzés és a naptári mezociklusablak a forrásváltozás kategóriáját is megmutatja. Az edzés további feltételei — gyakorlatjártasság, panaszok, állapot, dátum, helyszín és használható sorozatok — továbbra is számítanak. A saját mérésből származó sorozatokhoz nem találunk ki súlyt, ismétlésszámot vagy új maximális tesztet.

## Hogyan változik az elosztás?

A `training-plan-policy-v0.12` előbb elkészíti a korábbi szabályokkal érvényes kiinduló tervet. Ezután a teljes vizsgált időszak egyenként használható változatait is előállítja, és legfeljebb 32 javító lépésben átrendezi a szerkeszthető saját javaslatokat.

1. Elsőbbséget kap a mikrocikluson belüli különböző mentett fő célok képviselete. Azonos számú képviselt fő cél esetén a kiinduló terv már képviselt fő célja is számít. Ezután a fenntartó és a másodlagos célok következnek.
2. Ezen belül kevesebb egymást követő edzésnapot és rövidebb üres szakaszokat keresünk, az időszak szélén és a szomszédos mikrociklusok között is.
3. Azonos ritmus mellett előnyben részesülhet a mikrociklus korábbi részére kerülő erősítés. Két alkalom célszerinti cseréje vagy egy összeillő csoport eltolása is mérlegelhető.
4. A mikrociklus kiinduló edzésszáma nem nő, összideje nem emelkedik. A naptári áthelyezés önmagában nem növeli az egyes családok időtartamát. Nem kell kitölteni a rendelkezésre álló időt.

Ez korlátozott, determinisztikus keresés, nem globális optimum vagy személyre tanult regeneráció. A minden második civil napra kerülő edzés elhelyezési előny, nem mindenkire előírt élettani szabály. Szűk lehetőségeknél, meglévő edzések mellett vagy egy választott alternatíva miatt maradhatnak szomszédos edzésnapok. A meglévő importált, szerkesztett, teljesített és védett edzéseket nem mozgatjuk. A kézzel választott nap, sportváltozat, helyszín, cél és szerep kötött marad.

A napi egy új alkalom, a sportágak szerinti meglévő időköz, a gördülő hétnapos alkalom- és időkeret, a mikrociklus felső kerete, a helyszín, eszköz, napfény és időablak mind ellenőrzött marad. A 36 órás szabály továbbra is az ismeretlen erőfeszítéshez tartozó kezdő elhelyezési szabály; nem minden edzéspár általános minimuma.

Az elosztás előtti jelöltazonosítók és az előtte/utána számolt ritmus a felülvizsgálat része. A böngésző ellenőrzi a jelöltekből számolt mikrociklusonkénti edzésszámot és időt, valamint az egymást követő napok és üres szakaszok mutatóit. A régebbi felülvizsgálatok továbbra is olvashatók.

## Konkrét ellenőrző eset

A 2026. november 20-án, pénteken induló **négyhetes** mezociklus próbájában heti legfeljebb 3 alkalom és 155 perc állt rendelkezésre, hétköznapi esti és hétvégi reggeli lehetőségekkel. Mind a négy mikrociklusban megmaradt a három alkalom. Az új terv pénteki erősítésből, vasárnapi technikai kajakból és keddi könnyű úszásból vagy futásból állt. A nyolc szomszédos edzésnap-pár nullára, a leghosszabb üres szakasz négy napról két napra csökkent. Ez a konkrét teszteset eredménye, nem minden beállításnál ígért beosztás.

## Használat és ellenőrzés

A backend és frontend újraindítása, valamint a böngésző frissítése után a naptárban válaszd a **Terv frissítése most** műveletet. Az új elosztáshoz új felülvizsgálat szükséges. Egy hozzáadott, a felmérésben nem használt uszoda miatt nem szükséges új fizikai erőfelmérést végezned.

Ellenőrzés: `python tools/run_c21_10_8_checks.py`. A kapu teljes backend-tervezési és frontend-regressziót, Next típusgenerálást, TypeScriptet, az érintett felület lintjét és production buildet futtat. A mellékelt forráscsomag telepítője előzetes hash-ellenőrzést, biztonsági másolatot és visszaállítást biztosít. A telepítés nem módosítja az adatbázist.
