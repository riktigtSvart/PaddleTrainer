# P2.4C8.1R2 — Összefüggő távsakaszok naptári időbecslése

A konkrét kimaradás oka az R1 szűrése volt: csak szakasz nélküli vagy egyetlen WORK távsakaszos tervet engedett. A jelzett 6 km-es kajakterv 1 km WARMUP + 2 km WORK + 3 km WORK, így hiába állt rendelkezésre megfelelő saját történet, a becslés null maradt.

Az R2 az egymás után végrehajtandó, egy szinten tárolt WARMUP, WORK és COOLDOWN távsakaszokból álló terveket is támogatja. Minden szakasznak pozitív távval, hiányzó idővel és legfeljebb egyszeri végrehajtással kell rendelkeznie. A szakaszok összege legfeljebb 1% (minimum 1 méter) eltéréssel lefedi a terv teljes céltávját. A szakasznevekből nem következtetünk távra vagy időre.

Az ismétlés, hierarchikus szakaszfa, pihenő, vegyes idő/táv előírás és hiányos vagy ellentmondó szakasztáv továbbra sem kap egész edzések tempójából becslést. A forrásban megadott idő, a nulla érték és az eredeti szakaszok változatlanok.

A személyes medián, a 90 napos / 12 jelöltes történet, az eltelt idő (szünetekkel együtt), a kilógó megfigyelések jelölése, a tájékozódási tartomány és a megjelenítés az R1 módszerét használja. Ez a naptárhoz adott teljes időbecslés; nem állítja, hogy a bemelegítés és a munkaszakaszok sebessége azonos, és nem ad szakaszonkénti tempó- vagy terhelési előírást.

Az R1 dokumentumbeli ~33 perc egyetlen 6 km / 33 perc 20 másodperces referencia-mérés példája volt. Az élő érték az összes kiválasztott saját megfigyeléstől függ, így eltérhet ettől. Az R2 regresszió a bejelentés három távsakaszát és tizenkét mérésének számszerű értékeit használja, szintetikus azonosítókkal. Az edzések rögzített időtartama és a kezdés/befejezés közti eltelt idő különbözhet; a naptári foglaltság becslése az utóbbit veszi alapul.

Az új regresszió valódi izolált SQLAlchemy/FastAPI olvasással ellenőrzi a becslést, a 08:00-kor kezdődő munka előtti befejezést és a forrásértékek változatlanságát. A frontend próba ebből a backendből rögzített választ olvas, majd a kártya, az idővonal és a részletek becslésjelölését ellenőrzi.

Nincs migráció, függőségváltozás vagy új szolgáltatói lekérés. A javítás az alkalmazás-adatbázis módosítása nélkül, a következő naptárlekéréskor érvényesül.
