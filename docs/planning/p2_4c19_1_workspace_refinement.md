# C19.1 – helyszínek, napblokkok és személyes adatlap

## Megvalósított felületi módosítások

- A helyszínjegyzék fő művelete „+ Helyszín hozzáadása”.
- Minden aktív helyszínnél a Szerkesztés mellett Törlés szerepel. A törlés
  visszaállítható: a meglévő `archived` állapottal kikerül az aktív választékból,
  új edzéshez nem használható. Az órarendek, a dátumhoz kötött kivételek és a
  korábbi edzések hivatkozásai megmaradnak. A „Törölt helyszínek” alatt a
  visszaállítás szerkeszthető vázlatot nyit; a mentés igazolja a visszaállítást.
- Az általános órarend hét egymás alatti napblokkot mutat. A naphoz tartozó
  idősáv szerkesztője ugyanabban a blokkban nyílik meg. Az idősáv átvétele még
  helyi vázlatmódosítás; az egész órarend külön mentendő. Elvetéskor nincs írás.
- Az aktuális hét nap ugyanazt a blokkstruktúrát használja, a konkrét dátummal,
  örökölt lehetőségekkel és a napi eltérés forrásával. A szerkesztő az érintett
  napon belül jelenik meg. A napi kivétel továbbra sem írja át a heti mintát.
- A tervezési folyamat személyes adatlapján megszűnt a helyszínek és felszerelés
  ismételt bekérése. A heti összesített
  edzéskeret felirata elkülönül a napokra bontott időablakoktól; a korábban
  mentett mezők jelentése és értéke megmarad.
  A becslési beállítás, versenykategória és további kiegészítések opcionális,
  összecsukható részben találhatók. A mentett profil rejtett mezői, mérései és
  forráshivatkozásai szerkesztéskor megmaradnak.
- Az ágyazott adatlap nem kínál vissza a korábbi teljes felmérés saját
  órarend-folyamatába. A helyszínekhez, órarendhez és előzményekhez tartozó
  feladatot a megfelelő lépés magyarázza el. A személyes adatok teljes
  karbantartó nézete továbbra is elérhető.

## Az oldalak feladata

| Felület | Elsődleges adat / feladat |
| --- | --- |
| Cél és tervezési időtáv | Felkészülés, fő célok és időszak kiválasztása. |
| Személyes alapadatok és mozgáskeretek | Személyes adatok, sporttapasztalat, mozgást érintő keretek, heti összesített edzéskeret. |
| Előzmények és kiindulópont | Teljesítések és mérések, köztük testsúlyadatok átvétele vagy megadása. |
| Helyszínek | Tartósan elérhető sportok, felszerelés és helyszíni feltételek. |
| Általános órarend | Ismétlődő heti időablakok és választható helyszínek. |
| Az aktuális hét lehetőségei | Az általánosra épülő hét egymást követő nap, csak az eltérések megadásával. |
| Fejlesztési stratégia | Ciklusonkénti képességcélok és fejlesztési szerepek. |
| Edzésterv és változatok | Tervjavaslat, napi változatválasztás és elfogadás. |

Ez a kiadás a konkrét felületi észrevételeket és a személyes adatlap első
egyszerűsítését valósítja meg. Az egyes oldalak további részletes újratervezése
ennek a feladatelosztásnak a mentén folytatható. A tervezőmotor szabályai és az
adatbázissémák ebben a kiadásban nem változnak.

## Ellenőrzés

A teljes frontendcsomag 882 tesztje sikeres. Next útvonaltípus-generálás,
TypeScript és az érintett komponensek ESLint ellenőrzése sikeres.

Valós React StrictMode és FastAPI végpontok, izolált SQLite adatbázis mellett
ellenőrizve: a naphoz kötött szerkesztő elhelyezése; beágyazott formok hiánya;
vázlat és mentés különválasztása; változatlan hét írásmentessége; az általánost
megőrző napi kivétel; hivatkozásokat megőrző törlés és pontos visszaállítás;
a személyes adatok szerkesztése során a nem látható profilmezők megőrzése;
valamint az elveszett mentési válasz pontosan ismételhető helyreállítása.

Helyi kiadási kapu: `python tools/run_c19_1_checks.py --build`.
A cloud futtatókörnyezet produkciós buildje az ismert
`ENOENT: uv_resident_set_memory` korláton áll meg; a helyi buildet a fenti kapu
ellenőrzi. A C19.0 teljes backendkapuja változatlanul futtatható.
