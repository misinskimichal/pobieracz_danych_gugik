# NMT i NMTP ściągacz — Atlas widoczności 2.0.0

Jeden formularz do pobierania NMT/NMPT i tworzenia **map widoczności całych kół wokół turbin**. Obserwatorzy nie są wymagani. Każdy model ma własny promień i krok mapy. Wynik pokazuje liczbę widocznych turbin, trzy wysokości wirnika, niepewność danych i opcjonalnie ekspozycję dróg oraz zabudowy.

## Instalacja

QGIS → **Wtyczki → Zarządzanie wtyczkami → Zainstaluj z ZIP** → `NMT i NMTP ściągacz-2.0.0.zip`. Nie rozpakowuj. Zakończ wcześniejsze zadania i uruchom QGIS ponownie po aktualizacji. W razie potrzeby odinstaluj poprzednią wersję i zainstaluj nowy ZIP. Oddzielne foldery danych pozostają na dysku.

QGIS 3.28–3.x, Python >=3.9; sprawdzone QGIS 3.40.6 / Qt5 / GDAL 3.10.3 / Linux. Windows i macOS nie są dostępne tutaj do testów. QGIS 4 nie jest obsługiwany. Biblioteki środowiska QGIS: PyQGIS, GDAL/OGR, NumPy, requests i lxml, bez osobnego serwera, GRASS czy Open3D.

## Atlas krok po kroku

1. Otwórz wtyczkę. Pozostaw tryb **Pobierz potrzebne dane i utwórz atlas widoczności**.
2. Wybierz punktową warstwę turbin, opcjonalnie tylko zaznaczone obiekty. Podaj wysokość piasty nad gruntem i średnicę wirnika albo pola z wartościami w metrach. Puste pole oznacza stałą wartość z lewej.
3. Ustaw oko w otoczeniu, domyślnie 1,7 m ponad gruntem NMT. Mapa odpowiada, skąd widać turbinę na właściwej wysokości; nie jest widokiem z gruntu pod turbiną.
4. NMT i NMPT włączasz osobno. Każdy ma własny **promień koła** i **krok mapy [m]**. Domyślnie NMT 20000 m / 10 m, NMPT 1000 m / 1 m. NMPT może mieć np. 650, 1000, 1500 m lub własną wartość; krok od 0,5 m. NMT ustala też poziom gruntu dla NMPT, nawet gdy wyłączysz mapę NMT.
5. Ustaw foldery NMT, NMPT i atlasów tylko raz. Można użyć danych poprzedniej wersji. Ustawienia źródeł po rozwinięciu pozwalają wybrać preferowany piksel danych, tryb ścisły i układ wysokościowy każdego modelu.
6. **Ważne miejsca z projektu** są opcjonalne: drogi, zabudowa/działki i obserwatorzy. Bez nich nadal powstaną pełne mapy kół. Służą do oceny ekspozycji i prezentacji; wysokości przeszkód pochodzą z modeli, nie z samego obrysu działki.
7. Automatyczne pobieranie wybiera dostępne dane i ponownie używa zgodnych kafli. Odznacz je dla pracy tylko na lokalnych folderach. Na pierwszą próbę wybierz jedną turbinę i małe koła, np. NMT 1000 m / 5 m i NMPT 650 m / 1 m, szczególnie bez cache.
8. Kliknij **Utwórz atlas widoczności**. Postęp obejmuje pliki, MB, prędkość, szacowane pozostałe MB/ETA, bieżącą turbinę i wysokość wirnika. **Ukryj** pozwala pracować dalej. **Anuluj** zachowuje ukończone pliki; aktywne połączenie może czekać do 90 s.
9. Po zakończeniu atlas pojawi się w projekcie, jeśli pozostawisz tę opcję. Domyślnie widoczny jest NMPT; przełącz grupę na NMT do porównania. W grupie jest też początkowo wyłączona warstwa zakresu widocznego wirnika. Opcjonalny PDF/PNG/HTML zawiera stronę każdego modelu, legendę, skalę, granice i podsumowanie. Korzysta z widocznych podkładów projektu, np. ortofotomapy; bez nich z cieniowania terenu.

## Znaczenie map

- **Ile turbin widać:** liczba turbin, dla których widoczny jest najwyższy punkt zasięgu łopaty; 0 to brak potwierdzonej widoczności, 65535 poza analizą.
- **Zakres wirnika:** brak / górny zasięg łopaty / także piasta / także dolny zasięg / nierozstrzygnięte. To trzy punkty, nie procent widocznej powierzchni łopat.
- **Jakość:** niepewna trasa, brak danych w miejscu obserwacji, oko pod dachem/koroną albo model kompletny. Przy niepewności liczba potwierdzonych turbin jest dolnym ograniczeniem.
- **Drogi:** odcinki do 50 m pokolorowane według udziału próbek z widocznością. **Zabudowa/działki:** próbki obrysu odsuniętego o 2 m, aby nie badać punktu pod dachem. **Obserwatorzy:** próbki geometrii. Nie jest to ocena każdego miejsca elewacji lub działki.

Braki nie są znanym terenem o wysokości 0 i nie zatrzymują pozostałych kół. NMPT jest nieprzezroczystym modelem górnej powierzchni 2,5D; nie opisuje prześwitów pod koronami ani brył 3D. NMT nie uwzględnia drzew i zabudowy. Modele są oddzielnymi produktami.

## Pliki i wydajność

`atlas_DATA_ID/`: `atlas.gpkg`, `ekspozycja.csv`, `report.json`, `report.md`, `events.jsonl`, podfoldery NMT/NMPT z GeoTIFF i stylami QML. Po eksporcie także `atlas.pdf`, `atlas.png` / `atlas_2.png`, `atlas.html`. Zachowaj cały folder dla HTML bez internetu. Raporty transferów mają własne podfoldery.

Rastry: `count.tif`, `hub.tif`, `bottom.tif`, `unknown.tif`, `scope.tif`, `rotor.tif`, `quality.tif`, opcjonalnie `hillshade.tif`. Indeksy obserwują źródłowe foldery. Zmiana danych nie przelicza samoczynnie zakończonego atlasu — uruchom nowe zadanie.

Krok mapy jest niezależny od piksela źródłowego. Przy większym kroku przeszkody agregowane są maksimum, aby nie uśrednić dachów i grzbietów. Źródło może być znacznie większe od wyniku. Interfejs pokazuje orientacyjny transfer; NMPT 20 km przy 0,5 m to bardzo duży obszar. Transfer jest strumieniowy, kafle deduplikowane, turbiny analizowane kolejno, wyniki zbiorcze zapisywane blokami. Limity ochronne: 40 mln komórek na koło, 400 mln w rastrze zbiorczym i 1000 turbin na zadanie. To limity, nie gwarancja szybkiego wykonania największego zadania.

GDAL korzysta z wzajemności linii widzenia, rzeczywistej wysokości turbiny i oka nad NMT. Domyślnie uwzględnia krzywiznę i refrakcję 6/7. Braki są analizowane w wariancie optymistycznym i pesymistycznym; rozbieżność daje niepewność. Maska jakości zachowuje także małe dziury NoData po zmianie kroku. Nie ma automatycznej transformacji EVRF2007 ↔ KRON86; analiza NMPT używa NMT w tym samym pionie, bez cichego zamiennika.

## Samo pobieranie

Przełącz tryb na **Tylko pobierz NMT / NMPT dla bufora warstwy**. Wskaż dowolną warstwę wektorową, bufor, zasoby i foldery w tym samym oknie. Każdy zasób ma preferowany piksel źródłowy, najbliższy dostępny zamiennik / tryb ścisły i układ wysokościowy. Drugi układ można dopuścić w tym trybie; nie oznacza to transformacji. Po pobraniu można dodać rastry; indeksy folderów reagują na dodanie/usunięcie plików.

WCS GUGiK dostarcza numeryczny ASCII, lokalnie kompresowany do GeoTIFF Float32 w EPSG:2180. Sprawdzone TIFF-y tych usług zwracały Byte, dlatego nie zastępują numerycznych wysokości. Cache sprawdza żądanie i odczyt; nie rozpoznaje sam nowszej epoki źródła.

Kod: `workspace_dialog.py` — jedyny formularz; `atlas.py` — koła i rastry; `atlas_context.py` — ekspozycja; `atlas_presentation.py` — style i eksport; `engine.py`/`core.py`/`catalog.py` — transfer; `coverage.py` — indeksy. Starsze moduły linii pozostają pomocniczo w kodzie, lecz ich okno nie jest rejestrowane w menu.

Licencja GPL-3.0. Pełna instrukcja i walidacja: `docs/Instrukcja_ATLAS_2.0.0.md` w repozytorium.
