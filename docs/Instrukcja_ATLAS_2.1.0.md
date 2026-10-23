# NMT i NMTP ściągacz 2.1.0 — promienie, przekroje i scena 3D

Wydanie 2.1.0 rozszerza atlas całych kół o promienie widoczności, zielono-żółto-czerwoną mapę wysokości, przekrój terenu i lokalną, obracaną scenę 3D. Renderowanie map atlasu działa asynchronicznie, a okno pokazuje etap oraz czas również po zakończeniu pobierania. Zasoby technicznie nazywają się NMT i NMPT; „NMTP” zachowujemy w zamówionej nazwie wtyczki.

## Instalacja i aktualizacja

Pobierz [gotowy ZIP 2.1.0](https://github.com/misinskimichal/pobieracz_danych_gugik/raw/refs/heads/codex/nmt-nmtp-sciagacz/releases/NMT%20i%20NMTP%20%C5%9Bci%C4%85gacz-2.1.0.zip).

ZIP ma 102 653 bajty. SHA-256: `d998d0e12fe889e92c292ac73ecef9ebbfcae18a2f6e259a4ef5b414e8272610`.

W QGIS wybierz **Wtyczki → Zarządzanie wtyczkami → Zainstaluj z ZIP** i wskaż ZIP bez rozpakowywania. Po aktualizacji uruchom QGIS ponownie. Zakończ wcześniejsze zadania przed zmianą wersji. Foldery źródłowych kafli pozostają na dysku i można ich używać dalej.

Środowisko: QGIS 3.28–3.x, Python ≥3.9, GDAL/OGR, NumPy, requests i lxml ze środowiska QGIS. Testowane: QGIS 3.40.6 / Qt5 / GDAL 3.10.3 na Linux. Brak bezpośredniego testu Windows i macOS; QGIS 4 jest poza zakresem tego wydania. Przeglądarkowy podgląd używa standardowego HTML/JavaScript/Canvas, bez serwera, CDN, instalacji Open3D lub dodatkowych pakietów Python u użytkownika.

## Co znaczą procenty

| Wartość | Znaczenie | Przykład |
|---|---|---|
| `widoczne_pct` w drogach, zabudowie i obserwatorach | Udział próbek, w których model potwierdza widoczność co najmniej jednej turbiny na wysokości górnego końca zasięgu łopaty | 80% = np. 8 z 10 sprawdzonych miejsc |
| `niepewne_pct` | Udział próbek z niepewną trasą, brakującymi danymi lub okiem pod powierzchnią NMPT | 20% = np. 2 z 10 próbek wymagają uwagi |
| `probki` | Liczba próbek rzeczywiście ocenionych w obszarze mapy | Nie wszystkie punkty geometrii poza kołami wchodzą do mianownika |
| `turbin_max`, `piast_max` | Największa liczba widocznych turbin / piast w badanych próbkach | To liczby obiektów, nie procenty |

**Nie jest to procent widocznej powierzchni wirnika, procent pewności ani procent powierzchni działki.** Poligony oceniamy po zewnętrznym obrysie odsuniętym o 2 m; nie wykonujemy całkowania powierzchni działki ani analizy wszystkich fasad. Linie i punkty mają własne próbki. Kategorie potwierdzonej widoczności i niepewności mogą się nakładać: można widzieć jedną turbinę i mieć brak rozstrzygnięcia dla drugiej. Nie należy wymagać, aby dwa procenty sumowały się do 100%.

Warstwy rastrowe „Ile turbin widać” pokazują **liczby turbin**, a kolory wysokości pokazują **metry**. Warstwa zakresu wirnika rozróżnia trzy punkty wysokościowe, nie procent wirnika.

## Uruchomienie bez ponownego pobierania

1. Otwórz wtyczkę. Pozostaw tryb atlasu, wskaż warstwę punktową turbin i właściwe wysokości piast oraz średnice wirników.
2. Ustaw niezależne koła: np. NMT 20 000 m / krok 10 m oraz NMPT 650–1500 m / krok 0,5–2 m. Krok mapy nie zmienia rozdzielczości pobranych plików i nie jest dokładnością pomiarową.
3. Wskaż dotychczasowe, oddzielne foldery NMT i NMPT. NMPT potrzebuje także NMT do ustalenia poziomu gruntu. Oba modele używane razem muszą mieć zgodny układ wysokościowy. W analizie nie podstawiamy automatycznie innego układu w miejsce braków.
4. Jeśli dane są już pobrane, odznacz **Automatycznie pobierz brakujące kafle**. Braki zostaną oznaczone. Pozostawienie tej opcji włączonej pozwala pobrać brakujące kafle i użyć ponownie zgodnych plików.
5. Drogi, zabudowa/działki oraz obserwatorzy pozostają opcjonalne. Bez nich powstaną pełne koła, promienie, profil i scena.
6. Włącz promienie oraz przekrój/3D, podaj opisane poniżej parametry i kliknij **Utwórz atlas widoczności**.

Wyniku 2.0.0 nie można zamienić w promienie konkretnej turbiny wyłącznie na podstawie zbiorczego rastra. W komórce z liczbą „2” nie zapisano tożsamości tych dwóch turbin. Dlatego trzeba ponowić obliczenia na lokalnych źródłach. Wydanie 2.1.0 zapisuje promienie, kiedy wynik każdej turbiny jest jeszcze dostępny.

## Mapa z kreskami i zakresem

Opcja **Zapisz zielone / czerwone promienie widoczności** tworzy `promienie.gpkg`, osobno `promienie_NMT` oraz `promienie_NMPT`. Domyślnie promienie występują co 10°. Można ustawić od 1° do 90°. To gęstość ilustracji wektorowej; raster nadal analizuje wszystkie komórki w kołach, także między promieniami.

Po zakończeniu kliknij **Wysokości + promienie**. Przycisk włącza warstwę wysokości i promieni, a wyłącza konkurencyjne rastry liczby turbin i wirnika. Domyślnie aktywny pozostaje NMPT, jeśli został obliczony. NMT można włączyć w jego grupie.

| Wygląd | Znaczenie |
|---|---|
| Wypełnienie zielone → żółte → czerwone | Niska → wysoka wysokość w metrach, skala danego modelu |
| Zielony odcinek promienia | Potwierdzona w modelu widoczność piasty konkretnej turbiny |
| Czerwony odcinek promienia | Piasta przesłonięta w modelu |
| Fioletowa linia przerywana | Brak rozstrzygnięcia / nieobliczona komórka na brzegu koła |
| Szara linia przerywana | Oko znajduje się pod powierzchnią NMPT: dach lub korona |
| Przerywany obrys koła | Zadany maksymalny promień analizy, nie gwarancja widoczności |

Promień może mieć kilka zielonych i czerwonych fragmentów. Nie zakładamy, że widoczność musi kończyć się na pierwszej przeszkodzie — dalsze, wyżej położone miejsce może znów widzieć turbinę.

W stylach warstwy promieni dostępne są **Widoczność piasty**, **Widoczność końca łopaty** i **Widoczność dolnego zasięgu**. Wyniki zapisujemy jako 0 zasłonięta, 1 widoczna, 2 niepewna i 3 oko pod powierzchnią. Tabela ma pola `turbina`, `azymut`, `od_m`, `do_m`, `piasta`, `koniec`, `dolny`, `opis`. Można filtrować jedną turbinę, np. wyrażeniem `"turbina" = '1'`. `od_m` i `do_m` opisują zakres danego odcinka od turbiny, nie długość całej widocznej trasy.

Kolor promienia odczytujemy z wyniku jednej turbiny, nigdy ze zbiorczej liczby widocznych turbin. Granice odcinków są przybliżeniem na siatce obliczeniowej; nie oznaczają dokładności centymetrowej. Limit 200 000 odcinków na model chroni przed niekontrolowaną wielkością GeoPackage. Osiągnięcie limitu jest raportowane i nie ogranicza obliczeń rastrowych. Zwiększ odstęp promieni lub wybierz mniej turbin, jeśli potrzebujesz kompletnego zestawu wektorowego.

## Przekrój 2D

Włącz **Utwórz przekrój wysokościowy i obracaną scenę 3D**. Wskaż:

- **Numer turbiny w analizowanym zestawie**, licząc od 1. To kolejność odczytu warstwy/wybranego podzbioru, a nie jej atrybut identyfikatora. Wynik zawiera identyfikator użytego obiektu. Numer spoza zestawu zatrzymuje zadanie przed pobieraniem.
- **Kierunek od turbiny do obserwatora**: 0° północ siatki EPSG:2180, 90° wschód, 180° południe, 270° zachód. Domyślnie 225°.

Obserwator znajduje się na brzegu koła danego modelu, na wysokości oka ponad NMT. NMT i NMPT mogą więc mieć różne długości przekroju. Nie trzeba tworzyć warstwy obserwatorów. Wybranie opcjonalnej warstwy obserwatorów służy ocenie ekspozycji jej obiektów; w tym wydaniu nie zastępuje ręcznie ustawionego kierunku przekroju.

Przycisk **Przekrój 2D** otwiera `profil_NMPT.svg`, a jeśli brak NMPT — profil NMT. Wszystkie profile są też połączone z HTML i raportem MD. Wykres czytamy od obserwatora po lewej do turbiny po prawej:

- Kolorowe pole pokazuje teren; ciągła ciemna linia powierzchnię modelu, w NMPT także pokrycie.
- Trzy linie przerywane prowadzą do końca łopaty, piasty i dolnego zasięgu wirnika.
- Symbol po lewej oznacza oko, konstrukcja po prawej wysokość turbiny i zakres wirnika.
- Przerwy powierzchni pozostają brakami danych. Wynik nie jest wtedy przedstawiany jako pewna widoczność.
- Skala pozioma i pionowa są niezależne. Oś wysokości jest opisana w metrach.

Profil czyta ten sam model obliczeniowy co mapa, z próbkowaniem co najwyżej połowy kroku wzdłuż trasy; nie korzysta z uproszczonej siatki 3D. Włączona korekta krzywizny i refrakcji dodaje wypukłość `(6/7)·d·(L−d)/(2R)` między końcami. Przyjmujemy R = 6 378 137 m, zgodnie z półosią GRS80 używaną przez GDAL dla EPSG:2180. Dotyczy ona geometrii toru widzenia, nie zmiany wartości źródłowego NMT. Profil jednej linii może różnić się przy granicy cienia od aproksymacji rastrowej GDAL GVM_Max. Nie traktuj rozbieżności jednego piksela jako dowodu błędu źródłowych wysokości.

## Scena 3D z wybranej strony

**Scena 3D** otwiera lokalny `scena_3d_NMPT.html` albo NMT. Zawiera powierzchnię, turbinę, oko obserwatora oraz trzy linie widzenia z profilu. Początkowo kamera patrzy od podanego kierunku.

Przeciąganie zmienia stronę i nachylenie, kółko myszy powiększenie. Suwaki pozwalają też ustawić kamerę. **Pion ×1** zachowuje proporcje metrów; większe wartości służą prezentacji reliefu. Przełącznik pokrycia w NMPT porównuje górną powierzchnię z samym gruntem. **Ustaw widok z przekroju** przywraca kierunek, nachylenie i skalę. Zmiana kamery nie przelicza profilu — trasę określa parametr analizy.

Podgląd ma do 129×129 wierzchołków i jest tworzony tylko dla wybranej turbiny, osobno dla każdego modelu. Rzeczywisty krok podglądu i krok analizy widnieją w nagłówku. Braki pozostają otworami. Rzadsza siatka może pomijać wąskie przeszkody, dlatego **wyniku widoczności nie odczytujemy z samego wyglądu uproszczonej sceny**.

To widok powierzchni 2,5D w przestrzeni 3D. Nie jest pełnym ray tracingiem brył, BIM ani modelem wnętrz i prześwitów koron. Wirnik jest statyczną ilustracją wymiarów. Przerywane trasy są nakładką nad obrazem, aby dało się je śledzić; nie znikają za przeszkodami. Analiza i profil uwzględniają wybraną korektę krzywizny; lokalna scena pokazuje płaskie współrzędne. Podgląd nie zastępuje oceny krajobrazowej, rozpoznania terenowego ani analizy aktualności drzew i zabudowy.

## Dlaczego QGIS wcześniej długo nie odpowiadał

W 2.0.0 obliczenia działały w zadaniu roboczym, ale po nich funkcje eksportu układu PDF i PNG synchronicznie renderowały dane w głównym wątku. Duże rastry lub wolny podkład WMS mogły blokować okno. To ustalona z kodu przyczyna potencjalnego zatrzymania; bez pomiaru konkretnego uruchomienia nie przypisujemy jej całego czasu oczekiwania na danym komputerze.

W 2.1.0:

1. Dane, maski NoData, promienie, profile, siatka podglądu, piramidy i statystyki wysokości powstają w `QgsTask`.
2. Mapy do atlasu renderuje `QgsMapRendererParallelJob` z sygnałem zakończenia. Główna pętla interfejsu może obsługiwać zdarzenia w czasie renderowania.
3. Układ prezentacji używa gotowych obrazów map zapisanych w `mapy_atlasu/`. Końcowy PDF i PNG nie wymagają ponownego odczytu źródłowych modeli lub podkładów.
4. Widoczny jest etap, numer renderowanej mapy i licznik czasu. **Anuluj** przerywa renderowanie, zachowując obliczone rastry i podglądy.

Obiekty `QgsProject` i `QgsPrintLayout` pozostają w wątku interfejsu. Samo przeniesienie ich do dowolnego wątku Python byłoby niepoprawne. Końcowe składanie ograniczonych rozmiarem stron A4 oraz dodawanie warstw nadal odbywa się w interfejsie i może dać krótką pauzę. Nie deklarujemy całkowitego braku opóźnień na każdym komputerze. Wolny WMS może nadal wydłużyć renderowanie mapy, ale etap jest widoczny. ETA dotyczy konkretnego etapu/modelu i nie jest gwarantowaną godziną zakończenia całego zadania.

Zachowaj `mapy_atlasu/`, jeśli chcesz później ponownie wyeksportować układ zapisany w projekcie. Finalny PDF/PNG pozostaje niezależnym plikiem. Styl oryginalnych warstw i raster wynikowy w projekcie pozostają dostępne do dalszej pracy.

## Budowa i rozwiązania programistyczne

| Plik | Odpowiedzialność i uzasadnienie |
|---|---|
| `core.py`, `catalog.py`, `engine.py` | Planowanie, rzeczywiste źródła WCS, zgodność układów, kontrola pobranego rastra, cache, ograniczona równoległość, raporty i kontynuowanie po brakach |
| `visibility.py` | Odczyt punktów i indeks lokalnych rastrów; ograniczony cache bloków, wybór najlepszych poprawnych danych |
| `atlas.py` | Koła każdej turbiny, trzy wysokości, dwa skrajne modele dla braków, dyskowe rastry skumulowane; fizyczny poziom turbiny pochodzi z NMT |
| `atlas_details.py` | Promienie z wyników pojedynczej turbiny, profil z modelu obliczeniowego, ograniczona siatka i serializacja sceny; działa bez projektu QGIS w zadaniu roboczym |
| `scene3d.html` | Samodzielny Canvas: projekcja siatki, kolory wysokości, kamera, turbina i trasy; bez zależności sieciowych |
| `atlas_context.py` | Próbowanie dróg, obrysów i obserwatorów, GeoPackage i CSV, jawny mianownik procentów |
| `atlas_presentation.py` | Style i układ na wątku GUI, asynchroniczny renderer QGIS i składanie prezentacji |
| `workspace_dialog.py`, `plugin.py` | Jeden formularz, opcje kół, promieni i sceny, sygnały zadań, licznik czasu, anulowanie i otwieranie wyników |
| `coverage.py` | Automatycznie aktualizowany indeks pobranych kafli w folderach; zmiana indeksu nie przelicza dawnych atlasów |

Przykład konfiguracji silnika z kodu PyQGIS, po utworzeniu źródła punktowego i kontekstu transformacji:

```python
from qgis.core import QgsVectorLayerFeatureSource, QgsProject
from nmt_nmpt_downloader.atlas import AtlasEngine

height = 'PL-EVRF2007-NH'
opts = dict(
    folders={'NMT': '/dane/NMT', 'NMPT': '/dane/NMPT'},
    report_folder='/dane/atlasy', auto_download=False,
    source_settings={r: dict(resolution=0, height=height,
                            strict_resolution=False, alternate_height=False)
                     for r in ('NMT', 'NMPT')},
    models=[dict(resource='NMPT', radius=1000, resolution=1, height=height)],
    eye=1.7, hub=120, diameter=160, hub_field='', diameter_field='',
    curvature=True, rays=True, ray_spacing=10,
    details=True, view_turbine=1, view_azimuth=225,
)
# W aplikacji uruchamiaj silnik przez AtlasTask, nie blokuj konsoli/interfejsu.
engine = AtlasEngine(QgsVectorLayerFeatureSource(turbiny), turbiny.crs(),
                     QgsProject.instance().transformContext(), opts)
# report = engine.run()  # do skryptów poza interfejsem; GUI używa QgsTask
```

Samo uruchomienie kodu nie pobiera przykładowych danych: używa jawnie podanych folderów. Jeśli wybierzesz automatyczne pobieranie, obowiązuje istniejący mechanizm WCS, weryfikacji numerycznych wysokości i raportowania braków. Nie używamy prezentacyjnego obrazu Byte jako modelu wysokości tylko dlatego, że jest małym TIFF-em.

## Weryfikacja i dalsze kierunki

Weryfikacja wydania obejmuje 62 testy: wcześniejsze pobieranie i widoczność, promienie przypisane do właściwej turbiny, niepewność, limity, zasłonięcie profilu, oko pod koroną, korektę krzywizny, ograniczony podgląd z otworami, eksport asynchroniczny z aktywnym timerem interfejsu oraz anulowanie bez usunięcia danych. Dodatkowo sprawdzamy instalację rzeczywistego ZIP przez loader QGIS, generację na syntetycznym terenie oraz składnię i obsługę sterowania JavaScript. Testy automatyczne nie zastępują sprawdzenia konkretnej inwestycji i wydajności jej pełnego obszaru.

Kierunki kolejnych wydań: kliknięcie dowolnego miejsca na mapie do profilu bez ponownego obliczania całego atlasu, serie profili z wybranych dróg/zabudowy, fotomontaż z parametrami aparatu, wczytanie LoD2/CityGML i brył zamiast powierzchni oraz ray tracing siatki np. z [Open3D](https://github.com/isl-org/Open3D) lub [trimesh](https://github.com/mikedh/trimesh). To dalsze rozszerzenia, a nie deklarowane funkcje 2.1.0. Szersze pomysły biznesowe i źródła dodatkowych danych pozostają w [pełnej dokumentacji](NMT_i_NMTP_sciagacz_dokumentacja_i_rozwoj.md).

Publiczne przykłady w `docs/examples` używają danych syntetycznych, bez geometrii i ścieżek z załączników użytkownika.
