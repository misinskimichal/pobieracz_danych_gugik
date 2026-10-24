"""Atlas layers, publication layouts and a self-contained visual HTML report. GUI thread only."""
from datetime import datetime
import html
import json
from pathlib import Path

from qgis.PyQt.QtCore import QDateTime, QObject, QSizeF, QTimeZone, QTimer, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    QgsCategorizedSymbolRenderer, QgsColorRampShader, QgsCoordinateReferenceSystem, QgsFillSymbol, QgsGraduatedSymbolRenderer,
    QgsLayoutExporter, QgsLayoutItemLabel, QgsLayoutItemLegend, QgsLayoutItemMap,
    QgsLayoutItemPage, QgsLayoutItemPicture, QgsLayoutItemScaleBar, QgsLayoutPoint, QgsLayoutSize, QgsLineSymbol,
    QgsMapRendererParallelJob, QgsMapSettings, QgsRendererCategory,
    QgsMarkerSymbol, QgsPalettedRasterRenderer, QgsPrintLayout, QgsProject,
    QgsRasterLayer, QgsRasterShader, QgsRectangle, QgsRendererRange,
    QgsSingleBandPseudoColorRenderer, QgsSvgMarkerSymbolLayer, QgsVectorLayer,
)
from .core import VERSION, atomic_json

KEY = 'nmt_nmpt/atlas_run'
QUALITY = [(1, '#00000000', 'Komplet danych modelu'), (2, '#805288aa', 'Niepewna trasa — brakujące dane'),
           (3, '#c0b5a5cf', 'Brak danych w miejscu obserwacji'), (4, '#65a6aeb1', 'Dach / korona na wysokości oka')]
ROTOR = [(1, '#183e4f', 'Przesłonięta'), (2, '#6b4bc5', 'Widać górny zasięg łopaty'),
         (3, '#ec638b', 'Widać także piastę'), (4, '#ffcc66', 'Widać także dolny zasięg wirnika'),
         (5, '#9d99b4', 'Nierozstrzygnięte')]


def palette(layer, classes):
    renderer = QgsPalettedRasterRenderer(layer.dataProvider(), 1, [
        QgsPalettedRasterRenderer.Class(value, QColor(color), label) for value, color, label in classes])
    layer.setRenderer(renderer)


def count_style(layer, maximum, binary=False):
    ramp = QgsColorRampShader(0, max(1, maximum))
    ramp.setColorRampType(QgsColorRampShader.Interpolated)
    items = [(0, '#20263d49', 'Brak widocznych turbin'), (1, '#22bec5', '1 turbina')]
    if not binary and maximum > 1:
        items = [(0, '#20263d49', 'Brak widocznych turbin'), (1, '#2ac4b7', '1 turbina'),
                 (1 + (maximum - 1) * 0.45, '#b9d86a', 'Więcej widocznych turbin'),
                 (maximum, '#f05791', f'{maximum} turbin')]
    ramp.setColorRampItemList([QgsColorRampShader.ColorRampItem(v, QColor(c), label) for v, c, label in items])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp)
    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    renderer.setClassificationMin(0)
    renderer.setClassificationMax(max(1, maximum))
    layer.setRenderer(renderer)
    layer.setOpacity(0.83)


def turbine_number(count):
    if count == 1:
        return '1 turbina'
    return str(count) + (' turbiny' if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14) else ' turbin')


def count_color(value, maximum):
    stops = [(0, QColor('#667987')), (1, QColor('#2ac4b7'))]
    if maximum > 1:
        stops.extend([(1 + (maximum - 1) * .45, QColor('#b9d86a')), (maximum, QColor('#f05791'))])
    for (a, ca), (b, cb) in zip(stops[:-1], stops[1:]):
        if value <= b:
            f = (value - a) / (b - a)
            return QColor(round(ca.red() + (cb.red() - ca.red()) * f), round(ca.green() + (cb.green() - ca.green()) * f),
                          round(ca.blue() + (cb.blue() - ca.blue()) * f)).name()
    return stops[-1][1].name()


def exposure_style(layer):
    for field, title in [('widoczne_pct', 'Próbki z widocznością ≥1 turbiny [%]'),
                         ('niepewne_pct', 'Próbki z niepewnością lub okiem pod powierzchnią [%]'),
                         ('probki', 'Liczba sprawdzonych próbek')]:
        index = layer.fields().indexFromName(field)
        if index >= 0:
            layer.setFieldAlias(index, title)
    ranges = []
    for low, high, color, label in [(0, 0, '#84949f', 'Brak potwierdzonej widoczności'),
                                    (0.001, 25, '#29b9bf', 'Widoczność do 25% próbek'),
                                    (25, 75, '#f3b454', 'Widoczność 25–75% próbek'),
                                    (75, 100, '#ef5e7b', 'Widoczność 75–100% próbek')]:
        if layer.geometryType() == 0:
            symbol = QgsMarkerSymbol.createSimple(dict(name='circle', color=color, outline_color='white', size='3.2'))
        elif layer.geometryType() == 1:
            symbol = QgsLineSymbol.createSimple(dict(line_color='#ffffff', line_width='1.5'))
            inner = QgsLineSymbol.createSimple(dict(line_color=color, line_width='0.85'))
            symbol.appendSymbolLayer(inner.takeSymbolLayer(0))
        else:
            rgba = QColor(color)
            symbol = QgsFillSymbol.createSimple(dict(color=f'{rgba.red()},{rgba.green()},{rgba.blue()},45',
                                                     outline_color=color, outline_width='0.45'))
        ranges.append(QgsRendererRange(low, high, symbol, label))
    layer.setRenderer(QgsGraduatedSymbolRenderer('widoczne_pct', ranges))


def ray_style(layer, field='piasta'):
    categories = []
    for value, color, title in [(0, '#e15465', 'Zasłonięta'), (1, '#18b67a', 'Widoczna'),
                                (2, '#9977cd', 'Brak rozstrzygnięcia'), (3, '#88949c', 'Oko pod powierzchnią')]:
        symbol = QgsLineSymbol.createSimple(dict(line_color=color, line_width='0.38', line_style='dash' if value >= 2 else 'solid'))
        categories.append(QgsRendererCategory(value, symbol, title))
    layer.setRenderer(QgsCategorizedSymbolRenderer(field, categories))


def elevation_style(layer):
    from osgeo import gdal
    ds = gdal.Open(layer.source())
    stats = ds.GetRasterBand(1).GetStatistics(True, False)
    ds = None
    low, high = (stats[0], stats[1]) if stats and stats[3] >= 0 else (0, 300)
    high = max(high, low + 1)
    ramp = QgsColorRampShader(low, high)
    ramp.setColorRampType(QgsColorRampShader.Interpolated)
    ramp.setColorRampItemList([QgsColorRampShader.ColorRampItem(low + (high-low)*f, QColor(c), f'{low+(high-low)*f:.1f} m')
                              for f, c in [(0, '#21865a'), (.5, '#e4d45e'), (1, '#d34747')]])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp)
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader))


def add_atlas(report, iface=None, show=True):
    project = QgsProject.instance()
    run = report['report_dir']
    existing = [layer for layer in project.mapLayers().values() if layer.customProperty(KEY, '') == run]
    if existing:
        if show:
            node = project.layerTreeRoot().findLayer(existing[0].id())
            while node:
                if node.customProperty(KEY, '') == run or node.name().startswith('Atlas widoczności ·'):
                    node.setItemVisibilityChecked(True)
                    break
                node = node.parent()
        return {layer.customProperty('nmt_nmpt/atlas_key'): layer for layer in existing}
    root = project.layerTreeRoot()
    group = root.insertGroup(0, 'Atlas widoczności · ' + Path(run).name.replace('atlas_', ''))
    group.setCustomProperty(KEY, run)
    group.setItemVisibilityChecked(show)
    layers = {}

    def add(layer, parent, key, checked=True):
        if not layer.isValid():
            raise ValueError('Nie można otworzyć wyniku: ' + layer.name())
        layer.setCustomProperty(KEY, run)
        layer.setCustomProperty('nmt_nmpt/atlas_key', key)
        project.addMapLayer(layer, False)
        node = parent.addLayer(layer)
        node.setItemVisibilityChecked(checked)
        layers[key] = layer
        layer.saveNamedStyle(str(Path(layer.source().split('|')[0]).with_suffix('.qml')) if layer.type() == layer.RasterLayer
                             else str(Path(run) / (key.replace('/', '_') + '.qml')))
        return layer

    if report.get('links_gpkg'):
        from .atlas_links import configure_links
        links = QgsVectorLayer(report['links_gpkg'] + '|layername=raport', 'Raport HTML i sceny 3D · prawy przycisk', 'ogr')
        configure_links(links)
        links.renderer().setSymbol(QgsFillSymbol.createSimple(dict(color='0,0,0,0', outline_color='#18a991', outline_style='dash')))
        add(links, group, 'report_links', False)

    if report.get('gpkg'):
        turbines = QgsVectorLayer(report['gpkg'] + '|layername=turbiny', 'Turbiny — wysokość piasty i wirnik', 'ogr')
        symbol = QgsMarkerSymbol()
        symbol.changeSymbolLayer(0, QgsSvgMarkerSymbolLayer(str(Path(__file__).with_name('wind.svg')), 7))
        turbines.renderer().setSymbol(symbol)
        add(turbines, group, 'turbines')
    for product in reversed(report['products']):
        resource = product['resource']
        model_group = group.addGroup(f'{resource} · promień {product["radius"] / 1000:g} km · krok {product["resolution"]:g} m')
        preferred = 'NMPT' if any(p['resource'] == 'NMPT' for p in report['products']) else 'NMT'
        model_group.setItemVisibilityChecked(resource == preferred)
        if report.get('gpkg'):
            circles = QgsVectorLayer(report['gpkg'] + '|layername=kola_' + resource, resource + ' — granice analizy', 'ogr')
            circles.renderer().setSymbol(QgsFillSymbol.createSimple(dict(color='0,0,0,0', outline_color='#224854',
                                                                         outline_width='0.45', outline_style='dash')))
            add(circles, model_group, resource + '/circles')
            for item in report.get('context_summary', []):
                if item['model'] != resource:
                    continue
                role = item['role']
                titles = {'drogi': 'Drogi — ekspozycja', 'zabudowa': 'Zabudowa — ekspozycja obrysu', 'obserwatorzy': 'Obserwatorzy — ekspozycja'}
                context = QgsVectorLayer(report['gpkg'] + '|layername=' + role + '_' + resource, titles[role] + ' ' + resource, 'ogr')
                exposure_style(context)
                add(context, model_group, resource + '/' + role)
        if report.get('rays_gpkg'):
            rays = QgsVectorLayer(report['rays_gpkg'] + '|layername=promienie_' + resource,
                                  resource + ' — promienie: widoczność piasty', 'ogr')
            for field, title in [('piasta', 'Widoczność piasty'), ('koniec', 'Widoczność końca łopaty'), ('dolny', 'Widoczność dolnego zasięgu')]:
                ray_style(rays, field)
                rays.styleManager().addStyleFromLayer(title)
            rays.styleManager().setCurrentStyle('Widoczność piasty')
            add(rays, model_group, resource + '/rays', False)
        quality = QgsRasterLayer(product['paths']['quality'], resource + ' — jakość i brakujące dane')
        palette(quality, QUALITY)
        add(quality, model_group, resource + '/quality')
        count = QgsRasterLayer(product['paths']['count'], resource + ' — ile turbin widać')
        maximum = len(report.get('turbines', []))
        count_style(count, maximum)
        count.styleManager().addStyleFromLayer('Ile turbin widać')
        count_style(count, maximum, True)
        count.styleManager().addStyleFromLayer('Widoczność i cienie')
        count.styleManager().setCurrentStyle('Ile turbin widać')
        add(count, model_group, resource + '/count')
        rotor = QgsRasterLayer(product['paths']['rotor'], resource + ' — zakres widocznego wirnika')
        palette(rotor, ROTOR)
        rotor.setOpacity(0.82)
        add(rotor, model_group, resource + '/rotor', False)
        if product['paths'].get('elevation'):
            elevation = QgsRasterLayer(product['paths']['elevation'], resource + ' — wysokość: zielony nisko / czerwony wysoko')
            elevation_style(elevation)
            add(elevation, model_group, resource + '/elevation', False)
        if product['paths'].get('hillshade'):
            hill = QgsRasterLayer(product['paths']['hillshade'], resource + ' — cieniowanie terenu')
            hill.setOpacity(0.45)
            add(hill, model_group, resource + '/hillshade')
    if iface is not None and report['products']:
        preferred = next((p for p in report['products'] if p['resource'] == 'NMPT'), report['products'][0])
        from qgis.core import QgsCoordinateTransform
        canvas = iface.mapCanvas()
        extent = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:2180'), canvas.mapSettings().destinationCrs(),
                                        project.transformContext()).transformBoundingBox(QgsRectangle(*preferred['bounds']))
        extent.scale(1.08)
        canvas.setExtent(extent)
        canvas.refresh()
    return layers


def build_layout(report, layers, project=None):
    project = project or QgsProject.instance()
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    title = 'Atlas widoczności ' + Path(report['report_dir']).name
    number = 1
    unique = title
    while project.layoutManager().layoutByName(unique) is not None:
        number += 1
        unique = title + f' ({number})'
    layout.setName(unique)
    # Qt bundles Windows/IANA timezone mappings; no extra Python tzdata dependency.
    warsaw = QTimeZone(b'Europe/Warsaw')
    generated = QDateTime.currentDateTimeUtc().toTimeZone(warsaw).toString('dd.MM.yyyy HH:mm')
    base_layers = []
    for layer in project.layerTreeRoot().layerOrder():
        node = project.layerTreeRoot().findLayer(layer.id())
        if node and node.isVisible() and not layer.customProperty(KEY, '') and not layer.customProperty('nmt_nmpt/index_folder', ''):
            base_layers.append(layer)

    def label(text, x, y, width, height, size=10, color='#183c4e', background=None):
        item = QgsLayoutItemLabel(layout)
        item.setText(text)
        item.setFont(QFont('Noto Sans', size))
        item.setFontColor(QColor(color))
        if background:
            item.setBackgroundEnabled(True)
            item.setBackgroundColor(QColor(background))
        layout.addLayoutItem(item)
        item.attemptMove(QgsLayoutPoint(x, y))
        item.attemptResize(QgsLayoutSize(width, height))
        return item

    for page_number, product in enumerate(report['products']):
        if page_number == 0:
            page = layout.pageCollection().pages()[0]
        else:
            page = QgsLayoutItemPage(layout)
            layout.pageCollection().addPage(page)
        page.setPageSize('A4', QgsLayoutItemPage.Landscape)
        offset = page.pos().y()
        resource = product['resource']
        label('', 0, offset, 297, 26, background='#153747')
        label('ATLAS WIDOCZNOŚCI TURBIN', 8, offset + 3, 280, 11, 19, '#ffffff')
        subtitle = f'{resource} · {"rzeźba terenu" if resource == "NMT" else "teren, drzewa i zabudowa"} · promień {product["radius"] / 1000:g} km · krok {product["resolution"]:g} m'
        label(subtitle, 8, offset + 16, 280, 7, 10, '#8fe1d6')
        ordered = [layers[k] for k in ['turbines', resource + '/circles', resource + '/obserwatorzy',
                                       resource + '/zabudowa', resource + '/drogi', resource + '/quality',
                                       resource + '/count', resource + '/hillshade'] if k in layers]
        map_item = QgsLayoutItemMap(layout)
        layout.addLayoutItem(map_item)
        map_item.attemptMove(QgsLayoutPoint(8, offset + 33))
        map_item.attemptResize(QgsLayoutSize(213, 155))
        map_item.setCrs(QgsCoordinateReferenceSystem('EPSG:2180'))
        map_item.setLayers(ordered + base_layers)
        map_item.setKeepLayerSet(True)
        extent = QgsRectangle(*product['bounds'])
        extent.scale(1.07)
        map_item.zoomToExtent(extent)
        map_item.setFrameEnabled(True)
        map_item.setFrameStrokeColor(QColor('#c4d4d8'))
        label('N\n↑', 208, offset + 36, 9, 17, 15)
        scale = QgsLayoutItemScaleBar(layout)
        scale.setStyle('Single Box')
        scale.setLinkedMap(map_item)
        scale.setNumberOfSegments(2)
        scale.setNumberOfSegmentsLeft(0)
        scale.applyDefaultSize()
        layout.addLayoutItem(scale)
        scale.attemptMove(QgsLayoutPoint(13, offset + 176))
        scale.setBackgroundEnabled(True)
        scale.setBackgroundColor(QColor('#eaffffff'))
        summary = product.get('summary', {})
        label('', 227, offset + 33, 62, 155, background='#eef4f5')
        label(resource + '  /  EKSPOZYCJA', 231, offset + 36, 55, 9, 12)
        maximum = len(report.get('turbines', []))
        label(turbine_number(maximum), 231, offset + 47, 55, 12, 19)
        label(f'Obszar: {summary.get("area_km2", 0):.2f} km²\nWidoczna ≥1: {summary.get("visible_km2", 0):.2f} km²',
              231, offset + 61, 55, 16, 10)
        label('ILE TURBIN WIDAĆ', 231, offset + 82, 55, 7, 9)
        stops = list(range(maximum + 1)) if maximum <= 4 else sorted(set([0, 1, round(maximum / 2), round(maximum * .75), maximum]))
        for number, value in enumerate(stops):
            y = offset + 92 + number * 6
            label('', 232, y + 1, 5, 4, background=count_color(value, maximum))
            label('0 — brak widoczności' if value == 0 else turbine_number(value), 240, y, 46, 6, 8)
        label('JAKOŚĆ DANYCH', 231, offset + 126, 55, 7, 9)
        for number, (color, text) in enumerate([('#5288aa', 'Niepewna trasa\n(brak danych)'),
                                                ('#b5a5cf', 'Brak danych\nw miejscu obserwacji'),
                                                ('#a6aeb1', 'Dach / korona\nna wysokości oka')]):
            y = offset + 136 + number * 10
            label('', 232, y + 1, 5, 5, background=color)
            label(text, 240, y - 1, 46, 10, 7)
        label(f'Oko nad gruntem: {report["options"]["eye"]:g} m.\nKolor opisuje widoczność\nw wybranym modelu.',
              231, offset + 172, 55, 15, 7)
        label(f'{generated} · EPSG:2180 · {product["height"]} · NMT i NMTP ściągacz {VERSION}',
              8, offset + 193, 282, 7, 8, '#526b76')
        footer = 'DANE SYNTETYCZNE — demonstracja działania, nie analiza rzeczywistej inwestycji.' if report['options'].get('demo') else 'Model rastrowy 2,5D. Trzy wysokości wirnika nie oznaczają procentu jego widocznej powierzchni.'
        label(footer,
              8, offset + 200, 282, 6, 7, '#526b76')
    project.layoutManager().addLayout(layout)
    return layout


def export_atlas(report, layers, project=None):
    """Synchronous helper for scripts. The plugin UI uses AsyncAtlasExport below."""
    return export_layout(report, build_layout(report, layers, project))


def export_layout(report, layout):
    folder = Path(report['report_dir'])
    exporter = QgsLayoutExporter(layout)
    pdf_options = QgsLayoutExporter.PdfExportSettings()
    pdf_options.dpi = 150
    pdf_options.rasterizeWholeImage = True
    pdf_options.appendGeoreference = False
    pdf_options.exportMetadata = False
    pdf_result = exporter.exportToPdf(str(folder / 'atlas.pdf'), pdf_options)
    image_result = QgsLayoutExporter.Success
    png = []
    for page in range(layout.pageCollection().pageCount()):
        image = exporter.renderPageToImage(page, dpi=120)
        path = folder / ('atlas.png' if page == 0 else f'atlas_{page+1}.png')
        if image.isNull() or not image.save(str(path), 'PNG'):
            image_result = QgsLayoutExporter.FileError
        else:
            png.append(str(path))
    presentation = dict(layout=layout.name(), pdf=str(folder / 'atlas.pdf') if pdf_result == QgsLayoutExporter.Success else None,
                        pdf_status=int(pdf_result), image_status=int(image_result),
                        png=png)
    make_html(report, presentation)
    report['presentation'] = presentation
    atomic_json(folder / 'report.json', report)
    return presentation


class AsyncAtlasExport(QObject):
    """Render provider data with QGIS' asynchronous renderer; only bounded page assembly on GUI.

    QgsProject/QgsPrintLayout never cross Python worker threads. Cached map pictures keep
    the final PDF/PNG assembly independent of slow WMS services and large source rasters.
    """
    completed = pyqtSignal(object)
    status = pyqtSignal(str)

    def __init__(self, report, layers, parent=None):
        super().__init__(parent)
        self.report, self.layers = report, layers
        self.layout = self.job = None
        self.index, self.canceled = 0, False
        self.maps = []

    def start(self):
        QTimer.singleShot(0, self.prepare)

    def prepare(self):
        if self.canceled:
            self.completed.emit(dict(canceled=True))
            return
        try:
            self.layout = build_layout(self.report, self.layers)
            self.maps = sorted([i for i in self.layout.items() if isinstance(i, QgsLayoutItemMap)], key=lambda i: i.pos().y())
            self.next_map()
        except Exception as exc:
            self.fail(exc)

    def next_map(self):
        if self.canceled:
            self.completed.emit(dict(canceled=True))
            return
        try:
            if self.index == len(self.maps):
                self.status.emit('Składanie gotowych obrazów w PDF / PNG i HTML…')
                QTimer.singleShot(0, self.finish)
                return
            item = self.maps[self.index]
            self.status.emit(f'Renderowanie mapy w tle {self.index + 1}/{len(self.maps)} — QGIS pozostaje dostępny')
            size = item.sizeWithUnits()
            settings = item.mapSettings(item.extent(), QSizeF(size.width() * 150 / 25.4, size.height() * 150 / 25.4), 150, True)
            settings.setFlag(QgsMapSettings.ForceVectorOutput, False)
            self.job = QgsMapRendererParallelJob(settings)
            self.job.finished.connect(self.rendered)
            self.job.start()
        except Exception as exc:
            self.fail(exc)

    def rendered(self):
        if self.canceled:
            self.job = None
            self.completed.emit(dict(canceled=True))
            return
        try:
            errors = [e.message for e in self.job.errors()]
            if errors:
                raise ValueError('Renderowanie: ' + '; '.join(errors))
            image = self.job.renderedImage()
            cache = Path(self.report['report_dir']) / 'mapy_atlasu'
            cache.mkdir(exist_ok=True)
            path = cache / f'mapa_{self.index + 1}.png'
            if image.isNull() or not image.save(str(path), 'PNG'):
                raise ValueError('Nie można zapisać obrazu mapy')
            item = self.maps[self.index]
            picture = QgsLayoutItemPicture(self.layout)
            self.layout.addLayoutItem(picture)
            picture.attemptMove(QgsLayoutPoint(item.pos().x(), item.pos().y()))
            picture.attemptResize(item.sizeWithUnits())
            picture.setPicturePath(str(path))
            picture.setZValue(item.zValue())
            picture.setFrameEnabled(True)
            picture.setFrameStrokeColor(QColor('#c4d4d8'))
            item.setVisibility(False)
            self.index += 1
            self.job = None
            QTimer.singleShot(0, self.next_map)
        except Exception as exc:
            self.fail(exc)

    def finish(self):
        if self.canceled:
            self.completed.emit(dict(canceled=True))
            return
        try:
            self.completed.emit(export_layout(self.report, self.layout))
        except Exception as exc:
            self.fail(exc)

    def fail(self, exc):
        self.job = None
        self.completed.emit(dict(error=str(exc)))

    def cancel(self):
        self.canceled = True
        if self.job:
            self.status.emit('Anulowanie renderowania — obliczone dane zostają na dysku')
            self.job.cancelWithoutBlocking()


def make_html(report, presentation):
    folder = Path(report['report_dir'])
    cards = []
    for product in report['products']:
        summary = product.get('summary', {})
        cards.append(f'<article><small>{html.escape(product["resource"])}</small><strong>{summary.get("visible_km2", 0):.2f} km²</strong>'
                     f'<span>z widocznością co najmniej jednej turbiny · promień {product["radius"] / 1000:g} km · krok {product["resolution"]:g} m</span></article>')
    pages = ''.join(f'<a href="{html.escape(Path(p).name)}"><img alt="Mapa atlasu" src="{html.escape(Path(p).name)}"></a>' for p in presentation['png'])
    text = '<!doctype html><html lang="pl"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Atlas widoczności turbin</title>'
    text += '''<style>body{margin:0;background:#eef3f5;color:#153747;font:16px system-ui,sans-serif}header{background:#153747;color:white;padding:36px max(24px,6vw)}header small{color:#89e0d4;letter-spacing:.18em}h1{margin:.4em 0;font-size:clamp(25px,4vw,44px)}main{max-width:1250px;margin:26px auto;padding:0 20px}.cards{display:flex;gap:18px;flex-wrap:wrap}article{background:white;border-radius:16px;padding:24px;box-shadow:0 8px 24px #1237460a;flex:1;min-width:230px}article small{font-weight:700;color:#16a79c}strong{display:block;font-size:34px;margin:12px 0}span{line-height:1.6;color:#526d7b}img{width:100%;height:auto;margin:24px 0 0;border-radius:12px;box-shadow:0 10px 36px #15374718}nav{margin:24px 0;display:flex;gap:14px;flex-wrap:wrap}nav a{background:#153747;color:white;text-decoration:none;padding:12px 18px;border-radius:9px}aside{background:#fff;padding:22px;border-radius:12px;line-height:1.7}footer{font-size:13px;color:#57717d;margin:26px 0}</style>'''
    text += '<header><small>KRAJOBRAZ · EKSPOZYCJA · TURBINY</small><h1>Atlas widoczności</h1><p>Całe otoczenie inwestycji. NMT i NMPT w osobnych, porównywalnych modelach.</p></header><main>'
    text += '<div class="cards">' + ''.join(cards) + '</div><nav><a href="atlas.pdf">Atlas PDF</a><a href="atlas.gpkg">Warstwy GeoPackage</a><a href="ekspozycja.csv">Ekspozycja CSV</a><a href="report.md">Raport</a></nav>'
    text += pages + '<aside><b>Jak czytać mapę i procenty</b><br>Kolor pokazuje potwierdzoną w modelu liczbę widocznych turbin. Fiolet oznacza nierozstrzygniętą trasę lub brak danych; szare pokrycie może oznaczać dach lub koronę na wysokości oka. NMT opisuje sam teren, NMPT uwzględnia jego pokrycie. Widoczność trzech punktów wirnika nie mierzy widocznej powierzchni łopat.<br><b>widoczne_pct = udział próbek z widocznością co najmniej jednej turbiny.</b> 80% to np. 8 z 10 sprawdzonych miejsc przy drodze lub obrysie budynku. To nie 80% działki ani wirnika. <b>niepewne_pct</b> to próbki z niepewnością lub okiem pod powierzchnią; obie kategorie mogą się nakładać przy wielu turbinach.</aside>'
    for item in report.get('details', []):
        profile, scene = html.escape(Path(item['profile']).name), html.escape(Path(item['scene']).name)
        text += (f'<h2>{html.escape(item["model"])} · przekrój i scena 3D</h2><nav><a href="{scene}">Obróć scenę 3D</a>'
                 f'<a href="{profile}">Otwórz przekrój</a></nav><img src="{profile}" alt="Przekrój terenu i linii widzenia">')
    text += f'<footer>NMT i NMTP ściągacz {VERSION} · mapy i dane pozostają w tym folderze. Zachowaj cały katalog, aby HTML działał także bez internetu.</footer></main></html>'
    (folder / 'atlas.html').write_text(text, encoding='utf-8')
    presentation['html'] = str(folder / 'atlas.html')
