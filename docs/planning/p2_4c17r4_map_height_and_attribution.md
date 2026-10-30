# P2.4C17R4 – Magasabb térkép, közös alsó információs sor

A sikeresen alkalmazott C17R3-ra készült frontend-javítás. A felső térkép a mellette lévő fejléc és összesítők alsó széléig nyúlik. A térkép tényleges, mért magasságát és szélességét használó vetület és pontkövetés megmarad.

Az idő–táv kijelzés és a térkép forrásmegjelölése ugyanazon CSS Grid sorban, két oszlopban van. A forrásmegjelölés közvetlenül a térkép alatt, teljesen kiírva, olvasható és kattintható marad. Rétegváltáskor OpenStreetMap / SRTM / OpenTopoMap, illetve az Esri-forrás jelenik meg; a GPS-időpont a közös kurzort követi. Nincs két példányban renderelt forrásjelölés.

A térkép vezérlői továbbra is a térképen vannak. A magenta útvonal, sötét körvonal, kijelölt szakasz és a grafikon változatlan. Kisebb képernyőn az összesítők, az idő–táv, a térkép és annak forrásjelölése egymás alá rendeződik. A forrás szövege törhet, nem vágjuk le. A natív Windows-elrendezés végső próbája helyben történik.

Nincs backend-, adatbázis-, szinkron- vagy tanulási módosítás. A teljes forrásállapotot ellenőrző telepítő az eredeti bájtokat és a Next-cache-t külön menti. Nincs staging, commit, push, fetch vagy szolgáltatói kérés.
