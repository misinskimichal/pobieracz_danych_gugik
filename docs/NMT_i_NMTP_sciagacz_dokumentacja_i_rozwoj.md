# NMT i NMTP ściągacz — dokumentacja budowy, działania i kierunków rozwoju

**Wersja opisywanej wtyczki:** 1.1.0.  
**Data opracowania:** 23 października 2026 r.  
**Odbiorcy:** użytkownik QGIS, programista Python/PyQGIS oraz osoba planująca wdrożenia biznesowe.  
**Skróty:** NMT = model samego terenu, NMPT = model górnej powierzchni terenu, roślinności i zabudowy. Pisownia „NMTP” pozostaje częścią zamówionej nazwy produktu; techniczny skrót zasobu to „NMPT”.

Dokument opisuje działającą implementację i osobno proponowane rozszerzenia. Pomysły i przykłady analityczne z suplementu nie są funkcjami dostarczonymi w ZIP-ie 1.1.0.

## Spis treści

1. Ocena dostarczonego raportu.
2. Co robi wtyczka i jak jej używać.
3. Środowisko programistyczne i odtworzenie projektu.
4. Architektura oraz uzasadnienie decyzji.
5. Algorytm planowania, wyboru wariantów i pobierania.
6. Indeksy kafli, raporty i diagnostyka.
7. Testy, pakowanie, instalacja i rozwój kodu.
8. Suplement A: konkretne zastosowania biznesowe.
9. Suplement B: dodatkowe, mniej oczywiste dane.
10. Suplement C: przykłady Pythona i plan wdrożenia.
11. Granice obecnej wersji i bibliografia.

## 1. Czy ostatnie pobieranie poszło poprawnie?

**Tak — według spójnych raportów wtyczki zakończyło się powodzeniem.** Sprawdzono `report.json`, `report.md`, `events.jsonl` oraz GeoJSON obszarów problemowych. Poniższe zestawienie nie zawiera ścieżek lokalnych, nazwy warstwy, identyfikatora obiektu ani geometrii inwestycji.

| Wskaźnik | Wynik | Interpretacja |
|---|---:|---|
| Stan końcowy | `completed` | Kolejka ukończona bez końcowych braków/błędów |
| Zaplanowane / rozpatrzone kafle | 29 / 29 | Liczniki są spójne z listą wyników |
| NMT | 8 plików, piksel 1 m | Zastosowano zamiennik względem preferowanych 5 m |
| NMPT | 21 plików, piksel 0,5 m | Wybrano rozdzielczość źródłową |
| Układ wysokościowy wszystkich wyników | PL-EVRF2007-NH | Nie było potrzeby użycia KRON86 |
| NoData wewnątrz żądanego obszaru | 0 pikseli | W granicach kontroli opartej na środkach pikseli |
| Końcowe błędy / pominięte geometrie | 0 / 0 | Wszystkie wyniki mają stan `downloaded` |
| Zerwane połączenia | 3 | Każde ponowienie zakończyło się sukcesem, maksymalnie 2 próby |
| Błędy dodatkowego katalogu GRID5 | 2 × HTTP 401 | Nie dotyczyły publicznych wariantów GRID1 |
| Transfer | 627,82 MB | Dane numeryczne ASCII, wliczane są także ponowienia |
| Pliki wynikowe | 11,96 MB | Skompresowane GeoTIFF-y, zgodnie z zapisanymi rozmiarami |
| Czas | 1014,84 s ≈ 16 min 55 s | Ustawiono jedno pobieranie równoległe |
| Obszary problemowe | pusta kolekcja GeoJSON | Brak końcowych obszarów wymagających uwagi |

**Dlaczego NMT ma 1 m, skoro wybrano 5 m?** Dodatkowy endpoint GRID5 zwrócił 401. Tryb „Tylko wybrana rozdzielczość” był wyłączony, więc wtyczka poprawnie użyła dostępnego wariantu 1 m. To nie jest błąd pobierania. Zamiana jest jawnie zapisana w raporcie. Rozmiar piksela 1 m nie stanowi sam w sobie deklaracji dokładności pionowej 1 m.

**Czy użyto drugiego układu?** Nie. Chociaż opcja była dozwolona, wszystkie wybrane pliki mają EVRF2007. Flaga `fallback_used` w ośmiu wynikach NMT dotyczy zmiany rozdzielczości, nie zmiany układu wysokościowego.

**Dlaczego transfer jest znacznie większy od plików na dysku?** Usługa zwraca tekstowe liczby dla pełnych kafli. Dopiero lokalnie następuje konwersja i kompresja. Dodatkowo kafle na brzegu wykraczają poza bufor. W tym zadaniu analizowany obszar wynosił około 3,14 km², podczas gdy pełne kafle obejmowały około 8,39 km² NMT i 5,51 km² NMPT. Te dwa zbiory mogą się przestrzennie pokrywać; ich powierzchni nie należy dodawać jako powierzchni inwestycji.

**Co potwierdza ten audyt?** Spójność przebiegu i wyników zgłoszonych przez wtyczkę. Same pliki GeoTIFF, indeksy GeoPackage ani projekt QGIS nie były dołączone, więc niezależnie nie odczytano ich pikseli ani nie potwierdzono działania widoku mapy na tym komputerze. Nie wynika z tego także dokładność geodezyjna, aktualność wszystkich pomiarów czy kompletność bardzo wąskich obiektów, np. przewodów.

## 2. Funkcjonalność i instrukcja użytkowania

### 2.1. Przygotowanie wejścia

1. Dodaj do QGIS warstwę wektorową z poprawnie opisanym CRS.
2. Wskaż ją we wtyczce. Może zawierać punkty, linie lub poligony.
3. Dla wybranych obiektów włącz „Tylko zaznaczone obiekty”. Bez tej opcji używana jest cała warstwa.
4. Wpisz promień w metrach. Dla 20 km wpisz `20000`, dla 1 km `1000`.
5. Dla punktów i linii promień musi być większy od zera. Dla poligonu 0 oznacza jego własny obszar.

Bufor powstaje wokół całej geometrii obiektu. Trzy sąsiednie działki mogą mieć nakładające się bufory, ale ten sam kafel jest planowany tylko raz dla danego zasobu.

### 2.2. Osobne ustawienia danych

Dla NMT i NMPT ustaw niezależnie:

- czy pobierać zasób;
- folder wyników;
- preferowaną rozdzielczość źródłową;
- czy wolno zastąpić ją najbliższą dostępną;
- preferowany układ wysokościowy;
- czy przy brakach wolno sprawdzić drugi układ.

„Sprawdź dostępne rozdzielczości i układy” odświeża listę z usług. Każde pobieranie i tak sprawdza dostępność ponownie. Listy nie stanowią obietnicy, że każdy wariant ma dane w każdym punkcie kraju.

Domyślnie preferowany jest EVRF2007. Opcja drugiego układu jest wyłączona. Jeżeli potrzebujesz jednorodnego modelu do analiz, pozostaw jeden układ. Samo dopisanie EPSG:2180 do rastra nie transformuje wysokości między EVRF2007 a KRON86: EPSG:2180 opisuje tu geometrię poziomą.

### 2.3. Pobieranie, indeksy i mapa

1. Ustaw różne foldery NMT/NMPT i folder raportów.
2. Wybierz wielkość kafla, domyślnie 1024 × 1024 piksele, oraz równoległość 1–4, domyślnie 2.
3. Kliknij „Pobierz”. Przy pierwszym dużym zadaniu zacznij od mniejszego obszaru i 1–2 pobrań naraz; większa równoległość nie gwarantuje proporcjonalnego przyspieszenia usługi.
4. Obserwuj etap, aktywne transfery, postęp, MB i szacunkowe ETA. Ukrycie okna nie przerywa pracy.
5. Po ukończeniu otwórz raport. „Pokaż pobrane rastry na mapie” dodaje poprawne pliki do projektu; nie trzeba robić tego podczas samego pobierania.
6. „Pokaż / odśwież indeksy folderów” buduje także indeks dla wcześniej pobranych plików.

Warstwy „Pobrane kafle NMT” i „Pobrane kafle NMPT” pokazują obrysy plików na dysku. Po dodaniu, usunięciu lub podmianie rastra indeks się zmienia. Zapisz projekt, jeżeli ma pamiętać indeksy. Po ponownym uruchomieniu synchronizacja wymaga włączonej wtyczki.

### 2.4. Interpretacja wyników

GeoTIFF-y obejmują pełne kafle; nie są automatycznie przycinane do kształtu bufora ani łączone w jeden raster. Rozdzielczość, układ i siatka są zakodowane w nazwie. Indeks oznacza istnienie pliku, nie gwarancję ważnych danych w każdym jego pikselu.

Kafle są siatką utworzoną przez wtyczkę, a nie kopią numeracji arkuszy Geoportalu. Zawartość pochodzi z numerycznej usługi WCS. Bieżąca wersja nie wybiera roku nalotu, konkretnego archiwalnego arkusza ani konkretnego wykonawcy pomiaru.

## 3. Odtworzenie i rozwijanie wtyczki

### 3.1. Repozytorium i struktura

Kod źródłowy: [gałąź codex/nmt-nmtp-sciagacz](https://github.com/misinskimichal/pobieracz_danych_gugik/tree/codex/nmt-nmtp-sciagacz). Analiza implementacji odnosi się do kodu wtyczki z commitu `890e57c93fbd215e12d3b68b53af3d72b0897756`; kolejne commity dokumentacyjne nie muszą zmieniać aplikacji.

```text
pobieracz_danych_gugik/
├── nmt_nmpt_downloader/
│   ├── __init__.py       # punkt wejścia classFactory
│   ├── metadata.txt      # nazwa, wersja, zgodność QGIS
│   ├── plugin.py         # okno, ustawienia, QgsTask i sygnały Qt
│   ├── catalog.py        # warianty źródeł i reguły zastępowania
│   ├── core.py           # geometrie, kafle, walidacja rastrów, konwersja
│   ├── engine.py         # przebieg zadania, HTTP, retry, raporty
│   ├── coverage.py       # indeksy folderów i dodawanie rastrów
│   ├── icon.svg
│   ├── README.md
│   └── LICENSE
├── tests_nmt_nmpt/test_downloader.py
├── docs/                 # ten dokument i przykłady analityczne
└── releases/             # instalowalne ZIP-y
```

Jest to oddzielny pakiet QGIS w repozytorium zawierającym także projekt źródłowy „Pobieracz danych GUGiK”. Nowa wtyczka nie wymaga uruchomienia oryginalnej wtyczki. Obie nazwy mogą występować w tym samym repozytorium.

### 3.2. Środowisko

**Najpierw zainstaluj QGIS**, następnie pracuj w jego środowisku Pythona. `pip install qgis` nie zastępuje QGIS Desktop/PyQGIS.

Na Windows wykorzystaj Pythona i konsolę dostarczoną przez instalator QGIS/OSGeo4W. Na Linuksie użyj odpowiednich pakietów dystrybucji; przykładowo w Debianie:

```bash
sudo apt-get update
sudo apt-get install qgis python3-qgis python3-gdal python3-numpy python3-requests python3-lxml
```

Przed instalacją pakietów dopasuj repozytoria systemowe do docelowej wersji QGIS. Powyższe polecenia są instrukcją dla własnego komputera, nie poleceniami wykonanymi podczas tworzenia tego dokumentu.

Szybkie sprawdzenie w konsoli Pythona QGIS:

```python
from qgis.core import Qgis
from osgeo import gdal
import numpy, requests, lxml
print(Qgis.QGIS_VERSION, gdal.VersionInfo(), numpy.__version__)
```

Wersję 1.1.0 sprawdzano z QGIS 3.40.6, Qt5 i Pythonem 3.13 na Linuksie. Metadata dopuszcza QGIS 3.28–3.x; nie przeprowadzono tutaj macierzy testów wszystkich wspieranych wersji. Kod korzysta m.in. z `math.lcm`, więc wymaga Pythona co najmniej 3.9. QGIS 4 nie jest deklarowany jako obsługiwany.

### 3.3. Pobranie źródeł

```bash
git clone --branch codex/nmt-nmtp-sciagacz https://github.com/misinskimichal/pobieracz_danych_gugik.git
cd pobieracz_danych_gugik
```

Używaj istniejącego checkoutu, jeżeli już go masz. Do zwykłego rozwijania tej wtyczki nie trzeba tworzyć dodatkowych Git worktree. Przy pracy zespołowej zmiany funkcjonalne warto wprowadzać na oddzielnej gałęzi i porównywać z testowaną wersją bazową.

### 3.4. Minimalny punkt wejścia

QGIS szuka w katalogu pakietu pliku `metadata.txt` oraz funkcji `classFactory`:

```python
# nmt_nmpt_downloader/__init__.py
def classFactory(iface):
    from .plugin import TerrainPlugin
    return TerrainPlugin(iface)
```

`iface` daje dostęp do okna QGIS, menu, warstwy aktywnej i mapy. `TerrainPlugin.initGui()` rejestruje akcję, a `unload()` usuwa akcję, zatrzymuje obserwator indeksów i anuluje uruchomione zadania. Okno nie wykonuje sieciowych żądań w głównym wątku.

Nie należy zastępować właściwego pakietu samym powyższym fragmentem: pełną implementację stanowią wymienione pliki źródłowe.

### 3.5. Cykl tworzenia nowej funkcji

1. Zdefiniuj wymaganie i kryterium wyniku, np. „usunięcie pliku usuwa jeden obrys z indeksu”.
2. Rozdziel logikę od GUI: reguła do `catalog.py`/`core.py`, przebieg do `engine.py`, prezentacja do `plugin.py`.
3. Zadbaj o anulowanie i raportowanie błędów. Pojedynczy błąd danych nie powinien blokować innych kafli.
4. Utwórz test na małych sztucznych danych, w tym przypadek awarii.
5. Sprawdź małe reprezentatywne żądanie do usługi rzeczywistej.
6. Zwiększ wersję w `metadata.txt` i `core.VERSION`, jeżeli zmieniła się aplikacja.
7. Zbuduj ZIP, przetestuj jego instalację/ładowanie i dopiero potem udostępnij.

Licencja pakietu to GPL-3.0. Zachowaj plik licencji i sprawdzaj zgodność licencji bibliotek oraz danych dołączanych w przyszłości. Sam dostęp przez HTTP nie jest deklaracją dowolnego prawa do redystrybucji danych.

## 4. Architektura i uzasadnienie zastosowanych rozwiązań

```mermaid
flowchart TD
    A[Okno QGIS i ustawienia per zasób] --> B[Snapshot źródła obiektów]
    B --> C[QgsTask: geometrie i bufory w EPSG:2180]
    C --> D[DescribeCoverage: katalog dostępnych wariantów]
    D --> E[Plan unikalnych kafli]
    E --> F[Ograniczona pula transferów HTTP]
    F --> G[ASCII Grid: kontrola wymiarów, georeferencji i NoData]
    G --> H[GeoTIFF Float32 i zapis atomowy]
    G --> I[Raporty i maski braków]
    H --> J[Obserwacja folderów i indeksy GeoPackage]
    H --> K[Opcjonalne dodanie rastrów do projektu]
```

| Rozwiązanie | Co daje użytkownikowi | Dlaczego wybrano je tutaj |
|---|---|---|
| PyQGIS i Qt | Warstwy z bieżącego projektu, standardowe zadania QGIS | Brak konieczności osobnej aplikacji lub serwera |
| `QgsVectorLayerFeatureSource` | Praca na snapshotcie danych wejściowych | Worker nie powinien korzystać bezpośrednio z obiektu warstwy GUI |
| `QgsTask` + sygnały Qt | Responsywny interfejs | Postęp i zakończenie są przekazywane bez manipulowania widgetami z workerów |
| `ThreadPoolExecutor` | Kilka ograniczonych transferów równolegle | Sieć jest głównie zadaniem I/O, a nie tysiącami nieograniczonych wątków |
| Metryczny CRS EPSG:2180 | Promień rzeczywiście podawany w metrach | Bufor w stopniach nie odpowiada promieniowi 20 km |
| Przygotowane geometrie GEOS + indeks przestrzenny | Mniej obliczeń dla dużych warstw | Testy przecięć i wybór geometrii kafla są lokalne |
| WCS `DescribeCoverage` | Jawny faktyczny piksel i zasób | Nie zakładamy, że wariant istnieje tylko dlatego, że jest w formularzu |
| WCS 1.0.0 / ASCII Grid | Numeryczne wartości wysokości | W sprawdzonym żądaniu WCS 2.0.1 `image/tiff` dawało Byte i zaokrąglone wartości |
| GeoTIFF Float32 + DEFLATE | Małe, standardowe pliki do GIS | Zachowujemy ułamkowe wartości, kompresja DEFLATE jest bezstratna dla zapisanych wartości |
| Pełne kafle o stałej siatce | Ponowne użycie danych przy kolejnym buforze | Przycięcie każdego pliku do poprzedniego AOI ograniczyłoby cache |
| Plik tymczasowy i atomowa zamiana | Uszkodzony transfer nie wygląda jak gotowy wynik | Publikowany plik pojawia się dopiero po kontroli |
| Sygnatura żądania | Ochrona przed użyciem pliku dla innych parametrów | To skrót parametrów, nie podpis kryptograficzny samej zawartości rastra |
| GeoPackage dla indeksu | Trwałe warstwy zapisujące się z projektem | Warstwa pamięciowa utraciłaby obrysy po restarcie |
| Watcher + okresowy skan | Aktualizacja po zmianach dysku | Same zdarzenia systemowe nie gwarantują wykrycia każdej podmiany |
| JSON + Markdown + JSONL | Analiza maszynowa, czytelne podsumowanie i dziennik | Jeden format nie spełnia dobrze wszystkich trzech zastosowań |

Float32 jest świadomym ograniczeniem reprezentacji: tekstowe liczby mogą mieć więcej cyfr niż sensowne dla danych wysokościowych. Przykładowe wartości setek metrów są reprezentowane znacznie dokładniej niż centymetr, ale nie jest to obietnica dokładności pomiarowej. Zmiana formatu nie poprawia jakości źródła.

## 5. Szczegółowy algorytm działania

### 5.1. Geometrie i bufor

Wątek GUI pobiera źródło warstwy i kopię kontekstu transformacji projektu. W zadaniu:

1. stosowany jest filtr zaznaczonych ID, jeśli go wybrano;
2. geometria jest kopiowana i transformowana do EPSG:2180;
3. niepoprawna geometria jest naprawiana przez `makeValid()`;
4. dla dodatniego promienia tworzony jest bufor z 64 segmentami na ćwiartkę okręgu;
5. puste lub nadal błędne geometrie trafiają do `input_issues`;
6. pozostałe geometrie są indeksowane przestrzennie.

Bufor i rasteryzacja są przybliżeniami numerycznymi. Weryfikacja NoData dotyczy środków pikseli wewnątrz bufora, a nie każdej nieskończenie małej części granicy.

### 5.2. Katalog wariantów

`Engine.discover()` odpytuje znane endpointy i oba układy. Ma oddzielną pulę maksymalnie trzech zadań katalogowych. `parse_description()` rozpoznaje nazwę zasobu, zasięg w EPSG:2180, wektory kroku siatki i dostępność numerycznego ASCII Grid.

- NMT GRID1: `https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMT/GRID1/WCS/DigitalTerrainModel`
- NMPT GRID1: `https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMPT/GRID1/WCS/DigitalSurfaceModel`
- Opcjonalny NMT GRID5: analogiczna ścieżka z `GRID5`.

Używane identyfikatory to `DTM_PL-EVRF2007-NH`, `DTM_PL-KRON86-NH`, `DSM_PL-EVRF2007-NH` i `DSM_PL-KRON86-NH`, jeżeli zostaną potwierdzone przez usługę. `Orthoimagery` nie jest identyfikatorem tych modeli.

`catalog.py` nie przeszukuje całego internetu i nie omija uwierzytelniania. Błąd dodatkowego endpointu jest zapisywany w `catalog_errors`, a dostępne warianty działają dalej.

### 5.3. Ranking wariantów

`choose_variants()` stosuje reguły w tej kolejności:

1. usuwa drugi układ, jeśli nie ma zgody na jego użycie;
2. w trybie ścisłym usuwa inne rozdzielczości;
3. preferuje zadany układ wysokościowy;
4. w obrębie tego układu wybiera najmniejszą różnicę względem żądanego piksela;
5. przy remisie preferuje drobniejszy piksel;
6. przy „Źródłowa” preferuje najmniejszy piksel.

Preferencja układu jest ważniejsza od bliskości rozdzielczości. Dostępność 5 m w drugim układzie nie powoduje automatycznego odrzucenia 1 m w układzie preferowanym. Oba parametry są jawne w raporcie.

Jeżeli pobrany wariant jest niepełny lub błędny, sprawdzane są kolejne dopuszczone. Zachowywane są poprawne pliki, a podsumowanie wybiera wariant z największym procentowym pokryciem. Nie jest wykonywana automatyczna mozaika dopełniająca luki z różnych układów. Dwa częściowe rastry z różnych układów nie stają się potajemnie jednym „100% kompletnym” modelem.

### 5.4. Siatka kafli

Dla piksela `r` i liczby pikseli boku `p` bok kafla wynosi `s = r × p`. Kafle są wyrównane do globalnej siatki o początku 0 w EPSG:2180:

```text
xmin = x * s       xmax = (x + 1) * s
ymin = y * s       ymax = (y + 1) * s
```

Kandydaci powstają przy każdej geometrii, nie w jednym wielkim prostokącie między wszystkimi odległymi obiektami. Kafel trafia do planu, jeśli ma dodatnie przecięcie z buforem. Klucz zasób/x/y usuwa duplikaty.

Gdy warianty mają różne piksele, wspólny bok jest wyrównywany do wspólnego kroku ich siatek. Wariant zastępczy pokrywa dzięki temu ten sam prostokąt, choć może mieć inną liczbę pikseli. Limit planu to 100 000 kafli; zbyt duże zadanie wymaga podziału albo innej konfiguracji.

### 5.5. Żądanie i transfer

Przykładowe parametry, z ilustracyjnym małym BBOX:

```text
SERVICE=WCS
VERSION=1.0.0
REQUEST=GetCoverage
COVERAGE=DTM_PL-EVRF2007-NH
CRS=EPSG:2180
RESPONSE_CRS=EPSG:2180
BBOX=637000,486000,637064,486064
RESX=1
RESY=1
FORMAT=image/x-aaigrid
```

Plik pobierany jest strumieniowo fragmentami 65 536 bajtów. Połączenie ma timeout 10 s, odczyt 90 s; nie jest to limit całego czasu transferu. Sprawdzana jest długość odpowiedzi, jeśli nagłówki pozwalają ją porównać. Rozmiar odpowiedzi ma limit zależny od liczby pikseli.

Maksymalnie trzy próby są oddzielone oczekiwaniem 1 s i 2 s. Błędy plików HTTP 4xx poza 408/429 nie są ponawiane. Stałe 400/401/403/404 w katalogu także kończą próbę tego wariantu. Weryfikacja certyfikatu TLS jest włączona.

XML z błędem WCS może przyjść z HTTP 200. Dlatego nie wystarcza sam status HTTP: zawartość jest rozpoznawana, a XML parsowany z wyłączonymi encjami zewnętrznymi i bez sieciowego dołączania zasobów.

### 5.6. Walidacja i zapis

`inspect_raster()` sprawdza:

- czy GDAL otworzył plik i odczytał piksele;
- liczbę kanałów oraz szerokość/wysokość;
- oczekiwaną georeferencję i piksel;
- zgodność sygnatury dla plików istniejących;
- wartości NaN/Inf i NoData wewnątrz maski AOI.

Ważna uwaga: to nie jest niezależna weryfikacja dokładności pionowej ani daty pomiaru. Bieżąca funkcja nie wykonuje pełnego audytu pionowego CRS. Numeryczny ASCII może nie mieć własnej pełnej deklaracji CRS; znany CRS odpowiedzi jest ustawiany przy konwersji.

GeoTIFF jest zapisywany z opcjami `Float32`, `COMPRESS=DEFLATE`, `PREDICTOR=3`, `TILED=YES`, `NUM_THREADS=1`. Liczba wątków kompresji jest ograniczona, aby kilka równoległych kafli nie mnożyło niekontrolowanie obciążenia CPU. Po ponownej kontroli plik tymczasowy zastępuje plik docelowy.

Rastry całkowicie pozbawione ważnych pikseli w AOI nie są publikowane jako gotowe modele. Częściowe są zachowywane wraz z maską braków. Przerwanie zadania usuwa znane bieżące pliki tymczasowe, a zakończone kafle pozostają do wznowienia.

### 5.7. Cache i współbieżność

Nazwa pliku zawiera zasób, układ, piksel, liczbę pikseli i indeks x/y. `REQUEST_SIGNATURE` jest SHA-256 parametrów źródła, zasobu, zasięgu, rozdzielczości i CRS. Nie jest sumą kontrolną pikseli; do silnego audytu integralności plików warto w przyszłości dodać osobne SHA-256 zawartości.

Sprawdzony plik może być użyty ponownie dla innego bufora, ponieważ przechowuje pełny kafel. Cache nie dowodzi, że GUGiK nie opublikował nowszych danych. Aby odświeżyć źródło, wyłącz pomijanie plików.

Blokada folderu jest tworzona atomowo przez `O_EXCL`. Dwa zadania nie powinny nadpisywać tej samej kolekcji. Po awarii blokada może pozostać; przed ręcznym usunięciem trzeba upewnić się, że zadanie już nie pracuje.

## 6. Indeksy i raporty

### 6.1. Schemat indeksu

GeoPackage `.nmt_nmpt_index_NMT.gpkg` lub `.nmt_nmpt_index_NMPT.gpkg`, warstwa `kafle`, zawiera m.in.:

| Pole | Znaczenie |
|---|---|
| `plik`, `sciezka` | Nazwa i rzeczywista ścieżka pliku |
| `zasob` | NMT lub NMPT |
| `piksel_m` | Piksel w metrach dla wyjścia EPSG:2180 |
| `uklad_wys` | Odczytany układ lub „nieznany” |
| `rozmiar_MB` | Rozmiar pliku, MB dziesiętne |
| `mtime_ns`, `bajty` | Stan pliku wykorzystywany do przyrostowego skanowania |

GeoPackage dodaje własny klucz `fid`. Kod przypisuje atrybuty po nazwach/indeksach pól, aby dodatkowy `fid` nie przesunął kolumn.

### 6.2. Synchronizacja

`QFileSystemWatcher` obserwuje folder, a zdarzenia są grupowane przez 750 ms. Timer uruchamia też skan co 15 s. Skan działa w `ScanTask`, czyta nagłówki tylko nowych lub zmienionych plików, porównując czas modyfikacji i liczbę bajtów. Nie wykonuje pełnego haszowania ani przeliczania wszystkich pikseli.

Pliki `.tif`, `.tiff` i `.asc` są uwzględniane bezpośrednio w folderze. Podfoldery i pliki tymczasowe są pomijane. Dla nieczytelnego zmienionego pliku stary obrys może chwilowo pozostać, aby zapis w trakcie nie powodował migotania indeksu. Błędy trafiają do komunikatów QGIS.

Zmiany GeoPackage są wykonywane w głównym wątku i zatwierdzane transakcyjnie. Custom properties warstwy zapamiętują folder i zasób. Przy ponownym odczycie projektu `restore()` rejestruje obserwację. Wyłączenie wtyczki zatrzymuje timery; nie usuwa danych.

### 6.3. Pliki diagnostyczne i stany

| Plik / stan | Rola |
|---|---|
| `report.json` | Pełne parametry i wyniki, także `alternatives` oraz `files` |
| `report.md` | Czytelne podsumowanie |
| `events.jsonl` | Kolejne zdarzenia z czasem UTC, bez potrzeby doczytania całego JSON |
| `obszar.geojson` | Bufory w EPSG:4326 |
| `obszary_problemowe.geojson` | Fragmenty kafli wymagające uwagi, nie dokładny kształt każdej dziury |
| `masks/*_braki.tif` | Dokładna maska NoData: 1 = brak, 0 = poza brakami |
| `downloaded` / `reused` | Nowy transfer / ponownie użyty poprawny plik |
| `partial` / `missing` | Częściowe NoData / same NoData w AOI |
| `failed` | Nie udało się zweryfikować danych; nie dowodzi braku zasobu |
| `canceled` | Przerwano zadanie lub kolejkę |
| `outside_pixels` | AOI nie zawiera środka piksela danej rozdzielczości |

Raport jest aktualizowany okresowo, nie po każdym bajcie. Po nagłym wyłączeniu komputera dziennik i stan plików mogą zawierać więcej informacji niż ostatni checkpoint JSON. Pliki raportów mogą zawierać ścieżki i obszar inwestycji — przed publicznym udostępnieniem warto je zanonimizować.

### 6.4. MB i ETA

W GUI:

- licznik pobranych bajtów obejmuje odczytane fragmenty HTTP i ponowienia;
- pliki z cache nie zwiększają nowego transferu;
- początkowy szacunek rozmiaru kafla opiera się na 22 bajtach na piksel ASCII;
- później używana jest średnia z maksymalnie 30 zakończonych próbek;
- ETA dzieli szacowany pozostały transfer przez średnią prędkość od początku transferów;
- walidacja, kompresja, kolejne błędy i zmiany wariantu mogą wydłużyć rzeczywisty czas.

Pasek postępu uwzględnia ukończone kafle i część aktywnych transferów. ETA pozostaje oszacowaniem, a nie rezerwacją przepustowości serwera.

## 7. Weryfikacja, pakowanie i utrzymanie

### 7.1. Testy

Z katalogu głównego repozytorium, w Pythonie mającym PyQGIS:

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s tests_nmt_nmpt -v
```

W środowisku z katalogiem domowym tylko do odczytu ustaw także `XDG_CONFIG_HOME`, `XDG_CACHE_HOME` i `XDG_DATA_HOME` na własne zapisywalne katalogi. W Windows uruchom testy w środowisku QGIS; składnia ustawiania zmiennych zależy od konsoli.

Sprawdzona wersja 1.1.0 ma **18 testów zakończonych poprawnie**. Obejmują m.in. deduplikację, filtr zaznaczenia, bufor metryczny z EPSG:4326, dokładne i najbliższe warianty, fallback układu z zachowaniem zasięgu, NoData, XML błędu z HTTP 200, HTTP 503/404, ponowienia, cache, anulowanie, ochronę obcych plików, aktualizację indeksu po dodaniu/usunięciu/podmianie, zapis/odczyt projektu i cały przebieg GUI → pobranie → indeksy → mapa.

Lokalny serwer testowy zastępuje WCS. To pozwala deterministycznie sprawdzać awarie bez obciążania Geoportalu. Oddzielnie wykonano małe rzeczywiste pobrania obu modeli. Test użytkownika opisany w rozdziale 1 dostarcza dodatkowego dowodu działania pobierania na jego komputerze, ale nie zastępuje pełnej macierzy systemów i wersji QGIS.

Dodatkowe kontrole jakości:

```bash
flake8 --config=.flake8 .
bandit -ll -r nmt_nmpt_downloader
```

W czasie przygotowania dokumentacji zweryfikowano także przykłady nDSM, nachylenia, widoczności terenowej i radiolinii na danych syntetycznych oraz obliczenie PV na modelu bezchmurnego dnia. Nie wykonano modelu rzeczywistej farmy wiatrowej, analizy powodziowej ani pozyskania wszystkich dodatkowych danych z suplementu.

### 7.2. Budowa ZIP-a

Archiwum musi zawierać katalog `nmt_nmpt_downloader/`, a dopiero w nim `metadata.txt` i `__init__.py`. Nie pakuj całego repozytorium jako jednej wtyczki. Nie dołączaj raportów klienta, danych, środowiska wirtualnego ani `__pycache__`.

Przykład uruchamiany z katalogu głównego repozytorium:

```python
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import configparser
import hashlib

root = Path('nmt_nmpt_downloader')
config = configparser.ConfigParser()
config.read(root / 'metadata.txt', encoding='utf-8')
version = config['general']['version']
output = Path('releases') / f'NMT i NMTP ściągacz-{version}.zip'
output.parent.mkdir(exist_ok=True)
allowed = {'.py', '.svg', '.md', '.txt'}
with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
    for path in sorted(root.iterdir()):
        if path.is_file() and (path.suffix in allowed or path.name == 'LICENSE'):
            archive.write(path, str(Path(root.name) / path.name))
with ZipFile(output) as archive:
    assert archive.testzip() is None
    assert f'{root.name}/metadata.txt' in archive.namelist()
    assert f'{root.name}/__init__.py' in archive.namelist()
print(output, hashlib.sha256(output.read_bytes()).hexdigest())
```

Sprawdzenie CRC ZIP-a nie zastępuje uruchomienia wtyczki. Test dystrybucji powinien użyć **właśnie utworzonego archiwum**, sprawdzić odczyt metadata przez QGIS, `loadPlugin`, `classFactory`, `initGui`, otwarcie okna i `unload`.

### 7.3. Instalacja i publikacja

QGIS → Wtyczki → Zarządzanie wtyczkami → Zainstaluj z ZIP. Przy aktualizacji zakończ zadania i zrestartuj QGIS, aby wyładować stare moduły. Foldery danych pozostają niezależne od folderu instalacji.

[ZIP 1.1.0 do pobrania](https://github.com/misinskimichal/pobieracz_danych_gugik/raw/refs/heads/codex/nmt-nmtp-sciagacz/releases/NMT%20i%20NMTP%20%C5%9Bci%C4%85gacz-1.1.0.zip).

SHA-256 opublikowanej paczki 1.1.0:

```text
0f4c25d7f7e62b129caf8847b791a3f779f48853a21666077c93a7e18edccc99
```

Ponowne zbudowanie identycznych źródeł może dać inny skrót ZIP-a przez daty wpisów archiwum. Do porównania wydania używaj opublikowanego pliku lub wprowadź w przyszłości deterministyczne pakowanie.

Przed publikacją nowej wersji skontroluj skład archiwum i brak danych klienta. Umieszczenie pliku na gałęzi GitHub nie jest publikacją w oficjalnym repozytorium wtyczek QGIS; to odrębna ścieżka dystrybucji.

# Suplement A. Możliwe zastosowania biznesowe

Poniższe kierunki są propozycjami rozwoju, nie obietnicą wyników obecnej wtyczki. Najlepszy pierwszy produkt zwykle łączy dane wysokościowe z informacją o konkretnej inwestycji i daje powtarzalny raport porównujący warianty. Sama mapa wysokości jest łatwiejsza do zastąpienia niż dobrze zdefiniowany proces decyzyjny.

## A1. Wysokie budowle: widoczność masztu, turbiny, komina lub wieżowca

**Prosto:** sprawdzamy, z których miejsc planowany obiekt będzie widoczny i jak zmienia krajobraz. Klientem może być deweloper, operator telekomunikacyjny, inwestor wiatrowy lub zespół projektujący komin przemysłowy.

**Produkt:** mapa potencjalnej widoczności, liczba budynków/obserwatorów w zasięgu, porównanie wysokości np. 80/120/160 m i kilka realistycznych punktów widokowych. Dane dodatkowe: budynki 3D, lasy, obiekty chronione i rzeczywiste pozycje obserwatorów.

**Implementacja:** najpierw [GDAL Viewshed](https://gdal.org/en/stable/programs/gdal_viewshed.html) / [OSGeo/gdal](https://github.com/OSGeo/gdal) dla ukształtowania terenu; następnie przecięcia promieni z modelem zabudowy/roślinności w [trimesh](https://github.com/mikedh/trimesh). Wizualizacja wyników: [PyVista](https://github.com/pyvista/pyvista).

**Kod:** funkcja `terrain_viewshed()` w C2. Wykorzystuje NMT i odpowiada na pytanie o przesłanianie przez teren, bez przesłaniania budynkami i drzewami. Nie należy w raporcie klienta nazywać tego kompletnym fotorealistycznym ZTV. Obserwator ma wysokość nad powierzchnią wskazanego modelu; dla bardziej szczegółowego DSM trzeba osobno prawidłowo ustalić poziom terenu pod obserwatorem i odbiorcą. Analiza 20 km wymaga ciągłego rastra pokrywającego całe sąsiedztwo, nie tylko pojedynczego małego kafla.

**Uzasadnienie biznesowe:** tańsze porównanie lokalizacji przed kosztowną dokumentacją i wizją terenową. Wskaźniki odbioru: powtarzalność wariantów, zgodność z kontrolnymi punktami widokowymi, jawna wysokość obiektu i założenia refrakcji.

## A2. Maszty telekomunikacyjne: profil radiolinii i strefa Fresnela

**Prosto:** sama prosta między antenami nie wystarcza; wokół niej musi pozostać zapas przestrzeni. Drzewo może nie przecinać prostej, a mimo to pogarszać łącze.

**Produkt:** profil terenu i przeszkód, minimalny prześwit, sugerowana wysokość anteny i ranking par lokalizacji. NMT daje poziom gruntu, NMPT przybliża zabudowę i roślinność, a LiDAR pozwala dokładniej analizować przeszkody.

**Implementacja:** próbkowanie profilu w [Rasterio](https://github.com/rasterio/rasterio) albo GDAL, geodezja/transformacje w [pyproj](https://github.com/pyproj4/pyproj), obliczenia w NumPy. Funkcja `radio_clearance()` w C2 uwzględnia geometryczny prześwit 60% pierwszej strefy Fresnela i model efektywnego promienia Ziemi.

**Granica wyniku:** to kontrola geometryczna, nie pełny model propagacji. Następny etap powinien uwzględniać dyfrakcję, straty roślinności, częstotliwość, pogodę, anteny i odpowiednią metodę ITU-R. Założenie efektywnego promienia 4/3 Ziemi jest parametrem, nie stałą atmosfery.

**Uzasadnienie biznesowe:** szybka eliminacja słabych wariantów masztów oraz lista miejsc wymagających wizji terenowej zamiast nieukierunkowanych objazdów.

## A3. Energetyka wiatrowa: teren, lokalizacja i układ turbin

**Prosto:** modele wysokości pomagają znaleźć lokalizacje i ocenić przeszkody, ale nie mówią same, ile energii wyprodukuje turbina.

**Produkt:** karta lokalizacji: rzeźba terenu, nachylenia, dostęp, ekspozycja krajobrazowa, potencjalne ograniczenia wysokości oraz porównanie układu turbin po dołączeniu danych wiatrowych.

**Implementacja:** teren i nachylenia z GDAL, obrysy przeszkód z nDSM/LiDAR, dane meteorologiczne przez [ECMWF cdsapi](https://github.com/ecmwf/cdsapi). Krzywe mocy i modele pojedynczej turbiny: [windpowerlib](https://github.com/wind-python/windpowerlib). Oddziaływanie śladów aerodynamicznych i układ farmy: [FLORIS](https://github.com/NatLabRockies/floris), projekt wcześniej publikowany pod adresem NREL/floris.

**Konkretny moduł:** `WindSiteAssessment` przyjmuje punkt turbiny, wysokość piasty, promień analizy, pomiary/serie wiatru i typ turbiny. Zwraca zestaw wskaźników terenu oraz warianty uzysku z jawnie opisanymi danymi wejściowymi. `terrain_slope()` i `terrain_viewshed()` stanowią pierwsze dwie funkcje takiego modułu.

**Co trzeba uzupełnić:** ERA5 to model pogody o ograniczonej rozdzielczości, a nie pomiar na planowanej piaście. FLORIS nie zastępuje modelowania przepływu nad złożonym terenem ani CFD. Przy takim terenie potrzebne są odpowiedni model przepływu i kalibracja pomiarami. Szorstkości aerodynamicznej nie należy utożsamiać wprost z `NMPT − NMT`.

**Uzasadnienie biznesowe:** spójny screening dużej liczby lokalizacji i wskazanie miejsc, w których warto finansować pomiary, projekt dojazdu lub dokładniejsze modelowanie.

## A4. Fotowoltaika: dachy i teren z rzeczywistym zacienieniem

**Prosto:** obliczamy, które powierzchnie mają dostęp do słońca, a nie tylko gdzie jest wolne miejsce. Wysoki budynek lub drzewa mogą istotnie zmienić opłacalność.

**Produkt:** ranking dachów/działek, godziny zacienienia, powierzchnia użytkowa, wstępny uzysk i porównanie wariantów układu paneli.

**Implementacja:** segmentacja dachów z LiDAR/CityGML, nachylenie i azymut połaci, profil horyzontu oraz promienie przez przeszkody. [pvlib-python](https://github.com/pvlib/pvlib-python) służy do położenia słońca, irradiancji i modeli PV; [trimesh](https://github.com/mikedh/trimesh) do geometrii promieni. Dane o promieniowaniu można uzupełnić z [PVGIS JRC](https://re.jrc.ec.europa.eu/pvg_tools/en/).

**Kod:** przykład C3 oblicza pracę 10 kWp dla ilustracyjnego bezchmurnego dnia. Do użycia biznesowego zastąp model bezchmurny wieloletnimi danymi meteorologicznymi, dodaj temperaturę, urządzenia, przesłanianie bezpośrednie oraz osobno wpływ horyzontu na promieniowanie rozproszone. Nachylenie gruntu z NMT nie jest nachyleniem dachu.

**Uzasadnienie biznesowe:** kwalifikacja leadów instalatora, porównywanie dachów portfela nieruchomości i wskazywanie miejsc wymagających skanu lub pomiaru.

## A5. Linie energetyczne: roślinność w korytarzu i priorytety wycinki

**Prosto:** szukamy drzew i koron w pobliżu infrastruktury oraz odcinków, które warto obejrzeć w pierwszej kolejności.

**Produkt:** odcinki ryzyka, obiekty roślinności z wysokością, porównanie kampanii pomiarowych i harmonogram inspekcji/wycinki.

**Implementacja:** normalizacja chmury punktów względem NMT w [PDAL](https://github.com/PDAL/PDAL), czytanie LAZ w [laspy](https://github.com/laspy/laspy), segmentacja koron w [scikit-image](https://github.com/scikit-image/scikit-image), odległości 3D do osi/przewodów z danych operatora. Punkt startowy to nDSM w C2 i pipeline PDAL w C4.

**Ważne rozróżnienie:** NMPT może pokazać koronę, ale nie gwarantuje odtworzenia cienkiego przewodu. Do rzeczywistego prześwitu elektrycznego potrzebne są wiarygodna geometria przewodów, zwis w warunkach pracy, dokładność pomiaru i wymagane odstępy. Ogólnokrajowy LiDAR może nie mieć wystarczającej gęstości lub klas przewodów. Własny nalot korytarzowy jest tu często osobnym elementem usługi.

**Uzasadnienie biznesowe:** cykliczny produkt dla operatora, nie jednorazowa mapa. Metryki odbioru: trafność wykrytych przeszkód i procent odcinków z wystarczającą jakością danych.

## A6. Ciężki transport i budowa: dojazd, platformy dźwigowe i roboty ziemne

**Prosto:** można wcześnie sprawdzić, czy teren jest stromy i gdzie mogą być potrzebne niwelacja, nasypy lub objazd.

**Produkt:** warianty dojazdu dla komponentów turbin, transformatorów i konstrukcji; nachylenia; profile; orientacyjny bilans wykop/nasyp oraz lista miejsc wymagających projektu geotechnicznego.

**Implementacja:** `terrain_slope()` w C2, rastry kosztu trasy, [scikit-image graph](https://github.com/scikit-image/scikit-image) (`route_through_array`) oraz [GeoPandas](https://github.com/geopandas/geopandas) do ograniczeń przestrzennych. Pola wyłączone z ruchu muszą być barierą, a NoData nie może stać się tanią drogą.

Przykładowy start po przygotowaniu rastra kosztu `cost` i poprawnych indeksów start/koniec:

```python
from skimage.graph import route_through_array
path, accumulated_cost = route_through_array(
    cost, start=(row_a, col_a), end=(row_b, col_b),
    fully_connected=True, geometric=True)
```

To rozwiązanie siatkowe nie uwzględnia samo promienia skrętu zestawu, nośności mostu, skrajni, zezwoleń ani prawa do gruntu. NMT nie daje nośności podłoża; do platform i fundamentów potrzebne są badania geotechniczne.

**Uzasadnienie biznesowe:** wcześniejsze oszacowanie kosztów i wykrycie trudnych miejsc przed mobilizacją sprzętu.

## A7. Energetyka i przemysł: odpływ wody oraz screening zalania

**Prosto:** szukamy obniżeń i kierunków spływu, aby wiedzieć, gdzie zbierać dodatkowe dane przed budową stacji, BESS lub placu przemysłowego.

**Produkt:** zlewnie i drogi odpływu, punkty wymagające rozpoznania odwodnienia, porównanie wariantów posadowienia oraz scenariusze zalania po dołączeniu warunków hydrologicznych.

**Implementacja:** analiza zlewni w [pysheds](https://github.com/pysheds/pysheds), a dla modelowania powierzchniowego i scenariuszy powodziowych [HydroMT-SFINCS](https://github.com/Deltares/hydromt_sfincs). Uzupełnij model przepustami, ciekami, wałami, budowlami hydrotechnicznymi i danymi opadowymi/wodowskazowymi.

**Kod:** C5 pokazuje przepływ przygotowania DEM i akumulację. To nie jest mapa prawdopodobieństwa powodzi ani model wydajności kanalizacji. Automatyczne „wypełnianie zagłębień” może usunąć z modelu rzeczywiste zbiorniki lub obiekty retencji; wyniki trzeba sprawdzić względem lokalnej hydrologii.

**Uzasadnienie biznesowe:** wczesne porównanie działek i ograniczenie kosztownych niespodzianek w projekcie odwodnienia.

## A8. Wizualizacja terenu i cyfrowy model inwestycji

**Prosto:** klient widzi obiekt w otoczeniu w przeglądarce lub aplikacji 3D, może porównać warianty i pokazać problem interesariuszom.

**Produkt:** model terenu z projektem turbiny/budynku, przekroje, punkty widokowe, scenariusze przebudowy i przeglądarka całego portfela inwestycji.

**Implementacja:** lokalny prototyp w [PyVista](https://github.com/pyvista/pyvista), geometria i testy kolizji w [trimesh](https://github.com/mikedh/trimesh), publikacja dużych scen przez [CesiumJS](https://github.com/CesiumGS/cesium) i kafle 3D Tiles. Przyda się mesh z teksturą, CityGML i daty nalotów, nie tylko raster wysokości.

**Kod:** `make_terrain_mesh()` w C2 zapisuje VTK StructuredGrid `.vts`, który można otworzyć np. w ParaView. To etap demonstracyjny, a nie gotowy eksporter 3D Tiles.

Przed publikacją globu trzeba uzgodnić układy poziome i wysokościowe. Nie wolno użyć easting/northing EPSG:2180 jako długości/szerokości geograficznej ani bez sprawdzenia potraktować wysokości EVRF2007 jak wysokości elipsoidalnej WGS84. W dużych scenach potrzebne są LOD, decymacja i strumieniowanie; jednorazowe wczytanie miliardów pikseli do siatki jest niepraktyczne.

**Uzasadnienie biznesowe:** szybsze uzgodnienia z klientem, jedna scena dla kilku zespołów i produkt prezentacyjny połączony z analizą.

## A9. Wysokie obiekty i infrastruktura: monitoring ruchów gruntu

**Prosto:** można wykrywać długookresowy sygnał ruchu podłoża w otoczeniu inwestycji i wybierać miejsca do dodatkowego monitoringu.

**Produkt:** panel trendów przemieszczeń, porównanie obiektów i lista obszarów wymagających kontroli geodezyjnej/geotechnicznej.

**Dane i implementacja:** [European Ground Motion Service](https://land.copernicus.eu/en/products/european-ground-motion-service), analiza tabel/serii w pandas i GeoPandas. Własne serie InSAR: [MintPy](https://github.com/insarlab/MintPy), po przygotowaniu odpowiednich interferogramów przez osobny łańcuch przetwarzania.

**Konkretny moduł:** `GroundMotionScreening` łączy lokalizacje obiektów z punktami EGMS, zapisuje referencję produktu, jakość, epokę i składową obserwacji; wyznacza trend i jego niepewność. Nie należy traktować punktów EGMS jak pełnego, jednorodnego pola 3D przemieszczeń.

To nie jest różnica dwóch NMT. Modele wysokości nie służą do potwierdzania milimetrowych osiadań fundamentu. InSAR może mierzyć składową wzdłuż linii obserwacji satelity względem referencji; przeliczenie na ruch pionowy wymaga odpowiednich danych/założeń. Zmiany rozpraszacza i atmosfery także wpływają na interpretację.

**Uzasadnienie biznesowe:** cykliczny monitoring otoczenia i rozsądne kierowanie kosztowniejszych pomiarów in situ, bez przypisywania samemu screeningowi roli ekspertyzy konstrukcyjnej.

## A10. Zmiany terenu, hałdy, nasypy i obiekty przemysłowe

**Prosto:** porównujemy dwie daty i liczymy, gdzie materiał przybył lub ubył. Zastosowania to m.in. place budowy, odkrywki, składowiska i rekultywacja otoczenia infrastruktury.

**Produkt:** mapa zmian, objętości dodatnie/ujemne, wykryte anomalia i historia stanu obiektu.

**Implementacja:** wyrównanie rastrów w GDAL/[Rasterio](https://github.com/rasterio/rasterio), kontrola punktów odniesienia, analiza NumPy; dla chmur [PDAL](https://github.com/PDAL/PDAL). Różnicę liczy się dopiero po uzgodnieniu CRS, pionu, siatki, dat i pokrycia.

Po przygotowaniu zgodnych tablic i wspólnej maski:

```python
import numpy as np
change = after_m - before_m
cell_area_m2 = pixel_x_m * pixel_y_m
added_m3 = float(change[valid & (change > 0)].sum() * cell_area_m2)
removed_m3 = float(-change[valid & (change < 0)].sum() * cell_area_m2)
```

Nierozpoznane przesunięcie pionowe całego nalotu może wyglądać jak ogromna objętość robót. Dobrym rozszerzeniem jest próg istotnej zmiany, np. wyznaczony z błędów obu modeli po usunięciu biasu. Założenia niezależnych błędów i ich korelacja przestrzenna muszą być opisane — niepewność objętości nie jest prostą sumą dowolnie przyjętych „błędów na piksel”.

**Uzasadnienie biznesowe:** rozliczenia i monitoring postępu, o ile jakość oraz metoda pomiaru są odpowiednie do uzgodnionego celu.

# Suplement B. Dodatkowe, mniej oczywiste dane

Nie ma jednego publicznego, kompletnego zestawu dla wszystkich branż. Największą wartość często mają dane o strukturze, dacie i jakości pomiaru oraz własne dane operatora. Poniższa tabela wskazuje konkretne kierunki pozyskiwania. Portal jest punktem wejścia do katalogu, nie obietnicą stabilnego anonimowego API dla wszystkich produktów.

| Dane | Co wnoszą ponad NMT/NMPT | Źródło i sposób pozyskania | Proponowane biblioteki / integracja |
|---|---|---|---|
| Klasyfikowany LiDAR LAS/LAZ | Pojedyncze odbicia, grunt/roślinność/zabudowa; czasem intensywność i klasy specjalistyczne | [Geoportal](https://www.geoportal.gov.pl/): skorowidz WFS, metadane arkusza, link do pliku LAZ; klasy i gęstość sprawdzać w metadanych | [PDAL](https://github.com/PDAL/PDAL), [laspy](https://github.com/laspy/laspy) |
| Mesh 3D z teksturą | Fasady, bryła i wygląd otoczenia, lepsze wizualizacje/kolizje | Geoportal, katalog modeli siatkowych; pliki OBJ/tekstury, lokalne pokrycie zależne od projektu | [trimesh](https://github.com/mikedh/trimesh), [PyVista](https://github.com/pyvista/pyvista), [CesiumJS](https://github.com/CesiumGS/cesium) |
| Budynki CityGML LOD1/LOD2 | Bryły i dachy ze strukturą obiektową, a nie wyłącznie powierzchnia rastra | Geoportal, [katalog Budynki3D](https://opendata.geoportal.gov.pl/InneDane/Budynki3D/); dostępność wersji i LOD z katalogu | GDAL GMLAS/OGR; [citygml4j](https://github.com/citygml4j/citygml4j) dla większego łańcucha Java; Python: lxml do wybranych struktur |
| Skorowidze i daty nalotów/arkuszy | Informacja, czy NMT, NMPT i zdjęcia pochodzą z podobnego czasu | WFS/WMS skorowidzów Geoportalu + metadane produktu; schemat atrybutów przez DescribeFeatureType | [GeoPandas](https://github.com/geopandas/geopandas), requests, OGR; daty jako część manifestu |
| Zdjęcia lotnicze i dane orientacji/aerotriangulacji | Wgląd w geometrię zdjęcia i możliwość dokładniejszej wizualizacji/fotogrametrii | Geoportal, materiały zdjęć lotniczych/aerotriangulacji; zwykle pliki, nie pojedynczy WCS | [GDAL](https://github.com/OSGeo/gdal), pyproj; przetwarzanie fotogrametryczne jako osobny proces z kalibracją kamery |
| Obrazy intensywności LiDAR, wybrane CIR i archiwalne opracowania | Dodatkowa cecha materiału/roślinności i zmiany w czasie | Skorowidze Geoportalu, linki do rzeczywistych rastrów; obraz WMS służy do podglądu, nie zastępuje danych numerycznych | [Rasterio](https://github.com/rasterio/rasterio), NumPy, scikit-image; klasyfikacja po normalizacji i kontroli warunków nalotu |
| Ruchy gruntu EGMS | Długookresowe serie przemieszczeń / prędkości dla odpowiednich rozpraszaczy | [Copernicus EGMS](https://land.copernicus.eu/en/products/european-ground-motion-service); portal, produkty tabelaryczne/wektorowe, możliwe konto i warunki pobrania | pandas, GeoPandas; [MintPy](https://github.com/insarlab/MintPy) dla własnej serii InSAR, nie jako automatyczny czytnik gotowego CSV EGMS |
| Profile pogodowe i szeregi wiatru | Wymuszenie dla analiz energii zamiast wnioskowania o wietrze z samego terenu | [Copernicus Climate Data Store](https://cds.climate.copernicus.eu/), np. ERA5; API, konto, akceptacja warunków produktów | [cdsapi](https://github.com/ecmwf/cdsapi), xarray, windpowerlib, FLORIS |
| Geologia, osuwiska, otwory i wybrane dane geotechniczne | Ograniczenia posadowienia oraz kontekst, którego wysokość powierzchni nie opisuje | [PIG-PIB Geologia](https://geologia.pgi.gov.pl/); właściwe warstwy/usługi i metadane; część materiałów wymaga innych ścieżek dostępu | [GeoPandas](https://github.com/geopandas/geopandas), Shapely, OGR; przecięcia i zapytania przestrzenne, nie automatyczne określanie nośności |
| Głębokości/prędkości wody i elementy ochrony przeciwpowodziowej | Oficjalne scenariusze i warunki modelowania, nie tylko topografia | [Hydroportal / ISOK](https://isok.gov.pl/hydroportal.html); konkretne produkty i warunki pobrania z katalogu | [HydroMT-SFINCS](https://github.com/Deltares/hydromt_sfincs), GDAL/Rasterio, GeoPandas |
| Drzewostany i dane urządzeniowe lasu | Wiek/skład i kontekst wzrostu, przydatne w korytarzach energetycznych | [Bank Danych o Lasach](https://www.bdl.lasy.gov.pl/portal/); usługi/eksporty w zakresie danego produktu | [GeoPandas](https://github.com/geopandas/geopandas), PDAL; połączenie jednostek inwentaryzacyjnych z lokalnym CHM, bez udawania pomiaru każdego drzewa |
| Przeszkody i ograniczenia lotnicze | Ograniczenia wysokości dla turbin, masztów i zabudowy | [PANSA AIS](https://ais.pansa.pl/), właściwe publikacje AIP i warunki wykorzystania; często dokumenty/pliki zamiast WCS | [GeoPandas](https://github.com/geopandas/geopandas) / OGR + kontrolowane parsowanie tabel; sprawdzanie aktualności i rodzaju wysokości |
| Rzeczywista geometria sieci i eksploatacja | Przewody, słupy, temperatury/obciążenia, zwis, moce przyłączeniowe — klucz do wartości biznesowej | Dane operatora/klienta; publiczne informacje [PSE](https://www.pse.pl/dane-systemowe) mają inny zakres niż szczegółowy model sieci | [GeoPandas](https://github.com/geopandas/geopandas), GeoPackage/PostGIS, PDAL; oddzielny autoryzowany adapter do systemu operatora |

Dla materiałów archiwalnych i specjalistycznych zawsze sprawdź: obszar, datę pomiaru, licencję, układ poziomy i pionowy, jednostki, dokładność/gęstość oraz prawa do dalszego udostępniania. Nie zakładaj, że to, co widać w WMS, jest równocześnie dostępne anonimowo jako plik źródłowy. Brak dostępu do jednego produktu nie powinien blokować pozyskiwania innych, publicznych danych.

## B1. Jak dodać takie źródła do tej samej aplikacji

W obecnej wersji zakres jest celowo ograniczony do dwóch zasobów WCS. Dalsze produkty powinny mieć wspólny kontrakt adaptera, a nie dodatkowe instrukcje `if` w oknie.

Przykładowy projekt interfejsu — **propozycja**, nie istniejący moduł 1.1.0:

```python
from dataclasses import dataclass
from typing import Protocol

@dataclass
class Asset:
    identifier: str
    url: str
    bbox: tuple
    acquired_at: str | None
    horizontal_crs: str
    vertical_reference: str | None
    media_type: str
    license_url: str | None

class SourceAdapter(Protocol):
    def discover(self, aoi, preferences) -> list[Asset]: ...
    def estimate_bytes(self, asset: Asset) -> int | None: ...
    def download(self, asset: Asset, destination, progress, cancel): ...
    def validate(self, destination, asset: Asset) -> dict: ...
```

Ten skrót wykorzystuje składnię Pythona 3.10+; jeżeli nowe moduły mają działać także na Pythonie 3.9, zastąp `X | None` przez `Optional[X]`. Interfejs trzeba dostosować do rzeczywistych protokołów i potrzeb paginacji.

- `WcsAdapter`: małe numeryczne wycinki, jak obecnie.
- `WfsFileIndexAdapter`: najpierw obiekty skorowidza i atrybut z linkiem, potem pliki LAZ/GML/OBJ. Typy obiektów i nazwy pól odczytywać ze schematu, nie zgadywać.
- `StacAdapter`: wyszukiwanie scen/zasobów po geometrii, czasie, jakości i typie pliku; [pystac-client](https://github.com/stac-utils/pystac-client). Konkretna kolekcja i nazwy assetów muszą pochodzić z wybranego katalogu.
- `AuthenticatedArchiveAdapter`: kontrolowane pobieranie produktów wymagających konta, bez zapisywania haseł w kodzie lub raportach.
- `OperatorAdapter`: dane prywatnej sieci lub inwestycji, oddzielone od publicznego katalogu i od publicznego repozytorium.

Wspólny manifest powinien opisywać każdy pobrany artefakt: źródło, identyfikator produktu, datę pozyskania danych, datę pobrania, hash pliku, CRS, pion, jednostki, licencję, pokrycie i wynik walidacji. Obecny raport jest dobrym początkiem, ale nie zawiera jeszcze pełnej identyfikacji epoki pomiaru.

# Suplement C. Przykłady Pythona

Przykłady są samodzielnymi punktami startowymi analizy. Nie uruchamiają automatycznie pobierania wszystkich wymienionych danych. Produkty pochodne zapisuj w oddzielnym folderze, żeby indeks pobranych NMT/NMPT nie mieszał ich z materiałem źródłowym.

## C1. Najpierw mozaika i kontrola zgodności

Nie odejmuj tablic tylko dlatego, że obie mają rozszerzenie `.tif`. NMT 1 m i NMPT 0,5 m zwykle mają inne wymiary i granice kafli. Przed porównaniem trzeba uzgodnić projekcję, układ wysokościowy, piksel, zasięg, położenie siatki oraz maski braków. Zgodność pionu nie gwarantuje zgodności dat pomiaru.

Do lekkiej mozaiki można użyć VRT bez kopiowania wszystkich pikseli. Przykład zakłada pliki z metadanymi pionu zapisanymi przez wersję 1.1. Dla starszych plików najpierw potwierdź układ na podstawie ich metadanych źródłowych; nie dopisuj go na podstawie domysłu:

```python
from pathlib import Path
from osgeo import gdal

files = sorted(Path('dane/NMT').glob('NMT_PL-EVRF2007-NH_1m_*.tif'))
if not files:
    raise ValueError('Brak wejściowych plików')
for path in files:
    ds = gdal.Open(str(path))
    if ds is None or ds.GetMetadataItem('HEIGHT_SYSTEM') != 'PL-EVRF2007-NH':
        raise ValueError(f'Nieuzgodniony układ wysokościowy: {path.name}')
    ds = None
vrt = gdal.BuildVRT('nmt.vrt', [str(path.resolve()) for path in files], resolution='highest')
if vrt is None:
    raise RuntimeError('Nie udało się utworzyć mozaiki')
vrt.SetMetadataItem('HEIGHT_SYSTEM', 'PL-EVRF2007-NH')
vrt.FlushCache()
vrt = None
```

Przed włączeniem mieszanych rozdzielczości lub wielu dat zaprojektuj jawne reguły pierwszeństwa w obszarach nakładania. Nie dodawaj bezrefleksyjnie wszystkich wariantów EVRF/KRON i dat do jednej mozaiki.

## C2. nDSM, nachylenie, widoczność, radiolinia i siatka 3D

Pełny plik `terrain_examples.py` jest także w repozytorium pod `docs/examples/`. Funkcje z GDAL i NumPy sprawdzono na sztucznych rastrach. Funkcja PyVista jest przykładem wymagającym dodatkowego VTK/PyVista i nie była uruchamiana w tej weryfikacji.

Przykładowe wywołania:

```python
from terrain_examples import make_ndsm, terrain_slope, terrain_viewshed, radio_clearance

make_ndsm('nmt.vrt', 'nmpt.vrt', 'analizy/ndsm.tif')
terrain_slope('nmt.vrt', 'analizy/nachylenie_stopnie.tif')
terrain_viewshed('nmt.vrt', 'analizy/widocznosc_terenu.tif',
                x=637000, y=486000, observer_agl=120, radius=20000)
print(radio_clearance('profil.csv', frequency_ghz=3.5, mast_a_m=30, mast_b_m=30))
```

Folder `analizy` musi istnieć. Współrzędne są przykładowe i muszą leżeć w rzeczywistym obszarze rastra. Do `profil.csv` przygotuj kolumny `s_m,dtm_m,dsm_m` — odległość wzdłuż profilu i wysokości w jednym układzie. Profile należy próbkować gęsto względem rozmiaru przeszkód; pojedynczy piksel między próbkami może być pominięty.

W nDSM ujemne wartości nie są automatycznie zamieniane na zero, ponieważ mogą wskazywać niezgodność pomiarów lub zmianę terenu. Bilinear wyrównuje siatkę, ale może wygładzać ostre krawędzie; dla szacowania maksymalnej przeszkody trzeba dobrać metodę agregacji/resamplingu do celu. Powstały nDSM ma wysokości względne nad terenem, nie bezwzględne EVRF2007.

```python
"""Small analytical prototypes for correctly registered, metre-based height rasters.

Run with the GDAL/NumPy Python shipped with QGIS. These are analytical examples,
not additional features of plugin 1.1.0. Output files should use a separate folder.
"""
from pathlib import Path
import csv
import math

import numpy as np
from osgeo import gdal, osr


def open_metric_dem(path):
    ds = gdal.Open(str(path), gdal.GA_ReadOnly)
    if ds is None or ds.RasterCount != 1:
        raise ValueError('Oczekiwano jednokanałowego rastra wysokości')
    crs = osr.SpatialReference()
    if crs.ImportFromWkt(ds.GetProjection()) != 0 or not crs.IsProjected():
        raise ValueError('Oczekiwano poprawnego metrycznego CRS')
    if abs(crs.GetLinearUnits() - 1.0) > 1e-9:
        raise ValueError('Jednostką poziomą muszą być metry')
    gt = ds.GetGeoTransform()
    if abs(gt[2]) > 1e-9 or abs(gt[4]) > 1e-9 or gt[1] <= 0 or gt[5] >= 0:
        raise ValueError('Przykład wymaga regularnej siatki north-up')
    return ds


def heights_and_valid(ds):
    band = ds.GetRasterBand(1)
    values = band.ReadAsArray().astype(np.float32)
    valid = np.isfinite(values)
    nodata = band.GetNoDataValue()
    if nodata is not None and math.isfinite(nodata):
        valid &= values != nodata
    return values, valid


def write_float(path, reference, values, valid, product):
    target = gdal.GetDriverByName('GTiff').Create(
        str(path), reference.RasterXSize, reference.RasterYSize, 1, gdal.GDT_Float32,
        options=['TILED=YES', 'COMPRESS=DEFLATE', 'PREDICTOR=3'])
    if target is None:
        raise RuntimeError('Nie można utworzyć pliku wynikowego')
    target.SetGeoTransform(reference.GetGeoTransform())
    target.SetProjection(reference.GetProjection())
    target.SetMetadataItem('SOURCE_HEIGHT_SYSTEM', reference.GetMetadataItem('HEIGHT_SYSTEM') or '')
    target.SetMetadataItem('HEIGHT_REFERENCE', 'relative_above_ground')
    target.SetMetadataItem('PRODUCT', product)
    target.GetRasterBand(1).SetNoDataValue(-9999)
    target.GetRasterBand(1).WriteArray(np.where(valid, values, -9999).astype(np.float32))
    target.FlushCache()
    target = None


def make_ndsm(dtm_path, dsm_path, output):
    """DSM - DTM on the DTM grid; no implicit vertical-datum conversion."""
    dtm, dsm = open_metric_dem(dtm_path), open_metric_dem(dsm_path)
    height = dtm.GetMetadataItem('HEIGHT_SYSTEM')
    if not height or height != dsm.GetMetadataItem('HEIGHT_SYSTEM'):
        raise ValueError('Potwierdź i oznacz zgodny układ wysokościowy obu modeli')
    gt = dtm.GetGeoTransform()
    bounds = [gt[0], gt[3] + gt[5] * dtm.RasterYSize,
              gt[0] + gt[1] * dtm.RasterXSize, gt[3]]
    aligned = gdal.Warp('', dsm, format='MEM', dstSRS=dtm.GetProjection(),
                        outputBounds=bounds, width=dtm.RasterXSize, height=dtm.RasterYSize,
                        resampleAlg='bilinear', dstNodata=-9999, outputType=gdal.GDT_Float32)
    if aligned is None:
        raise RuntimeError('Nie udało się dopasować siatek')
    ground, valid_ground = heights_and_valid(dtm)
    surface, valid_surface = heights_and_valid(aligned)
    valid = valid_ground & valid_surface
    difference = surface - ground
    # Negative differences are retained for quality control rather than hidden.
    write_float(output, dtm, difference, valid, 'nDSM: NMPT-NMT')
    return {'valid_cells': int(valid.sum()), 'negative_cells': int(((difference < 0) & valid).sum())}


def terrain_slope(dtm_path, output):
    """Slope in degrees; not an assessment of soil bearing capacity."""
    ds = open_metric_dem(dtm_path)
    result = gdal.DEMProcessing(str(output), ds, 'slope', format='GTiff', scale=1.0,
                                computeEdges=True, creationOptions=['COMPRESS=DEFLATE'])
    if result is None:
        raise RuntimeError('Nie udało się obliczyć nachylenia')
    result = None


def terrain_viewshed(dtm_path, output, x, y, observer_agl=120, target_agl=1.7, radius=20000):
    """Terrain-only visibility. Buildings, tree occlusion and weather are not modeled."""
    ds = open_metric_dem(dtm_path)
    # For long distances the input must cover the entire analysis neighborhood.
    result = gdal.ViewshedGenerate(
        ds.GetRasterBand(1), 'GTiff', str(output), ['COMPRESS=DEFLATE'],
        float(x), float(y), float(observer_agl), float(target_agl),
        255, 0, 0, 0, 0.87, gdal.GVM_Edge, float(radius))
    if result is None:
        raise RuntimeError('Nie udało się obliczyć widoczności')
    result = None


def radio_clearance(profile_csv, frequency_ghz=3.5, mast_a_m=30, mast_b_m=30, effective_earth_factor=4/3):
    """Geometric line/Fresnel clearance, not a complete radio propagation model.

    CSV columns: s_m, dtm_m, dsm_m; heights in one vertical datum, no missing values.
    """
    with Path(profile_csv).open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    s = np.array([float(row['s_m']) for row in rows])
    ground = np.array([float(row['dtm_m']) for row in rows])
    surface = np.array([float(row['dsm_m']) for row in rows])
    if len(s) < 3 or not np.all(np.isfinite([s, ground, surface])) or s[0] != 0 or np.any(np.diff(s) <= 0):
        raise ValueError('Profil musi być kompletny, rosnący i zaczynać się od 0 m')
    if frequency_ghz <= 0 or effective_earth_factor <= 0:
        raise ValueError('Częstotliwość i współczynnik Ziemi muszą być dodatnie')
    length = s[-1]
    z_a, z_b = ground[0] + mast_a_m, ground[-1] + mast_b_m
    line = z_a + (z_b - z_a) * s / length
    wavelength = 299792458.0 / (frequency_ghz * 1e9)
    fresnel = np.sqrt(wavelength * s * (length - s) / length)
    earth_bulge = s * (length - s) / (2 * 6371000 * effective_earth_factor)
    reserve = line - (surface + earth_bulge + 0.6 * fresnel)
    return {'minimum_reserve_m': float(reserve.min()), 'sample_count': len(s),
            'all_sampled_points_clear': bool(np.all(reserve > 0))}


def make_terrain_mesh(dtm_path, output_vts, stride=4):
    """Requires pyvista (VTK); intentionally rejects holes rather than inventing elevations."""
    import pyvista as pv
    ds = open_metric_dem(dtm_path)
    z, valid = heights_and_valid(ds)
    if not np.all(valid[::stride, ::stride]):
        raise ValueError('Wybierz wycinek bez NoData lub zaplanuj jawne uzupełnienie dziur')
    gt = ds.GetGeoTransform()
    rows = np.arange(0, ds.RasterYSize, stride)
    cols = np.arange(0, ds.RasterXSize, stride)
    x, y = np.meshgrid(gt[0] + (cols + 0.5) * gt[1], gt[3] + (rows + 0.5) * gt[5])
    grid = pv.StructuredGrid(x, y, z[::stride, ::stride])
    grid.save(str(output_vts))
    return grid
```

## C3. PV: przykład obliczenia, nie prognoza produkcji

W oddzielnym środowisku analitycznym zainstaluj `pvlib` i pandas. Nie podmieniaj przypadkowo NumPy/GDAL wewnątrz działającego QGIS; wersje binarne muszą do siebie pasować. Kod poniżej jest sprawdzonym przykładem modelu bezchmurnego dnia, bez przeszkód. Nie prezentuj jego wyniku jako produkcji rocznej ani gwarantowanego uzysku inwestycji.

```python
"""PV illustration for a cloud-free day; not an annual energy yield forecast."""
import pandas as pd
import pvlib


def clear_sky_example():
    site = pvlib.location.Location(52.0, 21.0, tz='Europe/Warsaw', altitude=110)
    times = pd.date_range('2026-06-21', periods=96, freq='15min', tz=site.tz)
    sun = site.get_solarposition(times)
    sky = site.get_clearsky(times)
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=30, surface_azimuth=180,
        solar_zenith=sun['apparent_zenith'], solar_azimuth=sun['azimuth'],
        dni=sky['dni'], ghi=sky['ghi'], dhi=sky['dhi'])
    # An illustrative constant efficiency factor; no temperature/shading/snow model.
    power_kw = 10.0 * poa['poa_global'].fillna(0) / 1000 * 0.85
    return pd.DataFrame({'poa_W_m2': poa['poa_global'], 'illustrative_power_kW': power_kw})


if __name__ == '__main__':
    result = clear_sky_example()
    result.to_csv('pv_bezchmurny_dzien.csv')
    print('Ilustracyjna energia 10 kWp [kWh]:', result['illustrative_power_kW'].sum() * 0.25)
```

Weryfikacja przykładu: wykonano serię 96 kroków po 15 minut. Wynik ilustracyjny wyniósł około 65,2 kWh dla zdefiniowanych 10 kWp i założeń tego konkretnego bezchmurnego dnia. To kontrola uruchomienia kodu, nie ocena rzeczywistej instalacji. Kolejny etap: rzeczywiste dane promieniowania, model temperatury/modułów/falownika i geometria zacienienia.

## C4. PDAL: wysokość punktów nad gruntem

Pipeline do normalizacji chmury z użyciem NMT. Wymaga instalacji PDAL z właściwymi sterownikami LAZ i danych w zgodnych układach. Nie uruchamiano go na rzeczywistym LiDAR-ze w tym zadaniu.

```python
import json
from pathlib import Path

pipeline = {
    'pipeline': [
        {'type': 'readers.las', 'filename': 'chmura.laz'},
        {'type': 'filters.expression',
         'expression': 'Classification != 7 && Classification != 18'},
        {'type': 'filters.hag_dem', 'raster': 'nmt.tif'},
        {'type': 'writers.las', 'filename': 'punkty_z_wysokoscia_nad_gruntem.laz',
         'extra_dims': 'HeightAboveGround=float32'}
    ]
}
Path('normalizacja.json').write_text(json.dumps(pipeline, indent=2), encoding='utf-8')
```

Następnie: `pdal pipeline normalizacja.json`. Wysokość względna pojawia się w dodatkowym wymiarze `HeightAboveGround`; nie oznacza to automatycznej zamiany oryginalnego Z na wysokość względną. Wykorzystanie klasyfikacji wymaga sprawdzenia, jakie klasy rzeczywiście zawiera plik.

## C5. Kierunki spływu i akumulacja

Prototyp z biblioteką pysheds. Przed wykonaniem potrzebny jest odpowiedni NMT, ciągły obszar zlewni i analiza wpływu obiektów hydrotechnicznych. Ten fragment nie był wykonywany na danych rzeczywistych w tym zadaniu; API trzeba dopasować do zainstalowanej wersji biblioteki.

```python
from pysheds.grid import Grid

grid = Grid.from_raster('nmt.tif')
dem = grid.read_raster('nmt.tif')
filled = grid.fill_pits(dem)
filled = grid.fill_depressions(filled)
prepared = grid.resolve_flats(filled)
directions = (64, 128, 1, 2, 4, 8, 16, 32)
flow = grid.flowdir(prepared, dirmap=directions)
accumulation = grid.accumulation(flow, dirmap=directions)
grid.to_raster(accumulation, 'akumulacja_komorek.tif')
```

Wynik akumulacji to liczba/udział komórek dopływających według modelu, a nie głębokość wody w metrach. Do scenariusza powodziowego potrzebne są co najmniej wymuszenie opadowe/stan wody, czas, warunki brzegowe, parametry podłoża i właściwy model hydrauliczny.

## C6. Skrócona kontrola własnego raportu

Ten skrypt wykorzystuje standardowego Pythona i nie wypisuje ścieżek ani geometrii. Uruchom: `python validate_report.py report.json`. Sumowanie `output_bytes` opisuje rozmiary raportowanych najlepszych wariantów; przy kilku zachowanych alternatywach może nie obejmować wszystkich plików. Dla pełnego inwentarza odczytaj unikalne `files` i ich aktualne rozmiary na dysku.

```python
"""Read a plugin report without exposing local paths or geometry."""
import json
import sys
from collections import Counter
from pathlib import Path


def summarize(path):
    report = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    tiles = report.get('tiles', [])
    return {
        'state': report.get('state'),
        'planned': report.get('planned_tiles'),
        'processed': len(tiles),
        'counts': dict(Counter(t['status'] for t in tiles)),
        'nodata_cells': sum(t.get('nodata_cells', 0) for t in tiles),
        'transfer_MB': round(report.get('transfer_bytes', 0) / 1e6, 2),
        'output_MB': round(sum(t.get('output_bytes', 0) for t in tiles) / 1e6, 2),
        'recovered_errors': sum(len(t.get('errors', [])) for t in tiles),
        'catalog_errors': len(report.get('catalog_errors', [])),
        'resolutions': report.get('resolutions_m'),
        'height_systems': sorted({t['height'] for t in tiles if t.get('height')}),
    }


if __name__ == '__main__':
    print(json.dumps(summarize(sys.argv[1]), ensure_ascii=False, indent=2))
```

## C7. Co dokładnie zweryfikowano w przykładach

| Przykład | Sposób sprawdzenia | Wynik i granica |
|---|---|---|
| Spójność raportu | Dostarczony JSON, dziennik i GeoJSON | 29 wyników, zgodne liczniki, NoData 0; bez samych rastrów klienta |
| nDSM | Sztuczny NMT 1 m i NMPT 0,5 m, znana różnica +10 m | Wnętrze wyniku 10,0 m, poprawne wyrównanie siatki |
| Nachylenie | Płaszczyzna o znanych pochodnych 0,1 i 0,2 | Około 12,6045°, zgodnie z obliczeniem analitycznym |
| Widoczność terenowa | Sztuczny ciągły NMT, mały promień | Powstał raster z widocznymi komórkami; to test funkcjonalny, nie walidacja modelu optycznego 20 km |
| Radiolinia | Profil płaski i profil z przeszkodą | Pierwszy miał dodatni, drugi ujemny zapas geometryczny |
| PV | Model bezchmurnego dnia, pvlib i pandas | Kod wykonany; brak danych pogodowych rzeczywistej inwestycji |
| PyVista, PDAL, hydrologia, FLORIS, InSAR | Dobór bibliotek i prototypy | Nie uruchomiono tych pełnych integracji w tym zadaniu |
| Linki GitHub do bibliotek | Żądania HTTP do wskazanych repozytoriów | Repozytoria istniały podczas przygotowania; nie jest to audyt ich jakości ani obietnica zgodności każdej przyszłej wersji |

Nie uruchamiano kosztownej pełnej analizy 20 km. Dla dużych obszarów przykłady wczytujące całą tablicę należy zmienić na przetwarzanie oknami, z odpowiednim marginesem dla algorytmów sąsiedztwa. Nie należy uruchamiać ich bezpośrednio na wielomiliardowej mozaice w pamięci.

# Suplement D. Plan rozwoju produktu

## D1. Pierwszy etap: jakość, wydajność i przewidywalność

1. **Manifest źródła i dat pomiaru.** Pobieraj metadane skorowidza, datę nalotu/produkcji i dokładność; pokaż brak tej informacji jako brak, a nie wymyśloną datę.
2. **Jawne parowanie NMT/NMPT.** Sprawdzaj daty, układ, siatkę i pokrycie przed nDSM; zapisz raport zgodności.
3. **Wznowienie z inwentarza.** Raportuj sumy SHA-256 plików i odróżniaj zgodność parametrów od integralności zawartości. Rozważ TTL lub wykrywanie aktualizacji źródła.
4. **Mniejszy transfer.** Sprawdź możliwość pobierania oryginalnych skompresowanych arkuszy albo rzeczywiście numerycznego GeoTIFF/COG, zawsze kontrolując typ danych i wartości. Nie wracaj do wizualizacji Byte tylko dlatego, że jest mniejsza.
5. **Szacunek przed startem.** Liczba pikseli, kafli, zakres rozdzielczości i orientacyjny transfer; użytkownik ma widzieć koszt wyboru 0,5 m względem 1 m.
6. **Lepsza obsługa HTTP.** W przyszłości obsłuż `Retry-After` i rozdziel błędy sieci od błędów merytorycznych; nie zwiększaj bez końca równoległości.
7. **Skalowanie geometrii.** Dla bardzo wielu obiektów grupuj nakładające się bufory i sprawdzaj wydajność zarówno planowania, jak i serializacji raportów.

## D2. Drugi etap: mały, użyteczny pakiet analiz

Najbardziej praktyczna kolejność dla wysokich obiektów i energetyki:

1. Wspólna mozaika, kontrola siatek i nDSM.
2. Nachylenia, profile i prosta terenowa widoczność wariantów wysokości.
3. Raport dla jednej inwestycji: parametry, źródła, daty, mapy, ograniczenia, pliki wynikowe.
4. LiDAR + roślinność albo szczegółowe zacienienie — zależnie od pierwszego klienta.
5. Dopiero potem dane wiatrowe, modele energii, hydrologia lub InSAR.

Każdy moduł powinien przyjmować wyraźny kontrakt danych wejściowych i odmawiać obliczeń dla niezgodnego pionu/siatki. Wynik powinien mieć wersję algorytmu, parametry i listę źródeł. Do powtarzalnego uruchamiania poza oknem warto wprowadzić `QgsProcessingProvider` z osobnymi algorytmami, a do większych zadań opcjonalny CLI/worker.

## D3. Trzeci etap: produkt dla konkretnej branży

| Produkt startowy | Pierwszy klient | Minimalny zakres pilota | Kryterium powodzenia |
|---|---|---|---|
| Wysoki obiekt — screening lokalizacji | Projektant masztu, turbiny, komina | Kilka lokalizacji i wysokości, teren, profil, widoczność | Wynik odtwarzalny i zgodny z kontrolnymi punktami terenowymi |
| Priorytety roślinności | Operator infrastruktury | Znany odcinek z wiarygodną geometrią i nalotem | Trafność identyfikacji miejsc wymagających inspekcji |
| Dachy PV z przeszkodami | Instalator / właściciel portfela | Kilka dachów ze skanem i danymi pogodowymi | Zgodność geometrii i porównanie z kontrolą na obiekcie |
| Monitoring otoczenia | Zarządca infrastruktury | Dostępna seria EGMS + punkty kontroli | Jawna referencja, jakość i zasadna kwalifikacja sygnału |
| Cyfrowa scena inwestycji | Deweloper / konsultant | Jeden obiekt i mały obszar z mesh/CityGML | Płynna prezentacja, spójne wysokości, odtwarzalny eksport |

Wycenę można oprzeć na przygotowaniu projektu i cyklicznej aktualizacji albo na portfelu obiektów. Najpierw uzgodnij mierzalny wynik i dane kontrolne; sama liczba pobranych gigabajtów nie jest miarą wartości dla klienta.

## D4. Granice wersji 1.1.0, których nie należy ukrywać

- Brak automatycznego doboru epoki/roku danych.
- Brak transformacji pionowej EVRF2007 ↔ KRON86.
- Brak automatycznego scalania częściowych alternatyw w jeden model.
- Cache nie wykrywa sam, że źródło opublikowało nowszą wersję tego samego obszaru.
- Indeksy obejmują bezpośrednie pliki folderu, nie podfoldery; wymagają aktywnej wtyczki do synchronizacji.
- Nazwany „native” piksel jest informacją z DescribeCoverage, nie certyfikatem dokładności pionowej czy jednorodności pomiarów całego kraju.
- Brak rozbudowanego limitu wolnego miejsca przed startem i pełnego manifestu licencji/epok.
- QGIS 4 oraz pełna macierz Windows/macOS nie zostały tutaj zweryfikowane.
- Przykłady ładujące całe tablice są przeznaczone do małych wycinków; analizy produkcyjne muszą działać blokowo.

# Źródła i punkty odniesienia

## Kod i protokoły

- [Kod wtyczki](https://github.com/misinskimichal/pobieracz_danych_gugik/tree/codex/nmt-nmtp-sciagacz/nmt_nmpt_downloader).
- [Oryginalny Pobieracz danych GUGiK — materiał odniesienia](https://github.com/envirosolutionspl/pobieracz_danych_gugik).
- [Dokumentacja PyQGIS](https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/), szczególnie zadania i integracja wtyczek.
- [OGC WCS](https://www.ogc.org/standard/wcs/), [OGC WFS](https://www.ogc.org/standard/wfs/), [STAC](https://stacspec.org/).
- [GDAL](https://gdal.org/), [repozytorium GDAL](https://github.com/OSGeo/gdal).

## Dane i analizy

- [Geoportal — dane i usługi](https://www.geoportal.gov.pl/), [strona NMPT wskazana w materiałach](https://www.geoportal.gov.pl/en/data/digital-surface-model-dsm/).
- [Copernicus EGMS](https://land.copernicus.eu/en/products/european-ground-motion-service), [CDS](https://cds.climate.copernicus.eu/).
- [PVGIS JRC](https://re.jrc.ec.europa.eu/pvg_tools/en/).
- [PIG-PIB Geologia](https://geologia.pgi.gov.pl/), [ISOK Hydroportal](https://isok.gov.pl/hydroportal.html), [Bank Danych o Lasach](https://www.bdl.lasy.gov.pl/portal/), [PANSA AIS](https://ais.pansa.pl/).

Repozytoria bibliotek wskazano przy każdym zastosowaniu. Nazwy i adresy repozytoriów GitHub sprawdzono podczas przygotowania dokumentacji. Repozytorium FLORIS przekierowuje obecnie z NREL do NatLabRockies, a pysheds z mdbartos do organizacji pysheds; w dokumencie użyto adresów docelowych. Dostępność danych zależy od produktu, regionu, okresu i warunków dostawcy — nie jest weryfikowana samym działającym odnośnikiem do portalu.
