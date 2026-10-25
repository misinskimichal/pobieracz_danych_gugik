# NMT i NMTP ściągacz 2.8.0 — prosty wybór obrazu i model 3D Three.js

Wydanie z 25 października 2026. [Pobierz ZIP do instalacji w QGIS](https://github.com/misinskimichal/pobieracz_danych_gugik/raw/refs/heads/codex/nmt-nmtp-sciagacz/releases/NMT%20i%20NMTP%20%C5%9Bci%C4%85gacz-2.8.0.zip).

Sprawdzony ZIP: **41 plików, 389336 bajtów**. SHA-256: `31c3fe0f75fd0e951582f93739f36d8e8a5da2051b7726b0a79310455ebba2b2`. Test instalacji rozpakował tę paczkę, załadował ją menedżerem QGIS i z jej kodu przygotował samodzielny model Three.js z licencją oraz zdjęcie. Kliknięcie wspólnego przycisku otworzyło właściwy plik fotomontażu. Sprawdzono też wyłączenie zegara interfejsu przy wyładowaniu wtyczki.

## Dlaczego poprzednia obsługa była myląca

W 2.7.0 przycisk „Scena 3D” otwierał model terenu, natomiast zdjęcie z telefonu było używane przez osobny przycisk fotomontażu. Wybranie zdjęcia nie zmieniało pierwszego przycisku. Użytkownik mógł więc poprawnie dodać plik, a następnie otrzymać wynik bez tego obrazu. Formularz miał również kilka przycisków uruchamiających podobne odświeżenia i zbyt wiele parametrów stale na ekranie.

Drugim problemem było odtwarzanie warstw projektu według identyfikatorów QGIS. Po otwarciu atlasu w innym projekcie identyfikatory mogły nie istnieć. Ponowne przygotowanie sceny bez źródłowych warstw mogło usunąć dodatkowe bryły i korony, choć wcześniejsza scena zawierała te obiekty. Ortofotomapa oglądana z góry nie odtwarza fotograficznych ścian; na samej siatce NMPT stromym ścianom odpowiadają rozciągnięte piksele dachów.

Nowe wydanie zmienia przebieg obsługi, silnik 3D i zachowanie danych przy ponownym przygotowaniu. Nie przedstawia pojedynczej fotografii jako kompletnego modelu przestrzennego otoczenia.

## Instalacja i pierwsze uruchomienie

1. Zainstaluj ZIP przez **Wtyczki → Zarządzanie i instalacja wtyczek → Zainstaluj z ZIP**. Uruchom QGIS ponownie, aby nie pozostały w pamięci moduły poprzedniego wydania.
2. Otwórz wtyczkę i kliknij **Wczytaj report.json** z istniejącego atlasu. Zachowaj cały folder, w tym rastry `terrain.tif`, `elevation.tif`, sceny i zdjęcia.
3. W części **Wizualizacja** wybierz **Model 3D** albo **Fotomontaż**. Przygotowanie prezentacji korzysta z zapisanych modeli; nie wymaga ponownego pobierania NMT/NMPT ani liczenia widoczności. WMS może wymagać ponownego pobrania zdjęcia lotniczego.

## Model 3D — od gruntu, z domami i roślinnością

W głównym formularzu pozostały:

- wybór rodzaju wyniku;
- ortofotomapa: warstwa rastrowa QGIS albo automatycznie Geoportal;
- warstwa lasów/zadrzewień oraz obrysów budynków;
- **Wskaż miejsca patrzenia na mapie**, lista nazw i wysokości oka;
- **Utwórz model 3D** / **Otwórz model 3D** — jeden przycisk zależny od stanu;
- **Ustawienia zaawansowane…** w osobnym oknie.

Warstwy o rozpoznawalnych nazwach, np. `OT_PTLZ_A`, `OT_BUBD_A`, „Lasy” i „Budynki”, są wstępnie wybierane z projektu. Dowolna warstwa działek nie jest traktowana jako budynki. Jeśli zgadywanie nazwy nie pasuje do struktury projektu, wskaż właściwą warstwę ręcznie w głównym formularzu. Wybrana warstwa lasów powinna zawierać lasy/zadrzewienia, a nie wszystkie klasy pokrycia terenu razem.

Po przygotowaniu otwiera się model Three.js. Główne sterowanie to wybór widoku, miejsca, kąta widzenia, **Patrz na turbinę** i zapis PNG. Przeciąganie rozgląda się, kółko zmienia kąt widzenia w trybie z oczu. Po kliknięciu sceny strzałki/WASD przesuwają aparat, Shift zwiększa krok. Mała mapka jest nakładką na scenie i pozwala wybrać otwarte miejsce patrzenia. Parametry dodatkowe są pod zwijaną sekcją.

Scena jest lokalnym modelem płaskim; krzywiznę i refrakcję uwzględniają obliczenia widoczności oraz profile zgodnie z ich ustawieniami. Przy dalekich obserwacjach nie należy zastępować tych wyników oceną samego wyglądu sceny.

Źródła mają różne zadania:

| Dane | Co rzeczywiście dostarczają |
| --- | --- |
| NMT | Grunt i wysokość aparatu nad gruntem |
| NMPT | Wysokości dachów i koron, nie kompletne bryły ścian i drzew |
| Ortofotomapa WMS/WMTS/raster | Obraz na terenie i dachach; nie zdjęcia elewacji |
| Obrysy budynków | Podstawa oddzielnych brył; wysokości i przybliżony dach z NMT/NMPT |
| Lasy/punkty drzew | Miejsca ilustracyjnych koron o wysokościach NMT/NMPT |

**Bez obrysów i danych o roślinności sam NMPT nadal jest powierzchnią 2,5D.** Test rzeczywistych danych potwierdził to ograniczenie: zdjęcie jest na modelu, ale jego piksele rozciągają się na stromych fragmentach. Większa liczba pikseli zdjęcia nie tworzy brakujących widoków ścian. W widoku z gruntu korzystaj z obiektów wektorowych albo rzeczywistej fotografii. Elewacje, okna i sylwetki liści są poglądowe; dachy mają ortofotomapę. Nie jest to fotogrametryczna rekonstrukcja fotograficznych fasad i prześwitów pod drzewami.

Zapisane w poprzedniej scenie budynki/korony są zachowywane, jeśli odpowiadają temu samemu modelowi, turbinie i układowi wysokościowemu, a brakuje ich warstw projektu. Dotyczy to również części brakujących źródeł, np. budynków przy nadal dostępnej warstwie lasów. Maski prezentacji są przeliczane na bieżącą siatkę, obiekty przycinane do zasięgu. Dla starszych scen bez maski budynków odtwarzamy ją z zapisanych rzeczywistych obrysów. Przy zmianie turbiny lub pionowego układu odniesienia danych nie łączymy automatycznie. Nie odtworzymy obiektów, których nigdy nie zapisano w scenie.

Zachowanie poprzednich obiektów można świadomie wyłączyć w ustawieniach zaawansowanych. Nowa jawnie wybrana warstwa zastępuje zapisane obiekty danej roli.

## Własne zdjęcie — obraz faktycznie używany jako tło

1. Wybierz **Fotomontaż**.
2. Kliknij **Dodaj zdjęcie**, wskaż aparat i kierunek na mapie, następnie JPG/PNG. Import automatycznie wybiera tryb zdjęcia.
3. Nazwa, ścieżka i podgląd pokazują, który plik trafi do wyniku. Kliknij **Utwórz fotomontaż**.
4. W przeglądarce zdjęcie stanowi nieruchome tło. Modele turbin mają pozycje i wymiary z atlasu. Dopasuj kierunek, pochylenie i kąt widzenia. Dodatkowe kąty, ustawienie wirnika oraz maski są w zwijanej sekcji.
5. Zapisz PNG. Aby zachować korekty przy ponownym przygotowaniu w QGIS, pobierz też JSON i wczytaj go w ustawieniach zaawansowanych zdjęcia.

Nie ma drugiego widocznego przycisku, który po dodaniu zdjęcia przypadkowo otwiera model z ortofotomapą. Jeśli wybierzesz jawnie **Model 3D**, otworzy się model; jeśli **Fotomontaż**, otworzy się zdjęcie. Wybór zachowuje raport. Brakujący lub starszy plik wyniku jest przygotowywany ponownie z aktualnym interfejsem, jeśli zachowano dane wejściowe.

JPG może być obrócony zgodnie z EXIF; ogniskowa równoważna 35 mm pomaga ustawić początkowy kąt widzenia. Pozostają limity 6000 px / 24 MP obrazu roboczego, kopia oryginału i do 24 zdjęć. HEIC należy wyeksportować do JPG; sklejane panoramy i fisheye wymagają innego modelu aparatu. To fotomontaż jednego kadru, nie swobodne poruszanie się wewnątrz zdjęcia. Model zasłaniania jest przybliżony; ręczna maska nie zmienia rastrów analizy. Szczegóły fizycznego modelu i ograniczeń opisano też w [instrukcji 2.7.0](Instrukcja_ATLAS_2.7.0.md).

## Konkretny widok Street View zamiast samego obszaru mapy

W trybie fotomontażu kliknij **Dodaj widok Street View z linku…**. Otwórz wcześniej właściwą panoramę w przeglądarce, ustaw kierunek i skopiuj pełny adres z paska. Obsługiwany jest link widoku z `@lat,lon,3a,...` lub oficjalny adres `api=1&map_action=pano` z pozycją i opcjonalnym identyfikatorem `pano`. Link zwykłej mapy jest odrzucany z instrukcją. Krótki adres `maps.app.goo.gl` należy najpierw otworzyć i skopiować pełny adres docelowy.

Program odczytuje pozycję, kierunek, pochylenie, pole widzenia i identyfikator panoramy. Przelicza kierunek geograficzny na kierunek siatki QGIS. Zapisany odnośnik otwiera konkretną panoramę, zamiast ponownie szukać w przybliżonym obszarze.

Są dwa sposoby dostarczenia obrazu:

- **Bez klucza API:** wybierasz plik JPG/PNG odpowiadający temu kadrowi, pozyskany z odpowiednimi uprawnieniami. Link ustawia aparat, lecz sam nie zawiera pikseli zdjęcia. Nie udajemy, że otwarcie odnośnika pobrało fotografię.
- **Z własnym kluczem Street View Static API:** podaj go w ustawieniach zaawansowanych, przed importem linku. Program w tle sprawdzi panoramę i pobierze wybrany kadr przez oficjalne API. Potrzebny jest włączony dostęp i rozliczenia konta Google. Wersja używa kadru 640×480 i zachowuje metadane daty, panoramy oraz autorstwa. Zasady wykorzystania i eksportu obrazów pozostają zasadami dostawcy.

Klucz jest przechowywany wyłącznie w bieżącej sesji pola hasła, bez zapisu do raportu, HTML, projektu czy dziennika. Nie są dołączone cudze klucze ani nieudokumentowany downloader panoram. Błąd dostępu, brak pokrycia i limit usługi mają czytelne komunikaty. Domyślna wysokość aparatu Street View to 2,5 m — trzeba ją sprawdzić, nie jest pomiarem z API.

Po imporcie użyj tego samego przycisku **Utwórz fotomontaż**, aby umieścić turbiny na obrazie. Biblioteka Google nie jest wymagana do działania własnych zdjęć ani modelu Three.js.

## Interfejs i wydajność

Powtarzające się akcje odświeżenia sceny i przygotowania punktów zostały zastąpione wspólnym przyciskiem. Wysokości techniczne, gęstość siatki, limity koron, warianty tekstur, maski, rzadziej używane wyniki i pozostałe ustawienia są w oknie zaawansowanym. Nie ma dodatkowych zakładek kopiujących formularz. Dziennik jest rozwijany na żądanie; statystyki i postęp pojawiają się podczas zadania. Zmieniona prezentacja nie przelicza automatycznie formalnej widoczności.

Silnik Three.js odpowiada za bufory, materiały, tekstury i kontrolę głębokości. Każdy blok terenu i fragment dachu ma georeferencyjne UV i własny obraz; podgląd mapki ma oddzielny obraz. Materiały zdjęcia zachowują kolory bez domyślnego dodatkowego cieniowania. Przy zmianie miejsca zwalniamy tekstury poprzedniego detalu. Korony używają instancji przecinających się płaszczyzn z wycinaniem alfa. Braki NMT/NMPT pozostają otworami. Rysowanie odbywa się na żądanie, bez ciągłego obciążania procesora nieruchomą sceną.

Three.js 0.184 wymaga WebGL 2. Jeśli go nie ma, strona próbuje poprzedniego renderera WebGL 1 i pokazuje informację o trybie zgodności. To nie ukryta zmiana źródła obrazu. Sama fotografia używa Canvas 2D, bez WebGL i bez usług sieciowych. Wyeksportowane pliki zawierają skrypty i obrazy, nie pobierają bibliotek z CDN.

## Kod i sprawdzone wzorce innych projektów

- [Qgis2threejs, sprawdzony commit 922f1663](https://github.com/misinskimichal/Qgis2threejs/tree/922f1663e4767361fc98205d005ac63c8cfaa447): model DEM i wektory jako oddzielna geometria, obraz przypisany do materiału bloku, wybór materiału bez cieniowania, lokalne zasoby i Three.js. Sprawdzono m.in. `core/build/dem/material_builder.py`, zarządzanie obrazami/materiałami oraz wersję biblioteki w `package.json`.
- [Street View Saccon](https://github.com/saccon/streetview-plugin): kierunek wskazywany na mapie i oficjalny adres widoku w przeglądarce.
- [go2streetview](https://github.com/enricofer/go2streetview): użycie własnego klucza w dostępie do zdjęcia; podgląd strony w panelu nie jest automatycznym importem obrazu do niezależnej sceny.
- [GoogleMapsStreetDock](https://github.com/Consortis-Geospatial/GoogleMapsStreetDock): rozdzielenie mapy i panoramy oraz transformacja współrzędnych.

Nasza paczka pozostaje samodzielna. `three_runtime.js` to lokalnie zbudowany Three.js 0.184.0 z npm, na licencji MIT. `THREE_LICENSE.txt` jest w ZIP, pełna treść licencji jest również osadzona w wyeksportowanym HTML. Budowanie IIFE: esbuild 0.28.1, wejście `export * from 'three'`, `--bundle --minify --format=iife --global-name=AtlasTHREE --legal-comments=inline`. Użytkownik wtyczki nie instaluje Node/npm.

Nowe moduły: `scene_three.js` — silnik; `visual_workflow.py` — uproszczony formularz; `scene_saved_context.py` — zachowanie eksportowanych obiektów i masek; `street_reference.py` — link konkretnego widoku i opcjonalne oficjalne API. Dotychczasowy `scene_webgl.js` pozostaje trybem zgodności. Formalne obliczenia widoczności nie zostały zmienione.

## Weryfikacja i jej granice

Przeszedł pełny zestaw **105 testów Python/QGIS** w QGIS 3.40.6 / Qt5 / GDAL 3.10.3 na Linux. Obejmuje routing jednego przycisku, wybrany plik zdjęcia, odtworzenie widoku, rozpoznawanie warstw, zachowanie starych obiektów i masek, brak zmiany rastrów, link panoramy oraz żądanie kadru i ochronę klucza na kontrolowanym serwerze/mocku. Dostępu do Google z kluczem użytkownika nie wykonywano; test API nie potwierdza pokrycia jego miejsca ani rozliczeń konta. Windows/macOS nie były dostępne do prób.

Test rzeczywistego Chromium potwierdził pracę **Three.js 184**, 210 koron w aktywnym otoczeniu, 3 bryły, 25 materiałów z obrazami, zmianę punktów i brak błędu GL. Porównanie widoku z oczu ze zdjęciem włączonym/wyłączonym zmieniło 211765 pikseli. To świadomie syntetyczna scena testowa, nie fotografia lokalizacji użytkownika. Oddzielny test własnego zdjęcia potwierdził PNG 2400×1600, maski, JSON, brak wyjątków JS i brak zewnętrznych zapytań HTTP.

Dodatkowo użyto rzeczywistych numerycznych NMT/NMPT GUGiK oraz pobrano osiem kafli rzeczywistego WMS ortofotomapy. Test przeglądarki potwierdził materiały na modelu z poziomu oczu i różnicę 1042756 pikseli przy przełączeniu zdjęcia. Test bez BDOT pokazuje zarazem opisane wyżej ograniczenie stromych powierzchni NMPT. Nie traktujemy samego wyniku „test przeszedł” jako potwierdzenia fotorealistycznych fasad.

Przykłady i zrzuty w [folderze demonstracyjnym](examples/atlas_2.8.0/) są oznaczone jako syntetyczne. Przed udostępnieniem projektu użytkownika należy zachować odpowiadające mu źródła, daty i parametry kamery; screenshot demonstracyjny nie potwierdza dokładności jego fotomontażu.
