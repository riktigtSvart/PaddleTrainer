# C20.3.1 — Erősítőgépek és a katalógus megtalálhatósága

A C20.3 használati visszajelzése alapján a helyszínszerkesztő induló szűrése elrejtette a többi eszközcsoportot. A megnyitás az első kijelölt eszköz csoportjára szűrt, ezért például egy tornaszőnyeggel rendelkező helyszínnél a gépek nem látszottak a kezdőnézetben.

## Felületi változás

- A szerkesztő induláskor **minden eszközt** mutat.
- A kereső és a legördülő mellett látható csoportgombok és csoportonkénti darabszámok segítik a böngészést. Az **Erősítőgépek · 45** gomb közvetlenül elérhető.
- Csoportválasztáskor az adott csoport teljes kínálata jelenik meg: a keresés és a „csak a kijelöltek” szűrés törlődik. A kijelölt felszerelés nem változik.
- A találatszám és a **Szűrők törlése** gomb jelzi a szűrés állapotát, és lehetővé teszi a teljes listához visszatérést.
- A kijelölés megőrzése, a helyszínenkénti mentés, az elvetés és a képes segédlapok működése változatlan.

## Katalógusbővítés

Az induló 55 felszerelés és 80 gyakorlat összes meglévő azonosítója, neve, aliasa és eszközfeltétele megmarad. Az új katalógus **91 eszköztípust, ezen belül 45 erősítőgépet és 117 gyakorlatot** tartalmaz. Mind a 36 új eszközhöz eredeti, témához igazodó SVG ábra tartozik. A lapsúlyos állomást és a tárcsasúlyos változatot eltérő súlyábrázolás jelöli.

| Csoport | Új lehetőségek példái |
| --- | --- |
| Padok | Mellhezhúzó pad, Scott-pad, haspad |
| Húzógépek | Melltámaszos evezés, magas evezés, pullover, T-rudas evezés |
| Mell és váll | Hátsóváll-gép, oldalemelő gép, tárcsasúlyos mellnyomók és vállnyomó |
| Kar | Bicepsz-, tricepsznyújtó és ülő tolódzkodó gép |
| Láb és csípő | Ülő és fekvő lábhajlító, Hack- és öves guggoló, vádligépek, farizom-toló és csípőemelő |
| Törzs | Hasprésgép, törzsforgató és lapsúlyos hátfeszítő gép |

## Az eltérő eszközök nem helyettesítik automatikusan egymást

- A **mellhezhúzó pad** magas, hason fekvő evezéshez kialakított pad. Nem a mellhez lehúzó gép, és nem következtetünk rá vízszintes edzőpadból. A rudas változathoz pad + súlyzórúd + tárcsák + tárcsarögzítők, a kézisúlyzós változathoz pad + kézisúlyzó szükséges.
- A Scott-pad súly nélküli támasz; a lapsúlyos bicepszállomás külön gép.
- A saját testsúlyos hátfeszítő pad és az ülő, lapsúlyos hátfeszítő külön lehetőség.
- A tárcsasúlyos gépeknél a gép **és** a helyszínen külön kijelölt súlytárcsák szükségesek a kapcsolódó gyakorlat eszközegyezéséhez. Más helyszín tárcsái nem egészítik ki a listát.
- A korábbi általános gépnevek nem nyitják meg automatikusan az új, konkrét gépváltozatokat.
- Kombinált gépnél csak a ténylegesen használható állásokat kell bejelölni; például egy pec deck nem válik automatikusan hátsóváll-géppé.

A katalógus továbbra is a felszerelést egyezteti. Nem jelent gyakorlat-ismereti nyilatkozatot, személyes alkalmasságot vagy edzésdózis-javaslatot. A meglévő tervező saját referenciafeltételeit ez a bővítés nem módosítja.

## Kompatibilitás és források

A katalógus verziója `2026-11-05-r1`, sémája továbbra is `strength-catalog-v0.1`. Nem változik a helyszínmentés formátuma, a 128-as felszereléskorlát, a pontos újrapróbálás, a tartós nyugta és a naptári lehetőségek öröklése. A régi, C20.3-ból rögzített backendválasz és nyugta külön tesztben továbbra is olvasható.

A géptípusok és a külön evezőpad ellenőrzéséhez gyártói forrásokat használtunk. Külső képeket, márkalogókat vagy oktatószövegeket nem másolunk a felületre:

- [Eleiko Seal Row Bench](https://eleiko.com/en/equipment/benches/workoutbenches/3085629-03-eleiko-seal-row-bench-black-skai-black)
- [Life Fitness Insignia géptípusok](https://support.lifefitness.com/hc/en-us/articles/360043013553-Life-Fitness-Insignia-Series)
- [Life Fitness / Hammer Strength tárcsasúlyos géptípusok](https://www.lifefitness.com/en-us/catalog/strength-training/plate-loaded)

## A visszajelzésen látható időablak-korlát

A mellékelt tervezési képen mindkét helyszínhez az `INTERVAL_TOO_SHORT_OR_START_PASSED` ok látható. A meglévő tervező a felülvizsgálat időpontjától, az előírt kezdési előnnyel és időrácsra igazítással számolja a még használható kezdést. Ha ez már a megadott időablakon kívülre vagy másik napra esik, az alkalom nem választható. A képből a mentett órák nem állapíthatók meg; a jelzés a tényleges API-korlátot jeleníti meg. Ebben a kiadásban a tervezési időkezelés nem változik.

## Ellenőrzés

Új backendtesztek ellenőrzik a mellhezhúzó pad elkülönítését, a tárcsaigényt, a helyszínek közti kölcsönzés kizárását és a kibővített készlet pontos mentését. A frontend valós HTTP-válaszból készült új tesztadatot olvas, a korábbi C20.3 mintát is megtartva. Külön DOM-interakció ellenőrzi az összes eszközzel induló nézetet, a gépcsoport elérését, a szűrők törlését, a mellhezhúzó pad kijelölését és a helyszín mentését.

Teljes tesztkapu: `python tools/run_c20_3_1_checks.py --build`.
