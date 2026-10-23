# NMT i NMTP ściągacz 1.2.0 — wersja z naciskiem na NMPT

Ta paczka zawiera rozwijaną tutaj wtyczkę, a nie oryginalny „Pobieracz danych GUGiK”. W głównym oknie pobierania domyślnie wybrane jest NMPT. Dodano działającą analizę **konkretnych linii widzenia** od wskazanych miejsc obserwacji do punktu turbiny, z uwzględnieniem drzew i dachów w NMPT.

## Pobranie i instalacja

[Pobierz ZIP 1.2.0](https://github.com/misinskimichal/pobieracz_danych_gugik/raw/refs/heads/codex/nmt-nmtp-sciagacz/releases/NMT%20i%20NMTP%20%C5%9Bci%C4%85gacz-1.2.0.zip).

1. Zakończ poprzednie zadania wtyczki i uruchom ponownie QGIS.
2. Wybierz **Wtyczki → Zarządzanie wtyczkami → Zainstaluj z ZIP**.
3. Wskaż pobrany ZIP bez rozpakowywania. Po aktualizacji uruchom ponownie QGIS, aby wczytać wszystkie nowe moduły.
4. Jeśli QGIS nie wymieni poprzedniej instalacji, odinstaluj ją i zainstaluj nowy ZIP. Oddzielne foldery danych pozostają na dysku.

Obsługiwane metadanymi: QGIS 3.28–3.x, Python >=3.9. Testowane tutaj: QGIS 3.40.6 / Qt5 / GDAL 3.10.3 / Python 3.13 / Linux. Windows i macOS nie są dostępne w tym środowisku do sprawdzenia. Wtyczka korzysta z PyQGIS, GDAL/OGR, NumPy, requests i lxml obecnych w środowisku QGIS; nie wymaga Open3D, GRASS ani osobnego serwera. QGIS 4 nie jest objęty tym wydaniem.

## Samo pobieranie NMPT

W głównym oknie wybierz warstwę, promień np. **20000 m**, folder NMPT i folder raportów. Domyślnie zaznaczone jest samo NMPT. Ustaw najlepszą rozdzielczość źródłową albo preferencję 0,5 m. Kliknij **Pobierz**. NMT można osobno włączyć, jeżeli jest potrzebne.

To pobiera kafle dla bufora całej geometrii, tak jak wcześniejsza wersja. Do analizy tylko wskazanych miejsc użyj nowego okna niżej, które pobiera znacznie węższe korytarze. Obie funkcje korzystają z tych samych folderów, więc można używać dotychczas pobranych danych.

## Pierwsza analiza widoczności

Otwórz w głównym oknie **Nowe: analiza widoczności turbin z NMPT…**. Funkcja jest też w menu **Wtyczki → NMT i NMTP ściągacz → Widoczność turbin — NMPT**.

1. **Turbiny:** wskaż warstwę pojedynczych punktów. Podaj wysokość piasty nad gruntem i średnicę wirnika albo wybierz pola z tymi wartościami w metrach. Puste pole atrybutów oznacza użycie stałej wartości z formularza. Brak wartości w wybranym polu jest błędem danego obiektu, nie automatycznym użyciem innej wysokości.
2. **Cel:** wybierz piastę lub najwyższy punkt zasięgu łopaty. Drugi wariant liczy `grunt NMT + piasta + średnica / 2`. Nie opisuje całego obracającego się wirnika.
3. **Obserwatorzy:** wybierz punkty, budynki lub działki. Dla każdego poligonu powstaje jeden punkt wewnętrzny (`pointOnSurface`). Nie jest to analiza wszystkich miejsc na działce. Można ograniczyć obie warstwy do zaznaczonych obiektów.
4. **Wysokość oka:** domyślnie 1,7 m ponad gruntem NMT. Dla budynków najlepiej przygotować punkty przy elewacji, na zewnątrz dachu. Umieszczenie obserwatora pod dachem lub koroną drzewa w NMPT daje wynik niejednoznaczny, a nie automatyczne „niewidoczne”.
5. **Promień od turbiny:** domyślnie 20000 m. Pary dalej od siebie mają osobny stan „Poza promieniem analizy” i nie powodują pobierania danych.
6. **NMPT:** pozostaw zaznaczone **Uwzględnij NMPT**. Domyślnie dane szczegółowe są wymagane do 1000 m od obserwatorów i turbin. Dostępne są 650 / 1000 / 1500 m oraz własna wartość. To promień od punktu, nie pierścień między 650 a 1500 m.
7. **Lokalnie czy cała linia:** lokalnie oznacza mniej transferu, ale nie sprawdza drzew i budynków w środkowej części długiej trasy. **NMPT na całej linii** sprawdza pokrycie od oka do turbiny. Nie trzeba pobierać całego koła 20 km.
8. **Foldery:** wskaż oddzielne NMPT, NMT i wyniki. NMT jest potrzebne pomocniczo do poziomu gruntu i kontroli terenu. Oko nie jest podnoszone na dach przez odczyt NMPT. Oba modele muszą mieć ten sam wybrany układ wysokościowy, domyślnie PL-EVRF2007-NH.
9. **Pobieranie:** domyślnie automatyczne; najlepszy dostępny piksel w wybranym układzie. Plan obejmuje korytarze linii z buforem 2 m dla NMPT / 5 m dla NMT i przecinające je pełne kafle. Zgodne pliki o tym samym żądaniu są ponownie używane. Odznacz pobieranie, aby pracować tylko na lokalnych folderach, np. bez internetu.
10. Kliknij **Analizuj widoczność z NMPT**. Widać etap, bieżącą parę, liczbę wyników, podczas transferu także aktywne pliki, MB, prędkość i szacowane pozostałe MB / ETA etapu. Kliknięcie **Ukryj** pozwala dalej pracować w QGIS. **Anuluj** zachowuje gotowe dane i obliczone pary; aktywne połączenie może czekać do 90 s.
11. Po zakończeniu kliknij **Pokaż wyniki na mapie**. Dodawane są punkty i kolorowe linie; rastry nie są automatycznie ładowane jako wielka kolekcja.

Na pierwszą próbę wybierz jedną turbinę i kilka punktów przy zabudowaniach. Limit jednego zadania to **20000 par**, wliczając pary poza promieniem; dla większych warstw stosuj zaznaczenie. To limit ochronny, nie deklaracja, że każde zadanie 20000 długich linii wykona się szybko.

## Kolory i znaczenie wyników

| Kolor / stan | Znaczenie |
|---|---|
| Czerwony, `blocked_detail` | Znana przeszkoda w NMPT przecina linię widzenia |
| Brązowy, `blocked_terrain` | Znany teren przecina linię |
| Zielony, `visible_modeled` | Brak przeszkody i komplet wymaganych NMT/NMPT wzdłuż całej linii |
| Żółty, `potential_visible_partial_detail` | Brak przeszkody w sprawdzonych odcinkach; poza lokalnym NMPT pokrycia nie sprawdzono |
| Niebieski, `visible_terrain_only` | NMPT było wyłączone; sprawdzono tylko teren |
| Fioletowy, `unknown_required_data` | Brakuje wymaganego NMT/NMPT, odczyt się nie udał albo wystąpił błąd tej linii |
| Różowy, `uncertain_geometry` | Oko/cel wewnątrz NMPT, wynik bliski przeszkodzie albo duża niespójność modeli |
| Szary przerywany, `outside_analysis` | Odległość przekracza wybrany promień |

Brak danych nie oznacza wysokości 0. Znana przeszkoda może potwierdzić przesłonięcie mimo braków w innym miejscu. Procenty w tabeli oznaczają **długość trasy**, a nie prawdopodobieństwo widoczności. Status `completed` oznacza ukończenie obliczeń, nie widoczność każdej turbiny ani kompletność NMPT poza zadeklarowanym modelem lokalnym.

## Pliki wynikowe i diagnostyka

Każde zadanie tworzy `widocznosc_DATA_ID`:

- `widocznosc.gpkg`: warstwy `obserwatorzy`, `turbiny`, `linie_widzenia` w EPSG:2180. Linie mają ID pary, status, powód, odległość, pokrycie modeli, wysokości końców, minimalny prześwit i przybliżoną odległość komórki przeszkody.
- `wyniki.csv`: te same podstawowe wyniki; średnik i UTF-8 z BOM ułatwiają otwarcie w Excelu.
- `report.json`: wszystkie ustawienia, punkty wejściowe, pominięte obiekty, każdy wynik, wybrane pliki rastrów, georeferencja, wielkość plików, daty modyfikacji i błędy. Nie jest to pełny kryptograficzny manifest zawartości.
- `report.md`: czytelne podsumowanie i zasady interpretacji.
- `events.jsonl`: kolejne zdarzenia; przy długim zadaniu JSON jest także okresowo aktualizowany.
- `pobieranie_NMT/` i `pobieranie_NMPT/`: raporty transferu, błędów usługi, kafli i masek NoData, jeżeli pobieranie było włączone.

Indeksy folderów NMT i NMPT nadal aktualizują się po dodaniu/usunięciu kafli, przy aktywnej wtyczce. Wyjściowe linie są zapisem zakończonej analizy: **nie przeliczają się same po zmianie rastrów**. Po aktualizacji danych uruchom nowe zadanie.

## Zastosowany algorytm i wydajność

`visibility_dialog.py` tworzy źródła snapshotów warstw i `VisibilityTask`. `visibility.py` w tle transformuje wejście do EPSG:2180, wybiera pary w promieniu, planuje dane i korzysta z istniejącego `Engine` pobierania. Analiza nie wymaga scalania całych folderów w jeden ogromny raster.

`RasterStore` indeksuje nagłówki kafli, wybiera najdrobniejszy ważny piksel i odczytuje tylko potrzebne bloki 256 × 256. Na zasób utrzymuje do 8 otwartych plików i 32 bloki Float64, około 16 MiB pamięci samych bloków. NumPy, profile, sterowniki i QGIS potrzebują dodatkowej pamięci. Maksymalnie milion granic komórek na linię chroni przed patologiczną liczbą nakładających się rastrów.

Linia jest dzielona we wszystkich granicach przecinanych komórek NMT/NMPT. Nie ma stałego kroku np. 10 m, który przeskakiwałby przez drzewo zapisane w pikselu 0,5 m. Dla linii biegnącej wzdłuż granicy siatki sprawdzane są oba boki. Pojedyncze dotknięcie narożnika o zerowej długości nie jest odcinkiem przesłaniania. W każdej komórce powierzchnia ma stałą wysokość; nie odtwarza się nieznanej geometrii poniżej piksela.

Wysokości: `oko = NMT(obserwator) + wysokość oka`, `cel = NMT(turbina) + piasta [+ połowa średnicy]`. Przeszkoda to maksimum dostępnego NMT i wymaganego NMPT. Domyślnie uwzględniana jest krzywizna Ziemi z refrakcją optyczną `k=1/7`, `R_eff=6371000/(1-k)`. Do przeszkody w odległości `s` na trasie długości `L` dodaje się `s*(L-s)/(2*R_eff)`. Sprawdzane jest minimum prześwitu w całym przedziale komórki, nie tylko w środku.

Tolerancja wysokości 0,25 m wyodrębnia graniczne przecięcia; **nie jest oszacowaniem błędu pomiaru**. NMPT niższe od NMT o ponad 3 m oznacza potencjalną niespójność i wyklucza bezwarunkowe potwierdzenie widoczności. Oba parametry są na razie stałymi algorytmu zapisanymi w raporcie.

Nowe GeoTIFF-y mają dokładną, uprzednio zweryfikowaną siatkę żądania. Pliki wcześniejszych wersji z submilimetrowym zaokrągleniem WCS są w analizie wyrównywane do zadeklarowanej siatki tylko przy obecności metadanych wtyczki i różnicy do 1 mm. JSON zachowuje `gt` i `source_gt`. To korekta numeryczna georeferencji, nie transformacja wysokości ani przesuwanie dowolnych danych.

Rastry z nieznanym zasobem/układem, innym CRS, obrotem, wieloma kanałami albo Byte są odrzucane z powodem w JSON. Nie są domyślnie traktowane jako prawidłowy NMPT. Wspierane są przede wszystkim dane pobrane tą wtyczką; własne modele wymagają poprawnych metadanych i wspólnego pionu. Nie ma automatycznej transformacji EVRF2007 ↔ KRON86.

## Co sprawdzono i co pozostaje do zrobienia

Testy automatyczne obejmują stare pobieranie i nowe linie NMPT: wąskie drzewo, przeszkodę przy obserwatorze, braki na trasie, model lokalny / pełny, piastę / koniec łopaty, punkt pod dachem, różne układy, krzywiznę, granice siatki, ograniczenie cache, anulowanie, błąd jednej pary, zapis wyników i obsługę GUI. Mały test rzeczywistych WCS GUGiK w Warszawie odczytał NMT 1 m i NMPT 0,5 m; kolejny przebieg użył tych samych plików bez ponownego transferu kafli. Obserwator pod pokryciem NMPT został poprawnie oznaczony jako niejednoznaczny. To test przepływu danych, nie terenowa walidacja farmy.

To analiza **2,5D** powierzchni NMPT. Korony i dachy są nieprzezroczyste; nie modeluje sezonowości roślinności, prześwitów, elewacji ani dokładnej geometrii turbiny. Nie ma jeszcze sceny 3D, ray tracingu siatek, animowanego wirnika, wyliczania jego widocznej części ani rastrowej mapy widoczności każdego piksela w promieniu. Plan tych rozszerzeń pozostaje w suplemencie E dokumentacji głównej. Najbliższe użyteczne kroki to próbkowanie wielu punktów elewacji / działki, profile kontrolne, model pokrycia na mapie i porównanie z obserwacjami terenowymi.

[Pełna dokumentacja, rozwiązania i plan 3D](https://github.com/misinskimichal/pobieracz_danych_gugik/raw/refs/heads/codex/nmt-nmtp-sciagacz/docs/NMT_i_NMTP_sciagacz_dokumentacja_i_rozwoj.md).
