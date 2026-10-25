"""Offline photograph viewer; no web engine, token or external Javascript required."""
import html
import json
from pathlib import Path


def render_photo_html(payload):
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    script = Path(__file__).with_name('photo_montage.js').read_text(encoding='utf-8')
    title = html.escape(payload['photo']['name'])
    template = '''<!doctype html><html lang="pl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · fotomontaż</title><style>
*{box-sizing:border-box}body{margin:0;background:#102c39;color:#e6f3f4;font:15px system-ui,sans-serif}
header{padding:18px 24px;background:#183d4d}h1{font-size:23px;margin:0 0 8px}p{line-height:1.5;margin:8px 0}
.tools{display:flex;flex-wrap:wrap;gap:10px 18px;padding:14px 24px;background:#1d4656;align-items:center}
label{display:flex;align-items:center;gap:7px}input[type=number]{width:82px}input,select,button{font:inherit;padding:7px;border:1px solid #7eabb4;border-radius:5px}
button{background:#a0dfcd;color:#123b43;cursor:pointer}button:hover{background:#c0eedf}button:disabled{opacity:.5;cursor:wait}
.stage{padding:16px 24px;background:#0b1d27}canvas{display:block;width:100%;height:auto;touch-action:none;cursor:grab;background:#203d48}
#status,#warnings,#summary{padding:8px 24px;white-space:pre-wrap}#warnings{color:#ffd889}#summary{color:#add5da}
details{padding:12px 24px;max-width:1200px}summary{cursor:pointer}#progress{color:#b9f4d8}a{color:#a0dfcd}
</style><header><h1>__TITLE__ · zdjęcie terenowe i turbiny</h1>
<p>Własne zdjęcie · model perspektywiczny · zapis offline. Przeciągnij zdjęcie, aby dopasować kierunek i pochylenie kamery.</p></header>
<div class="tools">
<label>Kierunek <input id="heading" type="number" min="0" max="360" step="0.1">°</label>
<label>Pochylenie <input id="pitch" type="number" min="-85" max="85" step="0.1">°</label>
<label>Poziomy kąt widzenia <input id="fov" type="number" min="10" max="140" step="0.1">°</label>
<label><input id="turbines" type="checkbox" checked>Pokaż turbiny</label>
<button id="save">Zapisz fotomontaż PNG</button><button id="settings">Zapisz dopasowanie JSON</button><span id="progress"></span>
</div><details><summary>Dopasowanie i zasłanianie · ustawienia zaawansowane</summary><div class="tools">
<label>Przechylenie <input id="roll" type="number" min="-45" max="45" step="0.1">°</label>
<button id="aim">Patrz na najbliższą turbinę</button><button id="reset">Przywróć ustawienia</button>
<label><input id="occlusion" type="checkbox" checked>Zasłanianie modelem</label>
<label><input id="guides" type="checkbox">Poziom i celownik</label>
<label><input id="labels" type="checkbox">Numery turbin</label>
<label>Kierunek osi wirnika <input id="yaw" type="number" min="0" max="360" step="1">°</label>
<label>Obrót łopat <input id="phase" type="number" min="0" max="360" step="1">°</label>
<label>Krycie <input id="opacity" type="range" min="0" max="1" step="0.05" value="1"></label>
</div><div class="tools">
<label>Narzędzie <select id="mode"><option value="camera">Dopasuj kamerę</option><option value="hide">Zamaluj pierwszy plan</option><option value="restore">Przywróć ręczną maskę</option></select></label>
<label>Pędzel <input id="brush" type="range" min="2" max="100" value="20">px podglądu</label>
<label><input id="show-mask" type="checkbox" checked>Pokaż maskę</label>
<button id="undo">Cofnij maskę</button><button id="clear">Usuń maskę</button>
</div></details><div id="status">Wczytywanie własnego zdjęcia…</div><div id="warnings"></div>
<div class="stage"><canvas id="photo" aria-label="Własne zdjęcie z modelem turbin"></canvas></div><div id="summary"></div>
<details><summary>Jak dopasować zdjęcie i zachować wynik</summary>
<p>Najpierw dopasuj kierunek, pochylenie i przechylenie; potem poziomy kąt widzenia. Wstępna ogniskowa EXIF nie uwzględnia wszystkich korekcji i kadrowania telefonu. Celownik oznacza oś aparatu, a linia poziomu kąt 0° — nie odtworzony horyzont terenu.</p>
<p>Model pokazuje rzeczywistą pozycję i wysokość turbin z atlasu, z uproszczonym kształtem wieży, gondoli i łopat. Kierunek wirnika i położenie łopat są parametrami poglądowymi. Obraz nie jest certyfikowanym fotomontażem ani fotograficzną rekonstrukcją przyszłego obiektu.</p>
<p>Automatyczne zasłanianie jest przybliżeniem z wybranego NMT/NMPT (65 promieni na turbinę, próbkowanie do odległości środka wieży). Nie uwzględnia dokładnej głębokości każdego fragmentu wirnika. Braki danych pozostają niepewne. NMT nie zawiera drzew i domów; NMPT może pochodzić z innej daty niż zdjęcie. Ręczna maska pozwala schować turbinę za rzeczywistym pierwszym planem. Zmiana maski nie zmienia analizy widoczności.</p>
<p>PNG zachowuje rozdzielczość przygotowanego zdjęcia, do 6000 px i 24 MP. Plik JSON zapisuje dopasowanie i maskę; wczytaj go przyciskiem „Wczytaj dopasowanie JSON” w QGIS, aby zachować zmiany przy ponownym przygotowaniu. Przeglądarka nie nadpisuje automatycznie raportu QGIS. Zmianę miejsca lub wysokości aparatu wykonaj we wtyczce i przygotuj zdjęcie ponownie.</p>
</details><script>const photoScene=__DATA__;</script><script>__SCRIPT__</script></html>'''
    return template.replace('__TITLE__', title).replace('__DATA__', data).replace('__SCRIPT__', script)
