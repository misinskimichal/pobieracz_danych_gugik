# NMT i NMTP ściągacz 2.2.0 — szczegółowe 3D, BDOT, raport w warstwach i ponowne przeliczanie

Wydanie 2.2.0 rozwija działający atlas z 2.1.0. Zwiększa gęstość podglądu, dodaje WebGL, opcjonalną teksturę z projektu, klasyfikację lasów i symbole drzew, odnośniki w panelu warstw oraz odtwarzanie zadania z raportu. NMT i NMPT nadal mają osobne koła i kroki obliczeń. Obserwatorzy pozostają opcjonalni.

## Instalacja

[Pobierz ZIP 2.2.0](https://github.com/misinskimichal/pobieracz_danych_gugik/raw/refs/heads/codex/nmt-nmtp-sciagacz/releases/NMT%20i%20NMTP%20%C5%9Bci%C4%85gacz-2.2.0.zip) i zainstaluj przez **QGIS → Wtyczki → Zarządzanie wtyczkami → Zainstaluj z ZIP**. Nie rozpakowuj. Zakończ aktywne zadania i uruchom QGIS ponownie po aktualizacji. Folderów danych nie trzeba usuwać.

Paczka ma 120922 bajtów; SHA-256: `37e89822d56605eebc66c3db23849d34bba06e3a258fa1468b591eb20748e6d1`.

Wymagania pozostają takie jak w 2.1.0: QGIS 3.28–3.x, Python ≥3.9, GDAL/OGR, NumPy, requests i lxml ze środowiska QGIS. Weryfikacja: QGIS 3.40.6, Qt5, GDAL 3.10.3 na Linux. Nie przeprowadzono bezpośredniego testu Windows/macOS. QGIS 4 nie jest objęty tym wydaniem. Szczegółowy HTML potrzebuje przeglądarki z WebGL; obok powstaje lekki podgląd Canvas bez WebGL. Wtyczka nie wymaga instalacji Three.js, Node.js, Open3D, ModernGL ani serwera. Biblioteki programistyczne użyte do testów nie są zależnościami użytkownika.

## Lepsza rozdzielczość 3D

W 2.1.0 siatka miała do 129×129 wierzchołków. Było to celowe ograniczenie rendererów Canvas. Teraz do wyboru są **129, 257, 513 lub 1025 wierzchołków na bok**. Domyślnie 513. Szczegółową scenę rysuje WebGL, dzieląc teren na płaty do 129×129 punktów. Płaty mieszczą indeksy w 16 bitach, więc nie wymagają rozszerzenia obsługi indeksów Uint32. Nie sortujemy setek tysięcy trójkątów w JavaScript przy każdym ruchu kamery.

**Gęstszy podgląd nie tworzy nowych pomiarów.** Najdrobniejszy dostępny krok jest ograniczony krokiem modelu obliczeniowego. Jeśli mapa jest liczona co 5 m, siatka 3D nie stanie się pomiarem co 0,5 m. Zmniejszenie kroku analizy ma koszt obliczeniowy i wymaga odpowiednio szczegółowego źródła.

Przykład dla analizy NMPT co 1 m:

| Promień samej sceny | Limit wierzchołków na bok | Orientacyjny rzeczywisty krok 3D |
|---:|---:|---:|
| 1000 m | 129 | 16 m |
| 1000 m | 257 | 8 m |
| 1000 m | 513 | 4 m |
| 1000 m | 1025 | 2 m |
| 500 m | 1025 | 1 m |

Wyrównanie siatki może lekko zmienić te wartości. **Rzeczywisty krok i liczbę punktów zawsze podaje nagłówek sceny.** Przykładowo przy analizie co 0,5 m, promieniu sceny 250 m i limicie 1025 można zachować krok 0,5 m. Duży HTML i bardziej wymagająca karta graficzna są ceną gęstej siatki. Braki pozostają otworami. Próbkowanie podglądu może pomijać cienkie przeszkody pomiędzy wierzchołkami; wynik widoczności i profil nadal korzystają z modelu analizy, nie z uproszczonej sceny.

Pole **Mniejszy promień samej sceny 3D** pozwala np. liczyć widoczność w 1 km, a szczegółowo oglądać 300–500 m. Wartość 0 oznacza cały promień modelu. Wpisanie większej wartości nie rozszerza sceny poza obliczone koło. Parametr nie zmienia koła widoczności ani długości przekroju. Dzięki temu można zachować szeroką analizę i małą, dokładną scenę bez dociążania całego zadania.

W przeglądarce dostępne są obrót, nachylenie, powiększenie, pion ×1–5, rzut perspektywiczny lub równoległy, kąt widzenia 15–90°, kierunek oświetlenia, wybór kolorów, przełączniki NMPT/NMT, symboli drzew i linii przekroju oraz **Zapisz PNG**. Pion ×1 zachowuje proporcje metrów. Zmiana kamery nie zmienia położenia obserwatora przekroju ani wyników analizy.

## Tekstura, np. ortofotomapa

1. W projekcie QGIS pozostaw widoczne warstwy, które mają tworzyć podkład sceny. Może to być ortofotomapa, lokalny raster RGB, mapa pól, dróg lub zabudowy.
2. Zaznacz **Nałóż na 3D teksturę z widocznych podkładów projektu**.
3. Po obliczeniach wtyczka wyrenderuje teksturę w tle, z rozmiarem dłuższego boku do 2048 pikseli, a następnie osadzi ją bezpośrednio w HTML.
4. W scenie wybierz **Kolory → Tekstura mapy**; po poprawnym załadowaniu tekstury tryb włącza się automatycznie.

Do tekstury trafiają widoczne warstwy projektu poza wynikami atlasów i indeksami pobranych kafli. Jeśli nie chcesz nadruku punktów, etykiet lub innych elementów, wyłącz je przed zadaniem. To obraz powierzchni, nie dodatkowy pomiar wysokości. Fotografia nałożona na rzadszy model nie zwiększa jego dokładności.

Warstwa WMS/XYZ może wykonać połączenia sieciowe także wtedy, gdy obliczenia korzystają wyłącznie z lokalnego NMT/NMPT. Jeśli potrzebna jest praca całkowicie offline, użyj lokalnego podkładu lub wyłącz teksturę. Sam zapisany HTML nie pobiera później podkładu z sieci: obraz jest osadzony jako `data:image/png;base64`. Pozwala to też uniknąć ograniczeń dostępu WebGL do sąsiednich obrazów otwieranych przez `file://`. Użytkownik odpowiada za możliwość dalszego udostępniania użytej tekstury zgodnie z warunkami jej źródła.

Brak widocznego podkładu lub błąd jego usługi nie usuwa wyników analizy. Scena pozostaje dostępna z kolorami wysokości/pokrycia, a problem zapisuje się w diagnostyce `scene_texture_error` i dzienniku okna. Renderowanie tekstury i map do PDF działa asynchronicznie. Końcowe składanie ograniczonych stron i dodawanie warstw nadal może dać krótką pauzę GUI.

## Co daje BDOT — lasy i drzewa

W formularzu są dwie opcjonalne listy: **Lasy / zadrzewienia** jako poligony oraz **Drzewa** jako punkty. Można wskazać odpowiednio przygotowane warstwy BDOT lub własne dane o takiej samej geometrii. Wtyczka nie zakłada, że dowolna warstwa o nazwie „BDOT” jest lasem ani że każdy obiekt bazy reprezentuje pojedyncze drzewo. W razie potrzeby wcześniej przefiltruj właściwe klasy obiektów.

| Dane | Obecne zastosowanie | Czego nie wyznaczają samodzielnie |
|---|---|---|
| Obrys lasu/zadrzewienia | Klasyfikacja i zielony materiał w trybie pokrycia | Wysokości drzew, gęstości koron i przepuszczalności światła |
| Punkt drzewa | Położenie symbolu; oszacowanie wysokości z NMPT−NMT w tym miejscu | Dokładnego kształtu korony, gatunku ani aktualnej wysokości bez zgodności dat i lokalizacji |
| NMT | Poziom gruntu | Wysokości dachu lub korony |
| NMPT | Górna powierzchnia przeszkód | Wnętrz budynków, prześwitów i sezonowego ulistnienia |

Symbole drzew powstają wyłącznie przy poprawnym gruncie i powierzchni, z różnicą wysokości od 2 do 80 m. Pozostałe punkty są pomijane i raportowane. Korony są uproszczonymi symbolami; ich szerokość i kształt są ilustracją, a nie pomiarem dendrometrycznym. BDOT i modele mogą pochodzić z innych terminów: punkt może trafić w przerwę korony, dach albo nieaktualny obiekt. To trzeba sprawdzić przy analizie konkretnej inwestycji.

**Warstwy BDOT w tym wydaniu wzbogacają prezentację i opis pokrycia. Nie zmieniają obliczonej widoczności.** Nie dokładamy lasowi umownych 20–30 m i nie nakładamy drugiej przeszkody na już istniejącą koronę w NMPT. Test porównuje raster przed i po dodaniu BDOT i potwierdza identyczny wynik analizy. Wysokości przeszkód pozostają z NMT/NMPT. W przyszłości klasy BDOT można wykorzystać do jawnych scenariuszy sezonowych, lecz wymaga to założeń i walidacji.

Ograniczenia podglądu: maksymalnie 20 000 poligonów lasu i 2000 symboli drzew dla sceny. Przekroczenie limitu i pominięcia trafiają do `details[].context_summary`. Limity nie zmniejszają zasięgu analizy rastrowej.

Do poprawy rzeczywistej geometrii kolejnym źródłem są chmury LAS/LAZ: klasy gruntu, roślinności i budynków, zgodne z epoką oraz układem wysokościowym modelu. Wtedy można budować osobne korony, dachy i sceny. Przydatne biblioteki: [PDAL](https://github.com/PDAL/PDAL), [laspy](https://github.com/laspy/laspy), [Open3D](https://github.com/isl-org/Open3D), [trimesh](https://github.com/mikedh/trimesh). Ich użycie do pełnego ray tracingu brył pozostaje dalszym rozszerzeniem; nie deklarujemy tej funkcji w 2.2.0.

## Raport dostępny z panelu warstw QGIS

W grupie atlasu pojawia się **Raport HTML i sceny 3D · prawy przycisk**. To przestrzenna warstwa odnośników w `raport.gpkg`, początkowo wyłączona na mapie. Jej geometrie pokazują koła zadania, a pola zawierają odnośniki.

Kliknij ją prawym przyciskiem, aby otworzyć HTML, scenę NMT/NMPT, przekrój albo wczytać ustawienia do przeliczenia. Raport otwiera się w przeglądarce; scena nie staje się rastrem QGIS. Zapisany projekt zachowuje warstwę i jej akcje. Po ponownym otwarciu projektu aktywna wtyczka odtwarza menu kontekstowe. Bez niej pozostają zapisane akcje obiektów dostępne z formularza/tabeli warstwy.

HTML wejściowy powstaje także po wyłączeniu eksportu PDF/PNG. Zachowaj cały folder atlasu dla profili i lekkiej sceny; szczegółowa scena z osadzoną teksturą jest samodzielnym HTML, ale jej odnośniki do profilu i lekkiej wersji wymagają sąsiednich plików. Przy przenoszeniu wyników odnośniki zapisane w atrybutach mogą nadal zawierać dawny adres. Menu wtyczki wyznacza bieżący folder z pliku warstwy, a wczytanie lokalnego `report.json` odszukuje standardowe pliki obok raportu. Foldery źródłowych modeli w ustawieniach trzeba w razie potrzeby poprawić ręcznie.

## Przelicz ponownie na tych samych danych

Po ukończeniu atlasu kliknij **Przelicz ponownie · lokalne modele**. Wcześniej możesz zmienić wysokość piasty, średnicę wirnika, oko obserwatora, promienie i kroki, układ wysokościowy, parametry sceny, kierunek profilu oraz opcjonalne warstwy.

Przycisk zachowuje ten sam zestaw i położenie turbin, porównując identyfikatory oraz współrzędne z raportem. Zmieniony zestaw/położenie wymaga zwykłego **Utwórz atlas widoczności**. Nowe koło może mieć większy zasięg; dostępność lokalnych kafli jest wtedy oceniana dla nowej geometrii. Braki nie są automatycznie dociągane w tym trybie.

Ponowne przeliczenie zawsze ustawia `auto_download=False` dla modeli, nawet jeśli checkbox automatycznego pobierania pozostaje zaznaczony. **Nie odpytuje WCS w celu pobrania NMT/NMPT.** Opcjonalna tekstura z WMS/XYZ nadal może korzystać z sieci. Jeśli nowych danych brakuje, użyj zwykłego uruchomienia z pobieraniem. Przy zmianie układu wysokościowego nie przeliczamy automatycznie źródeł — potrzebne są zgodne dane w wybranym układzie.

Każdy wariant dostaje nowy folder. Poprzednie rastry, raport i ustawienia pozostają nienaruszone. Nowy raport zawiera `options.recalculate_from`. Obliczenia widoczności wykonujemy ponownie — zmiana wysokości turbiny może zmienić cień. Nie pokazujemy poprzedniego rastra jako nowego wyniku.

### Po ponownym uruchomieniu QGIS

Kliknij **Wczytaj report.json** lub użyj menu warstwy raportu. Wtyczka odtworzy warstwę turbin z `atlas.gpkg`, pierwotne identyfikatory, promienie, kroki, foldery i parametry. Wskazania opcjonalnych warstw są odtwarzane przez ich identyfikatory projektu, jeśli te warstwy nadal są w projekcie; w przeciwnym razie wybierz je ponownie.

Pola **piasta_m** i **srednica_m** zachowują indywidualne wysokości z poprzedniego atlasu. Jeśli chcesz zastosować jedną nową wartość do wszystkich turbin, wyczyść pole atrybutu obok parametru i wpisz stałą wartość. Sama zmiana liczby po lewej nie zastępuje wskazanego pola — ta zasada obowiązuje również przy pierwszej analizie.

### Przyspieszenie kolejnych wariantów

Maski poprawnych pikseli źródłowych są zapisywane w `<folder atlasów>/.nmt_nmpt_cache/validity`. Klucz obejmuje ścieżkę, rozmiar, czas modyfikacji, geometrię rastra, skalę i przesunięcie oraz metadane/maski towarzyszące `.aux.xml` i `.msk`. Zmiana źródła powoduje nową maskę. Zapis atomowy zapobiega użyciu częściowo zapisanej maski. Cache nie zastępuje rastra źródłowego i nie umożliwia wykorzystania usuniętego kafla.

To oszczędza ponownego skanowania wszystkich pikseli tylko po to, aby ustalić braki danych. Nadal trzeba wykonać obliczenia dla nowych parametrów. Nie podajemy gwarantowanego przyspieszenia dla każdej lokalizacji. Cache można usunąć, gdy zadania nie działają; zostanie odtworzony. Starsze klucze po zmianach źródeł nie są jeszcze automatycznie czyszczone. Kontrola czasu/rozmiaru to mechanizm cache, nie kryptograficzny dowód niezmienności całej zawartości pliku.

## Co zastosowano z PDF „Pasiok_LUTRA.pdf”

Załącznik został przeczytany jako materiał referencyjny. To prezentacja zawierająca historię i plany rozwoju, a nie specyfikacja bieżącego QGIS. Nie traktujemy opisanych tam zapowiedzi, np. źródła MapZen, jako potwierdzenia dzisiejszej dostępności usługi.

| Strony PDF | Pomysł | Stan w 2.2.0 / kierunek |
|---|---|---|
| 9 | DEM i tekstura z mapy 2D | Osobne dane wysokościowe i osadzona tekstura z projektu |
| 10, 14 | Wektory i symbole 3D | Opcjonalny obrys lasu, symbole drzew i uproszczona turbina; wysokości z modeli |
| 17, 22 | Cieniowanie i źródła światła | Normalne siatki, oświetlenie kierunkowe z kontrolą kierunku; nie jest to analiza cieni słonecznych |
| 18 | Linie 3D | Linie przekroju jako jawnie opisana nakładka |
| 19 | Wydruki 3D | PNG sceny; atlas PDF pozostaje zestawem map 2D. Automatyczny wielostronicowy raport z ujęciami 3D to kolejny etap |
| 24–25 | Typ rzutu i kąt widzenia | Perspektywa/rzut równoległy, FOV 15–90° |
| 11, 15 | CityGML/CityJSON, 3D Tiles | Dalej: osobne bryły i strumieniowanie większych scen; nie wdrożono w tym wydaniu |
| 29 | Animacje z klatek kluczowych | Możliwy rozwój: zapisane pozycje kamery i przeloty; obecnie ręczne sterowanie oraz PNG |

Większe miasto, jak w przywołanym przykładzie Trento, wymaga zwykle budynków jako brył i dzielenia danych na kafle. Zwiększenie jednej siatki NMPT nie odtwarza automatycznie fasad, podcieni ani tekstur elewacji.

## Sprawdzone źródła i alternatywy

Próby odczytu wskazanych stron GISCOurse i Reddit zakończyły się w tym środowisku odmową połączenia proxy (403). Nie przypisujemy im szczegółów, których nie udało się przeczytać. Sprawdzono zamiast tego oficjalną dokumentację QGIS przez jej repozytorium oraz README poniższych projektów:

- [Oficjalny opis QGIS 3.40 3D Map View](https://github.com/qgis/QGIS-Documentation/blob/release_3.40/docs/user_manual/map_views/3d_map_view.rst) — rozdziela rozdzielczość terenu, tekstury, błąd modelu, cienie, kamerę i eksport.
- [Qgis2threejs](https://github.com/minorua/Qgis2threejs) — DEM i wektory w przeglądarce, publikacja scen i eksport glTF. Przydatny do osobnego, zaawansowanego przygotowania prezentacji.
- [Three.js](https://github.com/mrdoob/three.js) — rozwój większych scen, modele glTF, materiały i sterowanie kamerą.
- [3D spatial data](https://github.com/wonder-sk/3d-spatial-data) — zestaw przykładów formatów/danych, również wspomniany w PDF.
- [CesiumJS](https://github.com/CesiumGS/cesium) — kierunek dla dużych scen i 3D Tiles; wskazanie biblioteki, bez deklaracji integracji w tym ZIP.

Wbudowany widok QGIS 3D jest dobrą alternatywą do dalszej pracy na danych projektu: **Widok → Nowy widok mapy 3D**, następnie w konfiguracji wybór terenu DEM, rastra i tekstury/motywu mapy. `NMT/terrain.tif` albo `NMPT/terrain.tif` przedstawia grunt; `NMPT/elevation.tif` powierzchnię. Przy osobnych modelach budynków/drzew jako podłożę wybierz NMT, aby nie dodawać ich wysokości drugi raz ponad NMPT. Nasz przycisk sceny otwiera HTML w przeglądarce; automatyczne skonfigurowanie natywnego widoku 3D QGIS nie jest funkcją tego wydania.

## Budowa i weryfikacja

Nowe pliki: `scene_webgl.js` — geometria, bufory 16-bitowe, kamera i shadery; `scene3d.html` — interfejs; `scene3d_canvas.html` — lekka wersja; `scene_context.py` — BDOT i symbolika; `scene_texture.py` — asynchroniczna tekstura i osadzenie obrazu; `atlas_links.py` — warstwa i akcje raportu. `workspace_dialog.py` odtwarza zadanie i uruchamia nowy wariant, a `atlas.py` zapisuje/reużywa maski. Biblioteki wykonawcze pozostały w środowisku QGIS; renderer WebGL jest własnym kodem bez zewnętrznego CDN.

68 testów Python/QGIS obejmuje także zmianę źródła i unieważnienie cache, ponowne przeliczenie bez wywołania pobierania, zachowanie starego raportu, pierwotnych identyfikatorów i nowych wysokości, menu po ponownym otwarciu projektu, osadzenie tekstury, wzrost gęstości oraz identyczność widoczności po dodaniu BDOT. Testy JavaScript sprawdzają dziury siatki, zakres indeksów, macierze kamery, geometrię turbiny/drzew, materiały i sterowanie. Shadery zostały skompilowane i użyte do renderowania przykładowej sceny przez Mesa/EGL. Testy nie zastępują próby konkretnej karty graficznej i pełnego obszaru inwestycji.

Publikowane przykłady są syntetyczne; nie zawierają geometrii użytkownika ani kopii jego PDF. [Instrukcja 2.1.0](Instrukcja_ATLAS_2.1.0.md) opisuje pozostałe mapy, promienie, procenty i interpretację profilu. [Pełna dokumentacja](NMT_i_NMTP_sciagacz_dokumentacja_i_rozwoj.md) zachowuje wcześniejsze pomysły biznesowe i plan dalszego rozwoju.
