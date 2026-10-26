# Prawdziwe zdjęcia i modele 3D — kierunki rozwoju Atlasu NMT/NMPT

**Aktualizacja 2.9.0:** przywrócono renderer WebGL z 2.7.0. Opis Three.js wdrożonego w 2.8.0 poniżej jest historyczny; aktualny przebieg i ograniczenia opisuje [instrukcja 2.9.0](Instrukcja_ATLAS_2.9.0.md).

Stan weryfikacji: 24 października 2026. Dokument opisuje **proponowane integracje**, a nie funkcje już wdrożone w wersji 2.6.0. Przejrzano kod i dokumentację wskazanych niżej repozytoriów. Nie pobierano panoram ani modeli Google i nie potwierdzono pokrycia konkretnej lokalizacji użytkownika.

Aktualizacja z 25 października: **własne zdjęcia i poglądowy fotomontaż turbin wdrożono w 2.7.0** — [instrukcja i ograniczenia](Instrukcja_ATLAS_2.7.0.md). Automatyczne źródła Panoramax/Mapillary, panoramy 360° i importer GLB opisane poniżej pozostają planem.

W [2.8.0](Instrukcja_ATLAS_2.8.0.md) uproszczono wybór zdjęcia/modelu, wdrożono lokalny Three.js 0.184 oraz link konkretnej panoramy i opcjonalne pobranie kadru przez oficjalne Street View Static API z własnym kluczem. Nie oznacza to wdrożenia pozostałych planowanych dostawców ani fotogrametrycznej rekonstrukcji otoczenia.

## Co najbardziej poprawi widok z poziomu gruntu

Ortofotomapa pokazuje przede wszystkim dachy i korony drzew. Jej nałożenie na teren nie odtwarza wyglądu ścian, pni ani przestrzeni pod drzewami. Gęstsze symbole lasu mogą poprawić prezentację, ale nie zastąpią rzeczywistych zdjęć.

Dla wybranych kliknięciem punktów rekomenduję dwa uzupełniające się tryby:

1. **Zdjęcie lub panorama + fotomontaż turbiny.** Otoczenie pochodzi z rzeczywistego zdjęcia, a turbina jest umieszczana zgodnie z położeniem, wysokością i ustawieniem kamery. To najbardziej bezpośrednia droga do przekonującego widoku z konkretnego miejsca. Panorama pozwala rozglądać się ze stanowiska aparatu; nie pozwala swobodnie przechodzić między domami.
2. **Teksturowany model 3D.** Odtwarza bryły i ich fotograficzny wygląd, pozwalając przesuwać kamerę. Jakość elewacji, drzew i widoków pod koronami zależy od dostępnego modelu. Nawet dobry model fotogrametryczny nie gwarantuje jakości zdjęcia ulicznego z każdego stanowiska.

Analiza widoczności nadal powinna korzystać z kontrolowanych danych NMT/NMPT. Zdjęcie i atrakcyjny model prezentacji nie zastępują obliczenia przesłaniania.

## Zweryfikowane projekty

| Projekt | Potwierdzone możliwości | Znaczenie dla naszej wtyczki |
| --- | --- | --- |
| [Aleph](https://github.com/Belluxx/Aleph) | Zdjęcia Street View, panoramy 360°, obrazy lotnicze/satelitarne, teren i teksturowane modele `mesh.glb`; wybór punktu lub obszaru, plan pobierania, wznawianie | Najciekawszy wzorzec przygotowania rzeczywistego otoczenia 3D; konieczne sprawdzenie pokrycia, praw do danych i georeferencji |
| [Panoramax — sprawdzony fork](https://github.com/IGNF-Xavier/qgis_panoramax) | Zdjęcia w panelu QGIS, wybór instancji, metakatalog; eksperymentalnie kalibracja kierunku, dwa równoległe ujęcia i wyznaczanie położenia z kilku zdjęć | Dobre wzorce wiązania zdjęcia z mapą i ręcznego dopasowania kamery |
| [MapillaryClickPreview](https://github.com/annadeckmyn/MapillaryClickPreview) | Warstwy pokrycia, filtr lat, podgląd najbliższego zdjęcia, metadane i przejście do Mapillary | Przydatny wzorzec sprawdzania dostępności i wyboru zdjęć; wymaga tokenu użytkownika |

Katalog `plugins.qgis.org` zwracał w tym środowisku błąd dostępu sieciowego. Weryfikacja opiera się na publicznych repozytoriach. Nie potwierdzono aktualnych funkcji Look Around, Pin, StreetView Pro ani opisanego WMS pokrycia Google. Nie należy na tej podstawie obiecywać gotowej integracji Apple ani krajowych panoram.

Nie ma podstaw, aby uznać Mapillary za wszędzie gęstsze od Google lub MapillaryClickPreview za oficjalnego następcę go2mapillary. Dostępność i aktualność trzeba sprawdzić dla konkretnego obszaru, źródła i daty.

## Aleph: co można wykorzystać

Sprawdzona wersja `alephgeo` 0.2.0 wymaga Python 3.11+, Pillow i NumPy. Nie należy zakładać zgodności z interpreterem każdej instalacji QGIS. Ewentualny importer pliku GLB nie musi uruchamiać całego Aleph wewnątrz QGIS.

Aleph potrafi zapisać tekstury JPEG wewnątrz GLB. Budynki i las nie muszą wtedy otrzymywać naszych proceduralnych materiałów. W źródłach użyto materiałów `KHR_materials_unlit`, które zachowują fotograficzne barwy bez wymuszania dodatkowego oświetlenia. To dobry punkt odniesienia dla importera.

**Ważne rozróżnienie dotyczące danych:** kod Aleph ma licencję MIT, ale zdjęcia i modele Google mają odrębne zasady. Sam README Aleph podaje, że jego sposób pobierania tych zasobów narusza warunki Google oraz używa nieudokumentowanych API. Brak wymaganego klucza API nie daje prawa do dowolnego wykorzystania danych. Dlatego do docelowego rozwiązania biznesowego rekomenduję importer modeli i zdjęć pozyskanych w dozwolony sposób, własne materiały lub udokumentowaną integrację z właściwą usługą. Aleph nie tworzy również pokrycia tam, gdzie Google go nie ma.

Deklarowany poziom szczegółowości/rozmiar teksela nie jest gwarancją dokładności geometrii ani szczegółowości danej lokalizacji. Najwyższy poziom pobierania może wielokrotnie zwiększyć transfer bez proporcjonalnej poprawy widoku z gruntu.

### Georeferencja GLB wymaga osobnego adaptera

GLB eksportowany przez sprawdzony Aleph ma układ lokalny:

- `x`: wschód;
- `y`: góra;
- `z`: południe;
- najniższy punkt ma `y = 0`.

W `asset.extras` zapisano `latitude`, `longitude`, `base`, `radius`, `bounds` i tekstowy opis `frame`. Aleph buduje lokalną ramę z modelu kuli użytego przez źródło; nie deklaruje polskiego układu wysokościowego. Nie wolno potraktować `base` jako wysokości PL-EVRF2007-NH ani przypisać bez sprawdzenia EPSG:4978/4979 całemu modelowi.

Importer powinien odtworzyć położenie i osie, uwzględnić skalę i obrót względem docelowej siatki mapy, a następnie sprawdzić dopasowanie pionowe do NMT w kontrolnych miejscach odsłoniętego gruntu. Użytkownik musi widzieć, czy dopasowanie jest potwierdzone, oszacowane czy ręczne. NMT i wyniki widoczności pozostają niezmienione. Sama zamiana znaku osi Z nie wystarcza.

Przykład odczytu metadanych pliku Aleph — **nie wykonuje jeszcze transformacji do QGIS**:

```python
import json
import math
from pathlib import Path
import struct


def read_aleph_georeference(filename):
    path = Path(filename)
    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12:
            raise ValueError("Niepełny nagłówek GLB")
        magic, version, declared_size = struct.unpack("<4sII", header)
        if magic != b"glTF" or version != 2:
            raise ValueError("Wymagany GLB 2.0")
        if declared_size != path.stat().st_size:
            raise ValueError("Niezgodny rozmiar GLB")
        chunk = stream.read(8)
        if len(chunk) != 8:
            raise ValueError("Brak nagłówka JSON")
        size, kind = struct.unpack("<II", chunk)
        if kind != 0x4E4F534A or not 0 < size <= 4 * 1024 * 1024:
            raise ValueError("Nieprawidłowy lub zbyt duży JSON")
        if size > declared_size - 20 or size % 4:
            raise ValueError("Nieprawidłowa długość JSON")
        model = json.loads(stream.read(size).decode("utf-8"))
    asset = model["asset"]
    extra = asset["extras"]
    lat, lon = float(extra["latitude"]), float(extra["longitude"])
    base, radius = float(extra["base"]), float(extra["radius"])
    if not all(math.isfinite(v) for v in (lat, lon, base, radius)):
        raise ValueError("Nieskończona lub nieokreślona współrzędna")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180 or radius <= 0:
        raise ValueError("Współrzędne poza zakresem")
    return {
        "origin_lon_lat": [lon, lat],
        "local_axes": "east, up, south",
        "source_base": base,
        "source_radius": radius,
        "source_frame_description": extra.get("frame"),
        "source_copyright": asset.get("copyright"),
        "target_height_datum": None,
    }
```

To czytnik określonego eksportu Aleph, nie walidator dowolnego GLB ani całej jego geometrii. Sprawdzono przykład na syntetycznym poprawnym nagłówku oraz błędnych nagłówkach, długościach i metadanych. Nie potwierdza to dopasowania rzeczywistego modelu do NMT.

## Panoramax: zdjęcia i ustawienie kamery

Sprawdzony fork obsługuje QGIS od 3.28. Korzysta z federacji instancji Panoramax, metakatalogu oraz możliwości wskazania własnego serwera. Wybór źródła powinien uwzględniać pokrycie, datę i licencję konkretnej instancji.

Fork dodaje funkcje szczególnie interesujące dla naszej wizualizacji:

- dwa przypięte ujęcia tego samego obiektu;
- wyznaczanie położenia przez przecięcie kierunków obserwacji, przy większej liczbie ujęć dopasowanie metodą najmniejszych kwadratów;
- kalibrację kierunku obrazu względem mapy;
- pomiary wysokości z kątów pionowych i opcjonalnym modelem wysokościowym;
- zapis identyfikatorów, instancji i dat źródłowych zdjęć.

Autor określa te rozszerzenia jako **eksperymentalny prototyp**, sprawdzony na niewielu sekwencjach. Nie należy utożsamiać ich ze stabilnymi funkcjami każdej oficjalnej wersji Panoramax. Położenie aparatu bywa obarczone błędem GNSS rzędu kilku metrów, a kierunek jazdy nie musi odpowiadać środkowi kadru. Ręczna kalibracja pozostaje potrzebna.

Dla naszej wtyczki najcenniejsze są jawne parametry kamery i sprawdzenie zgodności zdjęcia z mapą. Fotomontaż bez tej kontroli może wyglądać atrakcyjnie, ale pokazywać turbinę w złym miejscu lub rozmiarze.

## Mapillary: dostępność i wybór zdjęcia

MapillaryClickPreview 1.3.0 deklaruje **QGIS co najmniej 3.44** i wymaga **tokenu Mapillary użytkownika**. Nasza obsługa QGIS 3.28+ nie oznacza automatycznej zgodności z tą wtyczką. Integracja przez udokumentowany interfejs wymaga osobnej obsługi zgodności i autoryzacji; token nie powinien trafiać do raportu ani udostępnianego HTML.

W sprawdzonym kodzie podgląd pobiera miniaturę 1024 px, metadane, kierunek, datę i znacznik panoramy. Wtyczka udostępnia warstwy pokrycia oraz pozycje oryginalne i obliczone. To nie jest gotowy eksporter pełnej panoramy ani modelu 3D. Do prezentacji dużego obrazu i eksportu fotomontażu trzeba osobno zweryfikować dostępne formaty oraz warunki wykorzystania zdjęcia.

## Konkretny plan wdrożenia

### Etap 1 — zdjęcia przy istniejących punktach wizualizacji

Pozostawiamy obecne klikanie punktów w mapie i jedną tabelę miejsc. Dodajemy do niej działanie „Sprawdź zdjęcia i modele”, a obok wyników: źródło, datę, odległość od punktu, kierunek, typ zdjęcia/modelu i warunki wykorzystania. Najbliższe zdjęcie nie musi być wykonane dokładnie w wybranym punkcie — rzeczywiste stanowisko aparatu powinno być zaznaczone na mapie i potwierdzone przez użytkownika.

Zadania sieciowe działają w tle z postępem, możliwością anulowania i limitem czasu. Brak pokrycia, brak autoryzacji i błąd serwera są osobnymi stanami. Awaria jednego punktu nie zatrzymuje pozostałych. Metadane źródła i wybór konkretnego ujęcia trafiają do raportu JSON. Program nie obiecuje automatycznego znalezienia zdjęć w każdym miejscu.

Pierwszym adapterem może być Panoramax i import własnego zdjęcia; Mapillary dodajemy jako opcjonalne źródło wymagające konfiguracji. Inne usługi mogą mieć działanie „Otwórz w serwisie” zamiast automatycznego pobierania, zależnie od udokumentowanych możliwości.

### Etap 2 — fotomontaż turbiny na zdjęciu

Użytkownik wybiera ujęcie, turbinę i jej rzeczywiste wymiary. Ustalamy położenie i wysokość kamery, kierunek, pochylenie, przechylenie oraz pole widzenia. Własne zdjęcie może wymagać danych obiektywu lub ręcznego dopasowania do rozpoznawalnych obiektów. Zdjęcie perspektywiczne i panorama equirektangularna wymagają różnych rzutowań.

Model turbiny jest rzutowany na zdjęcie w odpowiedniej skali. NMT/NMPT dostarcza oszacowanie przesłaniania; przydatna jest ręczna maska pierwszego planu dla elementów niezgodnych z modelem lub datą zdjęcia. Raport zachowuje parametry, metodę dopasowania i niepewność. Eksport obejmuje PNG i HTML z opisem źródła. To większa funkcja niż proste otwarcie Street View.

Przydatne biblioteki do oceny: [OpenCV](https://github.com/opencv/opencv) do kalibracji i projekcji, [SciPy](https://github.com/scipy/scipy) do dopasowania parametrów, [Photo Sphere Viewer](https://github.com/mistic100/Photo-Sphere-Viewer) lub [Marzipano](https://github.com/google/marzipano) do panoram. To propozycje, nie nowe zależności wersji 2.6.0. Pełna turbina wymaga projekcji geometrii, a nie tylko umieszczenia ikony w panoramie.

### Etap 3 — prawdziwe otoczenie 3D w pobliżu punktu

Dodajemy import modelu GLB z plikiem georeferencji lub obsługiwanymi metadanymi. Pierwszy wariant obejmuje niewielkie otoczenie, np. 50–150 m od stanowiska, z istniejącym NMT/NMPT jako dalszym tłem. Obsługujemy tekstury, orientację, dopasowanie wysokości, granice modelu i przełączanie między punktami.

Przydatne projekty: [Three.js / GLTFLoader](https://github.com/mrdoob/three.js) do glTF, [trimesh](https://github.com/mikedh/trimesh) do analizy geometrii, [glTF Transform](https://github.com/donmccurdy/glTF-Transform) i [meshoptimizer](https://github.com/zeux/meshoptimizer) do optymalizacji. Obecny renderer jest własnym rendererem WebGL 1; nie ma importera GLB. Współczesny Three.js wymaga WebGL 2, więc konieczne są wykrycie możliwości sprzętu, jawny wybór renderera i zachowanie lżejszego podglądu.

Budżet pamięci GPU, liczba trójkątów, rozmiar tekstur i poziom szczegółowości muszą być kontrolowane. Wczytujemy detal aktywnego punktu, zwalniamy poprzedni i pokazujemy postęp. Importer powinien odrzucać uszkodzone pliki, obsługiwać brakujące obrazy i nie otwierać automatycznie niekontrolowanych zewnętrznych adresów zasobów modelu.

### Kryteria odbioru

- Kliknięty punkt, stanowisko zdjęcia i kamera 3D są rozróżnione na mapie.
- Kierunek i rozmiar turbiny są sprawdzone na scenie kontrolnej o znanej geometrii.
- Panorama 360° poprawnie przekracza krawędź 0°/360°; zwykłe zdjęcie zachowuje właściwe pole widzenia.
- Brak zdjęć lub modelu pozostawia działającą analizę i pozostałe punkty.
- Model GLB jest sprawdzony względem NMT w kilku miejscach; nie miesza po cichu układów wysokościowych.
- Raport zapisuje źródło, datę, licencję, parametry i ograniczenia. Klucze i tokeny pozostają poza eksportem.
- Test przeglądarki obejmuje prawdziwy obraz, przełączanie punktów, brak błędów WebGL i ograniczenie pamięci.

## Wielkość pracy

Pokazanie dostępnych zdjęć i otwarcie ich z punktu QGIS jest stosunkowo małym rozszerzeniem. Powtarzalny, prawidłowo wyskalowany fotomontaż to średnie lub duże zadanie: najwięcej pracy wymaga kalibracja aparatu i przesłanianie. Swobodne, fotograficzne otoczenie 3D jest większą integracją obejmującą dane, georeferencję, nowy renderer i wydajność. Żadna z omawianych wtyczek nie rozwiązuje samodzielnie wszystkich tych problemów.

Najrozsądniejsza kolejność to: **sprawdzenie pokrycia → wybór rzeczywistego ujęcia → kalibracja i fotomontaż → opcjonalny import teksturowanego otoczenia 3D**. Pozwala to ocenić jakość na kilku ważnych punktach, zanim rozszerzymy pobieranie na duży obszar.

## Źródła i granice weryfikacji

- Aleph: commit [`ad68fc4a3c60fd7af3969597ef0ba886c63b0a40`](https://github.com/Belluxx/Aleph/tree/ad68fc4a3c60fd7af3969597ef0ba886c63b0a40), szczególnie `README.md`, `pyproject.toml`, `docs/cli.md`, `src/mesh.py` i licencja MIT.
- MapillaryClickPreview: commit [`4d71710369116aee65b90a9bef73658aba8c720d`](https://github.com/annadeckmyn/MapillaryClickPreview/tree/4d71710369116aee65b90a9bef73658aba8c720d), szczególnie `README.md`, `metadata.txt`, obsługa podglądu i warstw pokrycia. Kod GPL v2 lub nowsza.
- Eksperymentalny fork Panoramax: commit [`694f8c1fa91024dff397522cf6ba92fb96861683`](https://github.com/IGNF-Xavier/qgis_panoramax/tree/694f8c1fa91024dff397522cf6ba92fb96861683), szczególnie `README.md` i kod kalibracji/obserwacji. Kod GPL v2.
- Oficjalny upstream wskazany przez fork: [Panoramax QGIS Plugin](https://gitlab.com/panoramax/clients/qgis-plugin/). W tym przeglądzie nie weryfikowano osobno jego bieżącego wydania.

Nie instalowano obcych wtyczek ani ich zależności w profilu użytkownika. Nie badano autoryzowanego dostępu do Mapillary ani rzeczywistych panoram. Wnioski o możliwościach integracji opierają się na przeglądzie źródeł, a nie na działającym prototypie fotomontażu. Nowy suplement nie zmienia pakietu instalacyjnego 2.6.0.
