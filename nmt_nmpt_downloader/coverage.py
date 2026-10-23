"""Persistent GeoPackage tile indexes, incrementally synchronized with local folders."""
import math
import os
import re
from pathlib import Path

from osgeo import gdal
from qgis.PyQt.QtCore import QFileSystemWatcher, QObject, QTimer, QVariant
from qgis.core import (
    QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsCoordinateTransformContext,
    QgsFeature, QgsField, QgsFillSymbol, QgsGeometry, QgsMessageLog, QgsProject, QgsRasterLayer,
    QgsRectangle, QgsTask, QgsVectorFileWriter, QgsVectorLayer,
)

KEY = 'nmt_nmpt/index_folder'
RESOURCE_KEY = 'nmt_nmpt/index_resource'
FIELDS = [('plik', QVariant.String), ('sciezka', QVariant.String), ('zasob', QVariant.String),
          ('piksel_m', QVariant.Double), ('uklad_wys', QVariant.String), ('rozmiar_MB', QVariant.Double),
          ('mtime_ns', QVariant.String), ('bajty', QVariant.String)]


def canonical(path):
    return os.path.normcase(str(Path(path).resolve()))


def scan_folder(folder, resource, cache, context, canceled):
    """Read headers only for new/modified rasters; do not retain GDAL handles."""
    records, errors = {}, []
    for path in Path(folder).iterdir():
        if canceled():
            return None, []
        if path.name.startswith('.') or path.suffix.lower() not in ('.tif', '.tiff', '.asc') or not path.is_file():
            continue
        key = canonical(path)
        try:
            info = path.stat()
            previous = cache.get(key)
            if previous and previous['mtime_ns'] == str(info.st_mtime_ns) and previous['bajty'] == str(info.st_size):
                records[key] = previous
                continue
            ds = gdal.Open(str(path), gdal.GA_ReadOnly)
            if ds is None:
                raise ValueError('Nieczytelny raster')
            coverage = ds.GetMetadataItem('COVERAGE') or ''
            kind = ds.GetMetadataItem('RESOURCE') or ('NMPT' if coverage.startswith('DSM_') else 'NMT' if coverage.startswith('DTM_') else resource)
            if kind != resource:
                continue
            crs = QgsCoordinateReferenceSystem(ds.GetProjection())
            if not crs.isValid():
                raise ValueError('Brak układu współrzędnych rastra')
            gt = ds.GetGeoTransform()
            points = [(gt[0] + x * gt[1] + y * gt[2], gt[3] + x * gt[4] + y * gt[5])
                      for x, y in [(0, 0), (ds.RasterXSize, 0), (ds.RasterXSize, ds.RasterYSize), (0, ds.RasterYSize), (0, 0)]]
            geom = QgsGeometry.fromWkt('POLYGON((' + ','.join(f'{x} {y}' for x, y in points) + '))')
            geom.transform(QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem('EPSG:2180'), context))
            height = ds.GetMetadataItem('HEIGHT_SYSTEM')
            if not height:
                match = re.search(r'PL-(?:EVRF2007|KRON86)-NH', coverage + path.name)
                height = match.group(0) if match else 'nieznany'
            records[key] = dict(plik=path.name, sciezka=str(path.resolve()), zasob=resource,
                                piksel_m=math.hypot(gt[1], gt[4]) if crs.authid() == 'EPSG:2180' else None,
                                uklad_wys=height, rozmiar_MB=info.st_size / 1e6,
                                mtime_ns=str(info.st_mtime_ns), bajty=str(info.st_size), wkt=geom.asWkt(6))
            ds = None
        except Exception as exc:
            errors.append(f'{path.name}: {exc}')
            # Preserve the old extent while a modified file may still be written.
            if key in cache:
                records[key] = cache[key]
    return records, errors


class ScanTask(QgsTask):
    def __init__(self, folder, resource, cache, context, callback):
        super().__init__(f'Indeks kafli {resource}', QgsTask.CanCancel)
        self.args = folder, resource, cache, context
        self.callback = callback
        self.result, self.errors = None, []

    def run(self):
        try:
            self.result, self.errors = scan_folder(*self.args, self.isCanceled)
            return self.result is not None
        except Exception as exc:
            self.errors = [str(exc)]
            return False

    def finished(self, success):
        self.callback(self.result, self.errors)


class CoverageManager(QObject):
    def __init__(self, iface=None):
        super().__init__()
        self.iface = iface
        self.entries, self.jobs, self.dirty = {}, {}, set()
        self.closed = False
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.changed)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(750)
        self.debounce.timeout.connect(self.flush)
        self.poll = QTimer(self)
        self.poll.setInterval(15000)
        self.poll.timeout.connect(self.refresh_all)
        self.poll.start()
        self.add_timer = QTimer(self)
        self.add_timer.setInterval(0)
        self.add_timer.timeout.connect(self._add_batch)
        self.additions = []
        self.add_extent = None
        project = QgsProject.instance()
        project.readProject.connect(self.restore)
        project.layersWillBeRemoved.connect(self.removing)
        self.restore()

    def restore(self, *args):
        if self.closed:
            return
        for layer in list(QgsProject.instance().mapLayers().values()):
            folder, resource = layer.customProperty(KEY, ''), layer.customProperty(RESOURCE_KEY, '')
            if folder and resource:
                source = layer.source().split('|')[0]
                if Path(source).exists():
                    folder = str(Path(source).parent)
                self._register(folder, resource, layer)
        self.refresh_all()

    def _register(self, folder, resource, layer):
        folder = str(Path(folder).resolve())
        key = folder, resource
        if key in self.entries:
            return
        fields = [name for name, _ in FIELDS]
        cache = {}
        for feat in layer.getFeatures():
            record = {name: feat[name] for name in fields}
            record['wkt'] = feat.geometry().asWkt(6)
            cache[canonical(record['sciezka'])] = record
        self.entries[key] = dict(layer=layer, cache=cache)
        if Path(folder).is_dir() and folder not in self.watcher.directories():
            self.watcher.addPath(folder)

    def ensure(self, folder, resource):
        folder = str(Path(folder).expanduser().resolve())
        key = folder, resource
        if key in self.entries:
            layer = self.entries[key]['layer']
            if QgsProject.instance().mapLayer(layer.id()):
                self.request(key)
                return layer
            self.entries.pop(key)
        Path(folder).mkdir(parents=True, exist_ok=True)
        path = Path(folder) / f'.nmt_nmpt_index_{resource}.gpkg'
        if not path.exists():
            memory = QgsVectorLayer('Polygon?crs=EPSG:2180', 'kafle', 'memory')
            memory.dataProvider().addAttributes([QgsField(name, kind) for name, kind in FIELDS])
            memory.updateFields()
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName, options.layerName = 'GPKG', 'kafle'
            result = QgsVectorFileWriter.writeAsVectorFormatV3(memory, str(path), QgsProject.instance().transformContext(), options)
            if result[0] != QgsVectorFileWriter.NoError:
                raise RuntimeError('Nie udało się utworzyć indeksu: ' + str(result))
        layer = QgsVectorLayer(str(path) + '|layername=kafle', f'Pobrane kafle {resource}', 'ogr')
        if not layer.isValid() or any(layer.fields().indexFromName(name) < 0 for name, _ in FIELDS):
            raise ValueError('Nieprawidłowy plik indeksu: ' + str(path))
        layer.setCustomProperty(KEY, folder)
        layer.setCustomProperty(RESOURCE_KEY, resource)
        layer.setReadOnly(True)
        symbol = QgsFillSymbol.createSimple({'style': 'no', 'outline_color': '0,150,85' if resource == 'NMT' else '220,125,15',
                                             'outline_width': '0.35'})
        layer.renderer().setSymbol(symbol)
        layer.setMapTipTemplate('<b>[% "plik" %]</b><br>[% "uklad_wys" %]<br>Piksel: [% "piksel_m" %] m<br>[% "rozmiar_MB" %] MB')
        QgsProject.instance().addMapLayer(layer)
        self._register(folder, resource, layer)
        self.request(key)
        return layer

    def changed(self, folder):
        self.dirty.update(key for key in self.entries if key[0] == folder)
        self.debounce.start()

    def flush(self):
        for key in list(self.dirty):
            if key not in self.jobs:
                self.dirty.discard(key)
                self.request(key)

    def refresh_all(self):
        for key in list(self.entries):
            self.request(key)

    def request(self, key):
        if self.closed or key not in self.entries:
            return
        if key in self.jobs:
            self.dirty.add(key)
            return
        entry = self.entries[key]
        context = QgsCoordinateTransformContext(QgsProject.instance().transformContext())
        task = ScanTask(*key, dict(entry['cache']), context, lambda records, errors: self._finished(key, records, errors))
        self.jobs[key] = task
        QgsApplication.taskManager().addTask(task)

    def _finished(self, key, records, errors):
        self.jobs.pop(key, None)
        if self.closed or key not in self.entries:
            return
        for error in errors[:20]:
            QgsMessageLog.logMessage(error, 'NMT / NMPT — indeks')
        if records is not None:
            try:
                self.apply_records(key, records)
            except Exception as exc:
                QgsMessageLog.logMessage(str(exc), 'NMT / NMPT — indeks')
        if key in self.dirty:
            self.dirty.discard(key)
            self.request(key)

    def apply_records(self, key, records):
        entry = self.entries[key]
        if entry['cache'] == records:
            return
        layer = entry['layer']
        if not QgsProject.instance().mapLayer(layer.id()):
            return
        old = {canonical(f['sciezka']): f.id() for f in layer.getFeatures()}
        layer.setReadOnly(False)
        try:
            if not layer.startEditing():
                raise RuntimeError('Nie można aktualizować indeksu kafli')
            for path, fid in old.items():
                if path not in records:
                    layer.deleteFeature(fid)
            for path, record in records.items():
                if entry['cache'].get(path) == record:
                    continue
                attributes = {layer.fields().indexFromName(name): record[name] for name, _ in FIELDS}
                geometry = QgsGeometry.fromWkt(record['wkt'])
                if path in old:
                    layer.changeGeometry(old[path], geometry)
                    layer.changeAttributeValues(old[path], attributes)
                else:
                    feat = QgsFeature(layer.fields())
                    for index, value in attributes.items():
                        feat.setAttribute(index, value)
                    feat.setGeometry(geometry)
                    layer.addFeature(feat)
            if not layer.commitChanges():
                raise RuntimeError('; '.join(layer.commitErrors()))
            entry['cache'] = records
        except Exception:
            layer.rollBack()
            raise
        finally:
            layer.setReadOnly(True)
        layer.updateExtents()
        layer.triggerRepaint()

    def removing(self, layer_ids):
        removed = [key for key, entry in self.entries.items() if entry['layer'].id() in layer_ids]
        for key in removed:
            self.entries.pop(key)
            self.dirty.discard(key)
            if key in self.jobs:
                self.jobs[key].cancel()
            if not any(other[0] == key[0] for other in self.entries) and key[0] in self.watcher.directories():
                self.watcher.removePath(key[0])

    def show_results(self, report):
        project = QgsProject.instance()
        if not self.additions:
            self.add_extent = None
        existing = {canonical(layer.source().split('|')[0]): layer for layer in project.mapLayers().values()
                    if isinstance(layer, QgsRasterLayer)}
        for record in report.get('tiles', []):
            paths = record.get('files') or ([record['file']] if record.get('file') and record['status'] in ('downloaded', 'reused', 'partial') else [])
            for path in paths:
                key = canonical(path)
                if key in existing:
                    node = project.layerTreeRoot().findLayer(existing[key].id())
                    if node:
                        node.setItemVisibilityChecked(True)
                    self._extend_view(existing[key])
                elif Path(path).is_file() and not any(item[0] == key for item in self.additions):
                    self.additions.append((key, record['resource'], path))
        self.add_timer.start()

    def _extend_view(self, layer):
        if not self.iface or not hasattr(self.iface, 'mapCanvas'):
            return
        try:
            canvas = self.iface.mapCanvas()
            transform = QgsCoordinateTransform(layer.crs(), canvas.mapSettings().destinationCrs(), QgsProject.instance())
            extent = transform.transformBoundingBox(layer.extent())
            if self.add_extent is None:
                self.add_extent = QgsRectangle(extent)
            else:
                self.add_extent.combineExtentWith(extent)
        except Exception as exc:
            QgsMessageLog.logMessage('Nie można ustawić widoku mapy: ' + str(exc), 'NMT / NMPT')

    def _add_batch(self):
        project = QgsProject.instance()
        for _ in range(min(8, len(self.additions))):
            _, resource, path = self.additions.pop(0)
            layer = QgsRasterLayer(path, Path(path).stem, 'gdal')
            if layer.isValid():
                root = project.layerTreeRoot()
                group = root.findGroup('Rastry ' + resource) or root.addGroup('Rastry ' + resource)
                project.addMapLayer(layer, False)
                group.addLayer(layer)
                self._extend_view(layer)
        if not self.additions:
            self.add_timer.stop()
            if self.add_extent is not None:
                self.add_extent.scale(1.05)
                self.iface.mapCanvas().setExtent(self.add_extent)
                self.iface.mapCanvas().refresh()

    def stop(self):
        if self.closed:
            return
        self.closed = True
        for timer in (self.poll, self.debounce, self.add_timer):
            timer.stop()
        for task in self.jobs.values():
            task.cancel()
        project = QgsProject.instance()
        project.readProject.disconnect(self.restore)
        project.layersWillBeRemoved.disconnect(self.removing)
        if self.watcher.directories():
            self.watcher.removePaths(self.watcher.directories())
        self.entries.clear()
