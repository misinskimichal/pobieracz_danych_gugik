# NMT i NMTP ściągacz — 1.1.0

Wtyczka QGIS 3.28–3.x do pobierania numerycznych NMT i NMPT dla bufora wokół obiektów warstwy. Wynik: skompresowane GeoTIFF Float32 w EPSG:2180. Działa niezależnie od oryginalnego „Pobieracza danych GUGiK”.

## Instalacja i aktualizacja

QGIS → **Wtyczki → Zarządzanie wtyczkami → Zainstaluj z ZIP** → wybierz `NMT i NMTP ściągacz-1.1.0.zip`. Nie rozpakowuj pliku. Przy aktualizacji zamknij poprzednie zadania pobierania i uruchom ponownie QGIS, aby wymienić załadowane moduły. W razie potrzeby odinstaluj poprzednią wersję wtyczki i zainstaluj nowy ZIP. Pobrane dane i raporty nie są usuwane.

Sprawdzono QGIS 3.40.6 / Qt5 / Python 3.13 / Linux. Windows i macOS nie są tutaj dostępne do testów; podstawowe pobieranie wersji 1.0 działało w dostarczonym przez użytkownika raporcie z Windows. QGIS 4 nie jest obsługiwany. Potrzebne są biblioteki standardowej instalacji QGIS: GDAL/OGR, NumPy, lxml i requests. Nie instaluj `qgis` przez pip.

## Ustawienia obszaru

Wybierz warstwę wektorową, opcjonalnie **Tylko zaznaczone obiekty**, i promień w metrach. Dla 20 km wpisz **20000**. Bufor powstaje wokół geometrii, nie centroidu, po przeliczeniu do EPSG:2180. Dla punktów i linii promień musi być większy od zera. Nakładające się bufory nie powodują pobierania duplikatów kafli. Każdy plik obejmuje pełny kafel, także poza buforem przy jego granicy.

## Osobne rozdzielczości NMT i NMPT

Każdy zasób ma własny folder, preferowany piksel, checkbox **Tylko wybrana rozdzielczość**, układ wysokościowy i zgodę na użycie drugiego układu.

**Sprawdź dostępne rozdzielczości i układy** odpytuje DescribeCoverage WCS i aktualizuje listy wariantów. Można także wpisać preferowaną wartość w metrach. Dostępność jest sprawdzana ponownie przy pobieraniu. Przykładowo: NMT 1 m, NMPT 0,5 m w EVRF2007. Są to rozdzielczości źródłowe podane przez usługę, a nie nowe pomiary wygenerowane przez przeliczenie rastra.

- Bez **Tylko wybrana** wtyczka wybiera dostępny wariant o najmniejszej różnicy względem preferencji; przy remisie wybiera drobniejszy piksel. Gdy wybrany wariant ma braki lub błąd, sprawdza kolejne dostępne warianty.
- Z **Tylko wybrana** dopuszczana jest wyłącznie dokładnie taka rozdzielczość; jeśli jej nie ma, odpowiedni kafel/zadanie zasobu trafia do raportu jako niedostępny. Drugi zasób może działać dalej.
- **Źródłowa — najlepsza dostępna** preferuje najmniejszy dostępny piksel w wybranym układzie wysokościowym.
- Ustawienie 2 m w wersji 1.0 oznaczało przeliczenie siatki, nie osobny produkt źródłowy. W wersji 1.1 preferencja 2 m przy dostępnych źródłach 1 m i 5 m wybierze 1 m, chyba że włączysz tryb ścisły. Może to zwiększyć transfer względem starego przeliczenia na 2 m.
- Dodatkowy endpoint NMT GRID5 jest sprawdzany, ale jeżeli zwraca błąd lub odmowę dostępu, nie jest przedstawiany jako dostępny. Jego niedostępność nie blokuje publicznych wariantów GRID1. Nie są wymagane nowe hasła.

Faktyczny piksel jest zapisywany w nazwie rastra, indeksie i raporcie. Jeśli warianty mają różne rozdzielczości, siatka przestrzenna kafli jest wyrównywana do ich wspólnego kroku; liczba pikseli kafla może się nieznacznie zmienić.

## Osobne układy wysokościowe

Domyślnie każdy zasób preferuje **PL-EVRF2007-NH**. To domyślny wybór tej wtyczki dla współczesnych danych; dostępność konkretnego produktu/obszaru jest sprawdzana, a nie zakładana. Można oddzielnie wybrać **PL-KRON86-NH** dla NMT i NMPT.

Checkbox **Przy brakach sprawdź też drugi układ** jest domyślnie wyłączony. Po jego włączeniu najpierw sprawdzane są warianty preferowanego układu, a następnie drugiego. W razie częściowego pokrycia wtyczka zachowuje poprawne pliki i wybiera do podsumowania wariant z największym pokryciem. Zamienniki, ich rozdzielczość, rzeczywisty układ i wszystkie zachowane pliki są zapisane w `alternatives` / `files` w JSON.

**Wtyczka nie przelicza wysokości pomiędzy EVRF2007 i KRON86 i nie scala ich w jeden model.** Różne układy pozostają w oddzielnych plikach z oznaczeniem w nazwie i metadanych; indeks ma pole `uklad_wys`. Jeśli potrzebujesz jednorodnego modelu wysokościowego, nie dopuszczaj drugiego układu lub przelicz wysokości właściwą metodą poza wtyczką. Na granicy kafli z różnych wariantów mogą wystąpić różnice wysokości lub czasu pomiaru; dostępność nie stanowi dowodu zgodności modeli.

## Pobieranie i pokazywanie na mapie

Ustaw różne foldery NMT i NMPT oraz folder raportów. Kliknij **Pobierz**. Przetwarzanie działa w tle: etap, postęp kafli, aktywne transfery, MB, prędkość średnia i szacunkowe ETA. MB = 1 000 000 bajtów. Pozostałe MB i ETA są szacowane na podstawie zakończonych transferów, a licznik pobranych bajtów obejmuje ponowienia. Przy alternatywnych wariantach szacunki mogą się zmienić.

Po pobraniu kliknij **Pokaż pobrane rastry na mapie**. Dodaje to poprawnie zapisane i ponownie użyte rastry do grup **Rastry NMT** i **Rastry NMPT**; ścieżki już obecne w projekcie nie są dodawane ponownie. Widok jest ustawiany na obszar wyników. Pliki są dodawane partiami, aby QGIS zachował responsywność. Bez kliknięcia rastry nie są automatycznie dodawane.

**Ukryj** nie przerywa pobierania. **Anuluj** zachowuje ukończone pliki i raport. Aktywne połączenie może czekać do 90 s na dane. Domyślnie pobierane są dwa kafle naraz; można wybrać 1–4 pobrania i 512/1024/2048 pikseli kafla. Duży obszar i małe piksele oznaczają miliardy wartości; transfer numerycznego ASCII jest większy niż rozmiar skompresowanych GeoTIFF-ów.

## Automatyczne indeksy pobranych kafli

Po rozpoczęciu pobierania powstają **Pobrane kafle NMT** i **Pobrane kafle NMPT**. Można utworzyć je także bez pobierania przez **Pokaż / odśwież indeksy folderów**, wskazując istniejące foldery.

- Trwałe indeksy GeoPackage znajdują się w folderach danych: `.nmt_nmpt_index_NMT.gpkg` i `.nmt_nmpt_index_NMPT.gpkg`. Nie usuwaj ich, jeżeli mają być częścią zapisanego projektu.
- Warstwy pokazują obrysy rzeczywistych plików. Tabela zawiera nazwę i ścieżkę, zasób, piksel w metrach, rzeczywisty układ wysokościowy i MB. Obrys oznacza plik na dysku, nie gwarantuje pełnego pokrycia ważnymi pikselami; dokładne braki są w maskach raportu.
- Obserwacja folderu wykrywa dodanie/usunięcie pliku; aktualizacja jest grupowana z opóźnieniem około 0,75 s. Dodatkowy skan co 15 s wykrywa podmiany plików, także bez zdarzenia systemowego. Sieciowe dyski mogą zgłaszać zdarzenia z opóźnieniem.
- Skan działa w tle, czyta tylko nagłówki nowych/zmienionych rastrów i nie wczytuje wszystkich pikseli. Geometrie indeksu są aktualizowane przyrostowo.
- Po zapisaniu i ponownym otwarciu projektu synchronizacja wznawia się, gdy wtyczka jest włączona. Po wyłączeniu wtyczki zachowane warstwy indeksów nadal można oglądać, ale nie są synchronizowane. Usunięcie warstwy indeksu z projektu zatrzymuje jej obserwację; przycisk może ją ponownie dodać.
- Uwzględniane są pliki `.tif`, `.tiff` i `.asc` bezpośrednio w wybranym folderze, również pobrane wersją 1.0. Podfoldery i tymczasowe pliki są pomijane. Raster musi mieć czytelną georeferencję i CRS. Problemy skanowania są w panelu komunikatów QGIS, zakładka „NMT / NMPT — indeks”.

## Odporność i raporty

Gotowe pliki są zapisywane atomowo po kontroli odczytu, wymiarów i georeferencji; transfery są strumieniowe, a TLS pozostaje weryfikowany. Prawidłowe istniejące pliki o zgodnej sygnaturze są ponownie używane. Wyłącz pomijanie istniejących plików, aby odświeżyć dane opublikowane przez GUGiK. Obce/niespójne pliki nie są nadpisywane. Blokada `.nmt_nmpt_downloader.lock` chroni folder przed drugim zadaniem; po awarii usuń ją dopiero po upewnieniu się, że żadne pobieranie nie działa.

Każde uruchomienie tworzy `raport_DATA_ID`:

- `report.md`: podsumowanie, braki i zamienniki.
- `report.json`: ustawienia per zasób, rozpoznany katalog WCS i błędy jego odpytywania, każdy kafel, warianty, faktyczny piksel/układ, zachowane pliki i liczniki transferu. BBOX ma kolejność xmin/ymin/xmax/ymax w EPSG:2180.
- `events.jsonl`: bieżący dziennik zdarzeń.
- `obszar.geojson`: bufory w EPSG:4326.
- `obszary_problemowe.geojson`: obszary diagnostyczne kafli z brakami/błędami/anulowaniem, nie dokładne granice dziur.
- `masks/*_braki.tif`: maski dokładnych braków NoData wewnątrz żądanego obszaru; 1 = brak, 0 = poza brakami, EPSG:2180. Liczone są środki pikseli.

Brak danych lub błąd kafla nie przerywa pozostałych pobrań. `missing` oznacza NoData; `failed` oznacza niezweryfikowany obszar z powodu błędu, nie dowiedziony brak danych. Powód usługi jest zachowywany bez wymyślania przyczyn. Stany `downloaded`, `reused`, `partial`, `canceled` i `outside_pixels` opisują pobrane, ponownie użyte, częściowe, anulowane i obszary mniejsze od piksela. Maksymalnie trzy próby na wariant; trwałe HTTP 4xx poza 408/429 nie są ponawiane.

## Źródła, kod i walidacja

WCS GRID1: `https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMT/GRID1/WCS/DigitalTerrainModel` i `https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMPT/GRID1/WCS/DigitalSurfaceModel`; dodatkowy katalog NMT GRID5 jest sprawdzany pod analogiczną ścieżką GRID5. Zasoby `DTM_PL-…` i `DSM_PL-…`. Pobierany jest numeryczny `image/x-aaigrid` WCS 1.0.0 i lokalnie konwertowany do GeoTIFF Float32; testowane `image/tiff` WCS 2.0.1 zwracało Byte, więc nie używamy go do wysokości. Brak wyboru roku/archiwalnego arkusza.

Kod: `core.py` — geometrie/rastry; `catalog.py` — wybór wariantu; `engine.py` — transfery/raporty; `coverage.py` — indeksy/synchronizacja/mapa; `plugin.py` — UI i QgsTask. Testy: `tests_nmt_nmpt/test_downloader.py` w repozytorium. Testy sprawdzają m.in. osobne ustawienia, najbliższą/ścisłą rozdzielczość, drugi układ, zgodne zasięgi wariantów, NoData, HTTP 503/404, cache, anulowanie, dopisywanie/usuwanie/podmianę kafli, dodawanie rastrów oraz odtworzenie synchronizacji po zapisaniu projektu. Małe rzeczywiste żądania NMT 1 m i NMPT 0,5 m także zweryfikowano; pełnego obszaru 20 km nie pobierano.

Licencja: GPL-3.0, plik `LICENSE`.
