"""Persistent report footprint and layer-tree shortcuts, restored with the project."""
from pathlib import Path
import html

from osgeo import ogr
from qgis.PyQt.QtCore import QObject, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsAction, QgsMapLayer, QgsProject

PROPERTY = 'nmt_nmpt/report_links'


def write_shortcuts(folder, report):
    from .atlas import srs2180
    path = Path(folder) / 'raport.gpkg'
    dataset = ogr.GetDriverByName('GPKG').CreateDataSource(str(path))
    layer = dataset.CreateLayer('raport', srs2180(), ogr.wkbPolygon)
    for name in ['model', 'turbina', 'raport_html', 'raport_json', 'scena_3d', 'profil']:
        layer.CreateField(ogr.FieldDefn(name, ogr.OFTString))
    from qgis.core import QgsGeometry, QgsPointXY
    for product in report['products']:
        detail = next((d for d in report.get('details', []) if d['model'] == product['resource']), {})
        for turbine in report['turbines']:
            feature = ogr.Feature(layer.GetLayerDefn())
            values = dict(model=product['resource'], turbina=str(turbine['id']),
                          raport_html=(Path(folder) / 'atlas.html').resolve().as_uri(),
                          raport_json=(Path(folder) / 'report.json').resolve().as_uri(),
                          scena_3d=Path(detail['scene']).resolve().as_uri() if detail else '',
                          profil=Path(detail['profile']).resolve().as_uri() if detail else '')
            for key, value in values.items():
                feature.SetField(key, value)
            geometry = QgsGeometry.fromPointXY(QgsPointXY(turbine['x'], turbine['y'])).buffer(product['radius'], 64)
            feature.SetGeometry(ogr.CreateGeometryFromWkb(bytes(geometry.asWkb())))
            if layer.CreateFeature(feature) != 0:
                raise ValueError('Nie można zapisać odnośników atlasu')
    layer, dataset = None, None
    # A local HTML entry point is useful even when PDF/map export is disabled.
    links = [('report.md', 'Raport opisowy'), ('report.json', 'Diagnostyka JSON')]
    for detail in report.get('details', []):
        links.extend([(Path(detail['scene']).name, 'Scena 3D ' + detail['model']),
                      (Path(detail['profile']).name, 'Przekrój ' + detail['model'])])
    body = ''.join(f'<li><a href="{html.escape(filename)}">{html.escape(label)}</a></li>' for filename, label in links)
    (Path(folder) / 'atlas.html').write_text('<!doctype html><html lang="pl"><meta charset="utf-8">'
                                             '<title>Atlas widoczności</title><style>body{font:18px system-ui;padding:32px;'
                                             'background:#edf3f5;color:#153747}li{margin:16px 0}</style><h1>Atlas widoczności</h1>'
                                             '<p>Wyniki i sceny w lokalnym folderze. Procenty ekspozycji dotyczą próbek, nie powierzchni wirnika.</p><ul>'
                                             + body + '</ul></html>', encoding='utf-8')
    return str(path)


def configure_links(layer):
    layer.setCustomProperty(PROPERTY, True)
    for field, title in [('raport_html', 'Otwórz raport HTML'), ('scena_3d', 'Otwórz scenę 3D'),
                         ('profil', 'Otwórz przekrój'), ('raport_json', 'Otwórz diagnostykę JSON')]:
        action = QgsAction(QgsAction.OpenUrl, title, '[% "' + field + '" %]')
        action.setActionScopes({'Feature', 'Field'})
        layer.actions().addAction(action)


class AtlasLinks(QObject):
    def __init__(self, iface, on_load=None):
        super().__init__(iface.mainWindow())
        self.iface, self.actions = iface, {}
        self.on_load = on_load
        self.project = QgsProject.instance()
        self.project.layersAdded.connect(self.attach)
        self.project.layersWillBeRemoved.connect(self.remove)
        self.attach(list(self.project.mapLayers().values()))

    def attach(self, layers):
        if not hasattr(self.iface, 'addCustomActionForLayerType'):
            return  # Also supports minimal PyQGIS script interfaces.
        for layer in layers:
            if not layer.customProperty(PROPERTY, False) or layer.id() in self.actions:
                continue
            folder = Path(layer.source().split('|')[0]).parent
            paths = [('Otwórz raport HTML', folder / 'atlas.html'), ('Otwórz raport / diagnostykę', folder / 'report.md')]
            for resource in ['NMPT', 'NMT']:
                for label, filename in [('Scena 3D', f'scena_3d_{resource}.html'), ('Przekrój', f'profil_{resource}.svg')]:
                    if (folder / filename).is_file():
                        paths.append((label + ' ' + resource, folder / filename))
            registered = []
            for label, path in paths:
                action = QAction(label, self)
                action.triggered.connect(lambda checked=False, target=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))))
                self.iface.addCustomActionForLayerType(action, '', QgsMapLayer.VectorLayer, False)
                self.iface.addCustomActionForLayer(action, layer)
                registered.append(action)
            if self.on_load:
                action = QAction('Wczytaj ustawienia do ponownego przeliczenia', self)
                action.triggered.connect(lambda checked=False, target=folder / 'report.json': self.on_load(target))
                self.iface.addCustomActionForLayerType(action, '', QgsMapLayer.VectorLayer, False)
                self.iface.addCustomActionForLayer(action, layer)
                registered.append(action)
            self.actions[layer.id()] = registered

    def remove(self, ids):
        for layer_id in ids:
            for action in self.actions.pop(layer_id, []):
                self.iface.removeCustomActionForLayerType(action)
                action.deleteLater()

    def stop(self):
        self.project.layersAdded.disconnect(self.attach)
        self.project.layersWillBeRemoved.disconnect(self.remove)
        self.remove(list(self.actions))
