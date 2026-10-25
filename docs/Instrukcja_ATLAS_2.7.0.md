# NMT i NMTP ściągacz 2.7.0 — własne zdjęcie z telefonu i fotomontaż turbin

Wydanie z 25 października 2026 r. [Pobierz gotowy ZIP do instalacji w QGIS](https://github.com/misinskimichal/pobieracz_danych_gugik/raw/refs/heads/codex/nmt-nmtp-sciagacz/releases/NMT%20i%20NMTP%20%C5%9Bci%C4%85gacz-2.7.0.zip).

ZIP zawiera 35 plików i ma 182821 bajtów. SHA-256: `f5e67ec8301ce8d9f34ae9b0197db671f552102f95cbca15fc3799ef8bab0513`. Potwierdzono jego rozpakowanie, wykrywanie i ładowanie przez menedżer wtyczek QGIS oraz przygotowanie fotomontażu i trwałych warstw z kodu zainstalowanego z tej paczki.

Instalacja: **Wtyczki → Zarządzanie i instalacja wtyczek → Zainstaluj z ZIP**, następnie restart QGIS. To aktualizacja naszej osobnej wtyczki „NMT i NMTP ściągacz”, a nie ZIP oryginalnego Pobieracza GUGiK. Zachowaj dotychczasowe foldery atlasów i NMT/NMPT. Wczytaj istniejący `report.json`; nie trzeba ponownie pobierać modeli ani wykonywać analizy widoczności tylko po to, aby dodać zdjęcie.

## Co dostarczyć z terenu

Wystarczy oryginalne zdjęcie JPG/JPEG lub PNG. Najlepiej fotografować aparatem 1×, bez cyfrowego powiększenia, poziomo, z miejsca mającego znaczenie dla oceny inwestycji. Zachowaj oryginalny plik, aby nie stracić informacji o obiektywie i obrocie. Jeśli telefon zapisuje HEIC/HEIF, wyeksportuj zwykły JPG. Pełne panoramy 360°, obrazy typu fisheye i sklejane panoramy telefonu nie mają obsługi swojego rzutowania w tym wydaniu — użyj pojedynczego zwykłego kadru.

Zanotuj miejsce wykonania i przybliżoną wysokość aparatu nad gruntem, np. 1,7 m. Zdjęcie z piętra wymaga odpowiednio większej wysokości. GPS ani kompas w pliku nie są wymagane: lokalizację i kierunek wskazujesz na mapie. Ich dokładność ma znaczenie dla późniejszego dopasowania.

Własne zdjęcie przedstawia rzeczywiste domy, drzewa i drogę. Nie trzeba tworzyć ich fotograficznych elewacji z ortofotomapy. Zdjęcie nie zamienia się jednak w model pozwalający swobodnie przemieszczać kamerę; fotomontaż dotyczy miejsca wykonania kadru. Dotychczasowe sceny 3D pozostają osobną opcją w tym samym formularzu.

## Dodanie zdjęcia w QGIS

1. Otwórz wtyczkę i wczytaj `report.json` istniejącego atlasu lub najpierw wykonaj atlas dla swoich turbin.
2. W tym samym formularzu znajdź **Zdjęcie z telefonu · fotomontaż turbin** i kliknij **Dodaj zdjęcie na mapie · wskaż aparat i kierunek**.
3. Formularz odsuwa się i pojawia się małe okno instrukcji. **Przeciągnij od miejsca aparatu w kierunku środka zdjęcia**. Alternatywnie kliknij pierwsze miejsce, a następnie drugie. Nie musisz wskazywać dokładnie turbiny: wskazujesz kierunek kadru.
4. Wybierz plik JPG/PNG w oknie plików. Formularz pokaże jego ścieżkę, nazwę, podgląd i współrzędne aparatu. **Escape / prawy przycisk / Anuluj** przywraca poprzednie narzędzie bez dodawania ujęcia. Anulowanie wyboru pliku również nie tworzy rekordu.
5. W razie potrzeby użyj **Popraw miejsce i kierunek na mapie** albo **Zmień plik**. Wysokość aparatu, kierunek, pochylenie, przechylenie i kąt widzenia można zmienić w formularzu. Kierunek jest liczony względem siatki EPSG:2180; mapę możesz mieć w innym CRS.
6. Wybierz model **NMPT** albo **NMT**. NMPT uwzględnia pokrycie, NMT sam grunt. Model musi obejmować miejsce aparatu; nie ma cichego przejścia na inny układ wysokościowy. Niedostępny model jest wyłączony na liście. Wysokości gruntu pod aparatem i turbinami są brane z tego samego wybranego produktu.
7. Kliknij **Przygotuj wizualizację na zdjęciu**. Zadanie pracuje w tle, pokazuje etap i procent oraz daje się anulować. Gotowy fotomontaż otwiera się w przeglądarce.

Punkt aparatu oraz odcinek kierunku pojawiają się w projekcie. Możesz również wskazać zdjęcie przed wykonaniem pierwszego atlasu; wtedy punkty są warstwami tymczasowymi. Po utworzeniu atlasu zapisują się do GeoJSON razem z raportem. Dopiero dostępność zapisanych modeli odblokowuje przygotowanie fotomontażu. W zestawie można mieć do 24 ujęć, wybieranych z listy zdjęć.

## Dopasowanie w przeglądarce

Zdjęcie jest nieruchomym tłem. Na nim rysowane są uproszczone przestrzenne modele turbin o położeniu, wysokości piasty i średnicy wirnika zapisanych w atlasie. Wymiary nie są dobierane wyłącznie „na oko”; ich wielkość w obrazie wynika z perspektywy i odległości.

- **Kierunek:** przesuwa model zgodnie z obrotem kamery w poziomie. Przeciąganie zdjęcia koryguje kierunek i pochylenie.
- **Pochylenie:** dodatnie oznacza spojrzenie w górę.
- **Przechylenie:** dopasowuje obrót telefonu wokół osi obiektywu.
- **Poziomy kąt widzenia:** decyduje o skali perspektywy. Jeśli EXIF zawiera ogniskową równoważną 35 mm, program wyznacza wartość początkową. Korekcje telefonu, kadrowanie i stabilizacja mogą wymagać ręcznej poprawy. Bez takiego EXIF zaczynamy od 65°.
- **Patrz na najbliższą turbinę:** ustawia kierunek osi kadru na najbliższy poprawny obiekt; może pomóc w odnalezieniu turbin. Nie dowodzi, że rzeczywisty środek zdjęcia był skierowany właśnie tam.
- **Poziom i celownik:** pomoc w orientacji. Linia poziomu odpowiada kątowi 0°, nie zmierzonemu profilowi horyzontu terenu.
- **Kierunek osi wirnika / Obrót łopat:** poglądowe ustawienie gondoli i wirnika. Nie pochodzi z pomiaru aktualnej pracy turbiny ani z danych producenta.
- **Krycie, Pokaż turbiny i Numery turbin:** porównanie z oryginalnym zdjęciem i identyfikacja obiektów.

Nie zmieniaj kąta widzenia tylko po to, aby uzyskać oczekiwany rozmiar turbiny. Dopasuj parametry do aparatu i rozpoznawalnych elementów terenu. W tym wydaniu nie ma automatycznego rozpoznawania budynków, kalibracji z punktów kontrolnych ani pomiarowego oszacowania błędu ustawienia kamery. Do opinii wymagającej udokumentowanej dokładności konieczne są dalsza kalibracja i kontrola terenowa.

## Zasłanianie i ręczny pierwszy plan

**Zasłanianie modelem** stosuje profil przeszkód między aparatem a turbiną. Dla każdego obiektu próbkowane jest 65 kierunków obejmujących wirnik, do odległości przed środkiem wieży. Z NMT/NMPT powstaje kąt horyzontu, a odpowiadające mu fragmenty modelu turbiny są usuwane z obrazu. Opcja krzywizny i refrakcji jest dziedziczona z atlasu; nie przelicza formalnych rastrów widoczności.

To przybliżenie prezentacji, nie nowa analiza pełnej widocznej powierzchni wirnika. Nie uwzględnia dokładnej głębokości każdego fragmentu łopaty. Wąskie przeszkody między promieniami mogą nie zostać wychwycone; na długich trasach próbkowanie ma limit 8192 próbek/promień i zgłasza rozrzedzenie. Brakujące próbki oznaczają niepewność. Dla kierunków z lukami nie stosujemy automatycznej maski i nie nazywamy tego potwierdzoną widocznością.

Jeżeli aparat według NMPT znajduje się pod koroną lub dachem, automatyczne zasłanianie jest wyłączone i pojawia się ostrzeżenie. Sprawdź położenie, wysokość oraz datę modelu. NMT nie uwzględnia domów i drzew. NMPT nie opisuje prześwitów pod koronami i może być starsze od fotografii.

W trybie **Zamaluj pierwszy plan** malujesz po rzeczywistym drzewie, dachu, słupie itp. Turbina schowa się za zaznaczeniem. **Pokaż maskę** pokazuje czerwone pomocnicze zaznaczenie; nie trafia ono na eksportowany PNG. **Przywróć ręczną maskę**, **Cofnij maskę** i **Usuń maskę** służą do korekt. Przywrócenie ręcznej maski nie odwraca działania maski automatycznej — ją wyłącz osobnym przełącznikiem, jeżeli model nie pasuje do zdjęcia.

Ręczna maska jest decyzją prezentacyjną użytkownika i jest zapisana w JSON. Nie zmienia danych NMT/NMPT ani wyniku analizy.

## Zapis i powrót do ujęcia

**Zapisz fotomontaż PNG** pobiera obraz w rozdzielczości przygotowanego zdjęcia, a nie małego podglądu na ekranie. Limit wynosi 6000 px na dłuższym boku i 24 MP. Oryginał pozostaje skopiowany bez zmian. Dla większego zdjęcia raport informuje o zmniejszeniu wersji roboczej. Maksymalny przyjmowany plik to 100 MB i 150 MP wymiarów nagłówka; uszkodzony obraz może zostać odrzucony podczas odczytu.

**Zapisz dopasowanie JSON** zachowuje kierunek, kąty kamery, kąt widzenia, ustawienie wirnika, krycie i ręczną maskę. Przeglądarka pobiera plik do wybranego w niej folderu; nie ma automatycznego prawa do nadpisania raportu QGIS. Aby wrócić do tego samego ustawienia:

1. W QGIS wybierz właściwe zdjęcie z listy.
2. Kliknij **Wczytaj dopasowanie JSON zapisane w przeglądarce**.
3. Wskaż pobrany plik i kliknij **Przygotuj wizualizację na zdjęciu** ponownie.

Identyfikator ujęcia i SHA-256 oryginału pomagają odrzucić dopasowanie innego zdjęcia. Zmiana pliku obrazu usuwa ręczną maskę, aby nie przenosić jej na inny kadr. Zmianę miejsca lub wysokości aparatu wykonuje się we wtyczce; wymaga ponownego przygotowania horyzontów.

Wczytanie `report.json` odtwarza listę ujęć i ich parametry. Zapisz również projekt QGIS: punkty i kierunki mają trwałe źródła GeoJSON. Warstwa punktów ma działanie obiektu **Otwórz fotomontaż zdjęcia**, dostępne z identyfikacji/atrybutów. Przygotowane ujęcia są też podlinkowane z `atlas.html`. Dla zmienionych ustawień link w atlasie informuje o potrzebie ponownego przygotowania. Usunięcie ujęcia z listy usuwa je z indeksu, zachowując pliki zdjęcia i gotowe wyniki.

### Pliki

| Plik | Zawartość |
| --- | --- |
| `report.json` → `photo_imports` | Lista ujęć, miejsca i kierunki, parametry, względne ścieżki przygotowanych zasobów, hash oryginału, ostrzeżenia i czas przygotowania |
| `zdjecia_punkty.geojson` | Punkty aparatu w EPSG:2180 i odnośniki do HTML |
| `zdjecia_kierunki.geojson` | Pomocnicze odcinki długości 80 m, pokazujące kierunek; nie zasięg widoczności |
| `zdjecia_terenowe/ID/oryginal.jpg` lub `.png` | Kopia dostarczonego pliku bez modyfikacji |
| `zdjecia_terenowe/ID/podglad.jpg` | Obrócony zgodnie z EXIF obraz do wizualizacji, do limitu rozdzielczości |
| `zdjecia_terenowe/ID/ustawienia.json` | Ustawienia użyte podczas przygotowania we wtyczce |
| `zdjecia_terenowe/ID/model_fotomontazu.json` | Diagnostyka kamery, turbin i profili zasłaniania, bez kopii obrazu base64 |
| `zdjecia_terenowe/ID/fotomontaz.html` | Samodzielny interaktywny fotomontaż z osadzonym zdjęciem; działa offline |
| Pobrany `dopasowanie_ID.json` | Zmiany wykonane w przeglądarce, do ponownego wczytania w QGIS |

Przy przenoszeniu zadania zachowaj cały folder atlasu, wczytaj raport z nowego miejsca i zapisz projekt ponownie. Gotowy HTML może być udostępniony samodzielnie; nie zawiera bezwzględnej ścieżki do oryginału na komputerze. Obraz i dane lokalizacji są częścią wizualizacji.

## Street View i podane projekty

Przycisk **Otwórz Street View w tym miejscu i kierunku · przeglądarka** otwiera zwykły adres Google Maps. Nie wymaga klucza API w naszej wtyczce, nie pobiera zdjęć Google do fotomontażu i nie gwarantuje pokrycia dokładnie w punkcie. Kierunek mapy jest przeliczany na kierunek geograficzny użyty w odnośniku. To oddzielna czynność od przygotowania lokalnego zdjęcia. Zdjęcie z telefonu nie jest wysyłane do tej usługi.

Przejrzano wskazane źródła:

- [saccon/streetview-plugin](https://github.com/saccon/streetview-plugin/tree/03070786d30b07d231fa001929f3fdda5cbe06d1): potwierdzono przeciąganie na mapie i otwieranie adresu z `map_action=pano`, pozycją i kierunkiem. Własna implementacja uwzględnia CRS projektu i nie kopiuje nieprawidłowo dużego `fov=250` z przykładu w tym kodzie.
- [md-moinul-mobin/StreetView-Pro](https://github.com/md-moinul-mobin/StreetView-Pro/tree/e5624b83f68edb3195064ecf58624001d3985636): README opisuje kliknięcie/przeciągnięcie, wizualną linię i otwarcie w przeglądarce. W tym przeglądzie nie instalowano dostarczonych binarnych paczek ZIP ani nie weryfikowano deklaracji pokrycia Google WMS.
- [enricofer/go2streetview](https://github.com/enricofer/go2streetview/tree/0e52a37737e961bcf9f7d010284d6887d24bf14b): źródła mają panel QtWebEngine i obsługę klucza Google; sprawdzone metadane deklarują QGIS 3.36–3.98, wersję 10.1.
- [Consortis-Geospatial/GoogleMapsStreetDock](https://github.com/Consortis-Geospatial/GoogleMapsStreetDock/tree/6f782516669033cb071cfa5dfb7347eb0a94abe7): potwierdzono panel `QWebEngineView`, transformację współrzędnych i przełączanie widoku według README/kodu. Nie uruchamiano usługi Google wewnątrz panelu.

W naszej wersji wybrano zewnętrzną przeglądarkę dla tego odnośnika i lokalny HTML dla własnych zdjęć. Instalacja nie wymaga dodawania PyQtWebEngine, konta Google ani kopiowania danych z Google Maps. To własny kod oparty na ogólnych wzorcach interakcji i adresowania, bez włączenia kodu wymienionych wtyczek do paczki. Wcześniejsze kierunki Panoramax/Mapillary/GLB pozostają opisane w [analizie integracji](Panoramy_i_modele_3D_analiza_integracji.md); nie zostały tu wdrożone jako dostawcy zdjęć.

## Rozwiązania techniczne i wydajność

- `photo_map_tool.py`: dwa kliknięcia lub przeciągnięcie, marker i linia, anulowanie, przywracanie narzędzia mapy.
- `photo_panel.py`: import, formularz kamery w istniejącym oknie, warstwy punktów i kierunków, `QgsTask`, postęp, zapis raportu, ponowne wczytanie JSON oraz jawny odnośnik Street View. Przed wymianą GeoJSON zwalnia dostawców OGR, aby ograniczyć blokady plików na Windows. Duże podglądy obrazu są odkładane do przygotowania w tle.
- `photo_core.py`: kontrola pliku, dekodowanie `QImageReader` z automatycznym obrotem, opcjonalny EXIF GDAL, spójny produkt wysokościowy, profile przeszkód i pliki offline. Czytnik modeli ma cache do 64 bloków 256×256 Float32, ok. 16 MB danych wysokościowych na otwarty raster. Nie ładuje całego dużego atlasu do pamięci.
- `photo_montage.js`: model perspektywiczny aparatu, uproszczona geometria turbin, przycinanie bliskiej płaszczyzny, malowanie Canvas 2D, maska z modelu i ręczna, eksport. Podgląd ma do 2200 px szerokości, PNG pełny wymiar przygotowanego obrazu. Nie wymaga WebGL ani zewnętrznych bibliotek/CDN.
- `photo_html.py`: samodzielna strona z osadzonym obrazem i skryptem; nazwy i dane są kodowane przed wstawieniem do HTML.

Limit prezentacji wynosi 200 najbliższych turbin, z jawnym raportem pominiętych. Aparat musi być dalej niż większa z wartości 5 m i promień wirnika. Dane do bardzo bliskich ujęć wymagają dokładniejszego modelu konkretnej turbiny. Maska ma do 2000 pociągnięć i 200 000 punktów; jej położenia są normalizowane do wymiarów zdjęcia, więc eksport pełnej rozdzielczości zachowuje dopasowanie.

Wyniki są najpierw przygotowywane w osobnym katalogu roboczym. Dopiero po powodzeniu zastępują poprzednie pliki. Anulowanie lub błąd przed publikacją zachowuje wcześniejszy HTML. Nie jest to transakcja wieloplikowa odporna na awarię dysku w samym momencie zastępowania; błąd wejścia/wyjścia nadal jest raportowany.

## Weryfikacja

Próby wykonano w QGIS 3.40.6 / Qt5 / GDAL 3.10.3 na Linux oraz w rzeczywistym Chromium. Windows i macOS nie były dostępne do testów.

Przeszedł pełny zestaw **99 testów Python/QGIS**, cztery zestawy Node (w tym perspektywa i geometria fotomontażu) oraz rzeczywisty test obrazu i pobierania plików w Chromium: PNG 2400×1600, poprawny JSON, zero wyjątków JavaScript i zero zewnętrznych zapytań HTTP podczas pracy na własnym zdjęciu. W próbie obrazu potwierdzono różnicę 22 693 pikseli po dodaniu turbin, 21 545 po zastosowaniu modelu zasłaniania i 5713 po ręcznej masce bez jej pomocniczego czerwonego podglądu. To kontrola działania na danych syntetycznych, nie miara dokładności terenowej. Skan Bandit nie zgłosił problemów poziomu medium/high w kodzie wtyczki.

Samodzielny [przykład syntetyczny HTML](examples/atlas_2.7.0/fotomontaz.html) i [zrzut podglądu](examples/atlas_2.7.0/podglad.png) pokazują obsługę modułu. Pobierz HTML, aby otworzyć go lokalnie w przeglądarce. Tło jest celowo narysowanym przykładem testowym; właściwy fotomontaż używa dostarczonej fotografii.

Sprawdzono obrót EXIF i ogniskową 35 mm, perspektywę na geometrii o znanych wymiarach, kierunek przy innym CRS projektu, przywracanie narzędzia po przeciągnięciu/anulowaniu, pracę zadania w tle, zachowanie oryginału, brak ponownego uruchomienia pobierania/analizy, brak zmiany rastrów, zapisywanie i odtwarzanie warstw projektu oraz dopasowania. Testy obejmują NoData, brak gruntu pod aparatem, aparat wewnątrz pokrycia, jawny wybór różnych układów wysokościowych, błędne obrazy, anulowanie i odrzucenie maski innego zdjęcia.

Test przeglądarki porównuje rzeczywiste piksele zdjęcia bez turbin, z turbinami, z zasłanianiem i z ręczną maską. Sprawdza cofanie, obrót kamery o 180°, pobrane PNG w wymiarach źródła oraz plik JSON. Dane demonstracyjne są syntetyczne i wyraźnie oznaczone — nie przedstawiają lokalizacji użytkownika ani jakości przyszłego dopasowania do konkretnego telefonu.

Przydatne polecenia dla programisty:

```bash
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest tests_nmt_nmpt.test_downloader -v
node tests_nmt_nmpt/test_photomontage.cjs
python tests_nmt_nmpt/browser_photo.py /sciezka/fotomontaz.html /folder/testu
```

Ostatni test wymaga narzędzi deweloperskich Chromium, requests, websocket-client i Pillow. Nie są dodatkowymi zależnościami instalowanej wtyczki.
