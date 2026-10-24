"""Finite turbine sight lines with windowed DSM/DTM reads; no GUI objects in workers."""
from collections import Counter, OrderedDict
from datetime import datetime, timezone
import csv
import json
import math
from pathlib import Path
import threading
import time
import uuid

import numpy as np
from osgeo import gdal, ogr, osr
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsFeatureRequest,
    QgsGeometry, QgsPointXY, QgsRectangle, QgsSpatialIndex, QgsWkbTypes,
)

from .catalog import HEIGHTS
from .core import VERSION, Canceled, atomic_json, check_cancel
from .engine import Engine

LABELS = {
    'blocked_terrain': 'Przesłonięta przez teren',
    'blocked_detail': 'Przesłonięta w NMPT',
    'visible_modeled': 'Widoczna w sprawdzonym modelu NMPT',
    'potential_visible_partial_detail': 'Potencjalnie widoczna — NMPT tylko lokalnie',
    'visible_terrain_only': 'Widoczna w modelu samego terenu',
    'unknown_required_data': 'Brak wymaganych danych',
    'uncertain_geometry': 'Niejednoznaczna geometria / wynik graniczny',
    'outside_analysis': 'Poza promieniem analizy',
}
MAX_PAIRS = 20000
MAX_SEGMENTS = 1000000


def now():
    return datetime.now(timezone.utc).isoformat()


def read_points(source, crs, context, kind, options, event):
    """Read task-owned feature snapshots; polygon receivers use one point on surface."""
    transform = QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem('EPSG:2180'), context)
    request = QgsFeatureRequest()
    ids = options.get(kind + '_ids')
    if ids is not None:
        request.setFilterFids(ids)
    points, issues = [], []
    for feature in source.getFeatures(request):
        check_cancel(event)
        try:
            geometry = QgsGeometry(feature.geometry())
            if geometry.isEmpty():
                raise ValueError('Pusta geometria')
            geometry.transform(transform)
            polygon = QgsWkbTypes.geometryType(geometry.wkbType()) == QgsWkbTypes.PolygonGeometry
            if polygon and kind == 'receivers':
                if not geometry.isGeosValid():
                    geometry = geometry.makeValid()
                geometry = geometry.pointOnSurface()
            if QgsWkbTypes.geometryType(geometry.wkbType()) != QgsWkbTypes.PointGeometry or geometry.isMultipart():
                raise ValueError('Wymagany pojedynczy punkt (dla odbiorców także poligon)')
            point = geometry.asPoint()
            if not all(math.isfinite(v) for v in (point.x(), point.y())):
                raise ValueError('Nieprawidłowe współrzędne')
            item = dict(id=str(feature.id()), x=point.x(), y=point.y(), representative=polygon)
            if kind == 'turbines':
                if options.get('turbine_id_field'):
                    item['id'] = str(feature[options['turbine_id_field']])
                for name, default, minimum in [('hub', 120, 0.01), ('diameter', 160, 0)]:
                    field = options.get(name + '_field', '')
                    value = float(feature[field] if field else options.get(name, default))
                    if not math.isfinite(value) or not minimum <= value <= 2000:
                        raise ValueError(f'Nieprawidłowa wysokość / średnica: {name}')
                    item[name] = value
            points.append(item)
        except Exception as exc:
            issues.append(dict(kind=kind, id=str(feature.id()), reason=str(exc)))
        if len(points) > 50000:
            raise ValueError('Zbyt wiele punktów; wybierz podzbiór obiektów')
    if not points:
        raise ValueError(f'Brak poprawnych obiektów: {kind}. {issues[:3]}')
    return points, issues


def detail_intervals(distance, options):
    if not options.get('use_nmpt', True):
        return []
    if options.get('detail_mode', 'local') == 'full':
        return [(0.0, 1.0)]
    part = min(1.0, options.get('detail_radius', 1000) / max(distance, 1e-9))
    centers = options.get('detail_centers', 'both')
    intervals = []
    if centers in ('receivers', 'both'):
        intervals.append((0.0, part))
    if centers in ('turbines', 'both'):
        intervals.append((1.0 - part, 1.0))
    if len(intervals) == 2 and intervals[0][1] >= intervals[1][0]:
        return [(0.0, 1.0)]
    return intervals


class GeometrySource:
    """Minimal feature source used by the existing downloader, entirely in the task."""
    def __init__(self, geometries):
        self.geometries = geometries

    def getFeatures(self, request=None):
        for number, geometry in enumerate(self.geometries):
            feature = QgsFeature(number)
            feature.setGeometry(geometry)
            yield feature


class RasterStore:
    """Spatially indexed headers, bounded dataset handles and 256x256 pixel block LRU."""
    def __init__(self, folder, resource, height, event):
        self.resource, self.height, self.event = resource, height, event
        self.records, self.errors = [], []
        self.index = QgsSpatialIndex()
        self.datasets, self.blocks = OrderedDict(), OrderedDict()
        if not Path(folder).is_dir():
            return
        expected = osr.SpatialReference()
        expected.ImportFromEPSG(2180)
        expected.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        for path in sorted(Path(folder).iterdir()):
            check_cancel(event)
            if path.name.startswith('.') or path.suffix.lower() not in ('.tif', '.tiff', '.asc') or not path.is_file():
                continue
            ds = None
            try:
                ds = gdal.Open(str(path), gdal.GA_ReadOnly)
                if ds is None or ds.RasterCount != 1:
                    raise ValueError('Nieczytelny raster jednokanałowy')
                coverage = ds.GetMetadataItem('COVERAGE') or ''
                kind = ds.GetMetadataItem('RESOURCE') or ('NMPT' if coverage.startswith('DSM_') else 'NMT' if coverage.startswith('DTM_') else '')
                datum = ds.GetMetadataItem('HEIGHT_SYSTEM') or next((h for h in HEIGHTS if h in coverage or h in path.name), '')
                if kind != resource or datum != height:
                    raise ValueError(f'Zasób / układ wysokościowy: {kind or "nieznany"} / {datum or "nieznany"}; wymagane {resource} / {height}')
                srs = ds.GetSpatialRef()
                if srs is None:
                    raise ValueError('Brak CRS')
                srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
                if not srs.IsSame(expected):
                    raise ValueError('Wymagany CRS EPSG:2180; brak automatycznego przeliczania rastrów')
                gt = ds.GetGeoTransform()
                if gt[1] <= 0 or gt[5] >= 0 or abs(gt[2]) > 1e-10 or abs(gt[4]) > 1e-10:
                    raise ValueError('Wymagana siatka bez obrotu, północ na górze')
                band = ds.GetRasterBand(1)
                if band.DataType == gdal.GDT_Byte or band.GetUnitType().lower() not in ('', 'm', 'metre', 'meter', 'metres', 'meters'):
                    raise ValueError('Wymagane numeryczne wysokości w metrach; raster Byte nie jest dopuszczony')
                source_gt = gt
                if ds.GetMetadataItem('REQUEST_SIGNATURE') and ds.GetMetadataItem('NATIVE_RESOLUTION'):
                    native = float(ds.GetMetadataItem('NATIVE_RESOLUTION'))
                    if native > 0:
                        snapped = (round(gt[0] / native) * native, native, 0,
                                   round(gt[3] / native) * native, 0, -native)
                        if all(abs(a - b) <= 0.001 for a, b in zip(gt, snapped)):
                            gt = snapped  # Same validation tolerance as the downloader; old plugin files only.
                bounds = (gt[0], gt[3] + gt[5] * ds.RasterYSize, gt[0] + gt[1] * ds.RasterXSize, gt[3])
                if not all(math.isfinite(v) for v in (*gt, *bounds)):
                    raise ValueError('Nieprawidłowa georeferencja')
                info = path.stat()
                record = dict(path=str(path.resolve()), gt=gt, source_gt=source_gt, bounds=bounds, width=ds.RasterXSize,
                              height=ds.RasterYSize, resolution=max(gt[1], -gt[5]),
                              mtime_ns=info.st_mtime_ns, bytes=info.st_size,
                              scale=band.GetScale() if band.GetScale() is not None else 1,
                              offset=band.GetOffset() if band.GetOffset() is not None else 0)
                self.records.append(record)
            except Exception as exc:
                self.errors.append(dict(file=str(path), reason=str(exc)))
            finally:
                ds = None
        self.records.sort(key=lambda r: (r['resolution'], -r['mtime_ns'], r['path']))
        for number, record in enumerate(self.records):
            feature = QgsFeature(number)
            feature.setGeometry(QgsGeometry.fromRect(QgsRectangle(*record['bounds'])))
            self.index.addFeature(feature)

    def close(self):
        self.blocks.clear()
        self.datasets.clear()

    def candidates(self, start, end):
        # Slight expansion also includes horizontal / vertical lines with a zero-size envelope.
        box = QgsRectangle(min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1]))
        box.grow(1e-7)
        return sorted(self.index.intersects(box))

    def _block(self, number, bx, by):
        key = number, int(bx), int(by)
        if key in self.blocks:
            self.blocks.move_to_end(key)
            return self.blocks[key]
        check_cancel(self.event)
        record = self.records[number]
        if number not in self.datasets:
            ds = gdal.Open(record['path'], gdal.GA_ReadOnly)
            if ds is None:
                raise ValueError('Nie można ponownie otworzyć rastra: ' + record['path'])
            self.datasets[number] = ds
            if len(self.datasets) > 8:
                self.datasets.popitem(last=False)
        self.datasets.move_to_end(number)
        ds = self.datasets[number]
        xoff, yoff = int(bx) * 256, int(by) * 256
        width, height = min(256, record['width'] - xoff), min(256, record['height'] - yoff)
        band = ds.GetRasterBand(1)
        raw = band.ReadAsArray(xoff, yoff, width, height)
        mask = band.GetMaskBand().ReadAsArray(xoff, yoff, width, height)
        if raw is None or mask is None:
            raise ValueError('Błąd odczytu bloku: ' + record['path'])
        values = raw.astype(np.float64)
        valid = np.isfinite(values) & (mask != 0)
        nodata = band.GetNoDataValue()
        if nodata is not None and math.isfinite(nodata):
            valid &= raw != nodata
        values = values * record['scale'] + record['offset']
        values[~valid | ~np.isfinite(values)] = np.nan
        self.blocks[key] = values
        if len(self.blocks) > 32:
            self.blocks.popitem(last=False)  # <=16 MiB Float64 per store, plus small GDAL caches.
        return values

    def sample(self, x, y, candidates=None):
        x, y = np.asarray(x), np.asarray(y)
        values = np.full(x.shape, np.nan)
        sources = np.full(x.shape, -1, dtype=np.int32)
        if candidates is None:
            candidates = self.candidates((float(x.min()), float(y.min())), (float(x.max()), float(y.max())))
        for number in candidates:
            check_cancel(self.event)
            record = self.records[number]
            xmin, ymin, xmax, ymax = record['bounds']
            mask = ~np.isfinite(values) & (x >= xmin) & (x < xmax) & (y > ymin) & (y <= ymax)
            positions = np.flatnonzero(mask)
            if not len(positions):
                continue
            gt = record['gt']
            cols = np.floor((x[positions] - gt[0]) / gt[1]).astype(np.int64)
            rows = np.floor((y[positions] - gt[3]) / gt[5]).astype(np.int64)
            cols = np.clip(cols, 0, record['width'] - 1)
            rows = np.clip(rows, 0, record['height'] - 1)
            block_ids = (rows // 256) * math.ceil(record['width'] / 256) + cols // 256
            for block_id in np.unique(block_ids):
                indices = np.flatnonzero(block_ids == block_id)
                try:
                    block = self._block(number, cols[indices[0]] // 256, rows[indices[0]] // 256)
                    sampled = block[rows[indices] % 256, cols[indices] % 256]
                    good = np.isfinite(sampled)
                    locations = positions[indices[good]]
                    values[locations], sources[locations] = sampled[good], number
                except Canceled:
                    raise
                except Exception as exc:
                    error = dict(file=record['path'], reason=str(exc))
                    if error not in self.errors:
                        self.errors.append(error)
        return values, sources


def clip_interval(start, delta, bounds, interval):
    low, high = interval
    for coordinate, change, minimum, maximum in zip(start, delta, bounds[:2], bounds[2:]):
        if abs(change) < 1e-12:
            if coordinate < minimum or coordinate > maximum:
                return None
        else:
            a, b = sorted(((minimum - coordinate) / change, (maximum - coordinate) / change))
            low, high = max(low, a), min(high, b)
    return (low, high) if high - low > 1e-12 else None


def ray_breaks(start, end, terrain, detail, intervals, event):
    """Split at every crossed raster grid boundary, never use a coarse fixed ray step."""
    start, end = np.array(start), np.array(end)
    delta = end - start
    pieces = [np.array([0.0, 1.0] + [v for interval in intervals for v in interval])]
    candidate_sets = []
    count = 2
    for store, ranges in [(terrain, [(0.0, 1.0)]), (detail, intervals)]:
        candidates = store.candidates(start, end)
        candidate_sets.append(candidates)
        for number in candidates:
            check_cancel(event)
            record = store.records[number]
            for interval in ranges:
                clipped = clip_interval(start, delta, record['bounds'], interval)
                if clipped is None:
                    continue
                low, high = clipped
                pieces.append(np.array([low, high]))
                for axis, origin, spacing in [(0, record['gt'][0], record['gt'][1]), (1, record['gt'][3], -record['gt'][5])]:
                    if abs(delta[axis]) < 1e-12:
                        continue
                    a, b = sorted(((start[axis] + delta[axis] * low - origin) / spacing,
                                   (start[axis] + delta[axis] * high - origin) / spacing))
                    first, last = math.ceil(a), math.floor(b)
                    count += max(0, last - first + 1)
                    if count > MAX_SEGMENTS:
                        raise ValueError('Linia przecina zbyt wiele komórek; ogranicz zasięg / liczbę nakładających się rastrów')
                    coordinates = origin + np.arange(first, last + 1) * spacing
                    pieces.append((coordinates - start[axis]) / delta[axis])
    breaks = np.sort(np.clip(np.concatenate(pieces), 0, 1))
    breaks = breaks[np.r_[True, np.diff(breaks) > 1e-11]]
    return breaks, candidate_sets


def sample_ray_cells(store, x, y, candidates, delta):
    values, sources = store.sample(x, y, candidates)
    covered = np.isfinite(values)
    # A ray along a grid edge touches both neighbouring cells along its whole length.
    # Inspect both sides; an unknown neighbour cannot be treated as empty space.
    for axis, origin_index, spacing_index in [(0, 0, 1), (1, 3, 5)]:
        coordinates = x if axis == 0 else y
        if abs(delta[axis]) > 1e-10 or not len(coordinates):
            continue
        aligned = any(abs((coordinates[0] - store.records[i]['gt'][origin_index]) /
                          store.records[i]['gt'][spacing_index] - round(
                              (coordinates[0] - store.records[i]['gt'][origin_index]) /
                              store.records[i]['gt'][spacing_index])) < 1e-8 for i in candidates)
        if not aligned:
            continue
        for shift in (-1e-7, 1e-7):
            extra, extra_sources = store.sample(x + shift if axis == 0 else x,
                                                y + shift if axis == 1 else y, candidates)
            higher = np.isfinite(extra) & (~np.isfinite(values) | (extra > values))
            values[higher], sources[higher] = extra[higher], extra_sources[higher]
            covered &= np.isfinite(extra)
    return values, sources, covered


def analyze_pair(receiver, turbine, terrain, detail, options, event):
    start, end = (receiver['x'], receiver['y']), (turbine['x'], turbine['y'])
    distance = math.dist(start, end)
    result = dict(receiver_id=receiver['id'], turbine_id=turbine['id'], distance_m=distance,
                  start=list(start), end=list(end), status='unknown_required_data', reason='',
                  detail_required_percent=0, detail_valid_percent=0, terrain_valid_percent=0,
                  clearance_m=None, blocker_distance_m=None, blocker_xy=None, samples=0)
    if distance > options['radius']:
        result.update(status='outside_analysis', reason='Odległość przekracza wybrany promień')
        return result
    if distance < 0.01:
        result.update(status='uncertain_geometry', reason='Odbiorca i turbina w tym samym miejscu')
        return result
    check_cancel(event)
    endpoints, _ = terrain.sample(np.array([start[0], end[0]]), np.array([start[1], end[1]]))
    if not np.isfinite(endpoints).all():
        result['reason'] = 'Brak NMT gruntu w punkcie obserwacji lub turbiny, także przy analizie NMPT'
        return result
    eye = endpoints[0] + options['eye']
    target = endpoints[1] + turbine['hub'] + (turbine['diameter'] / 2 if options.get('target', 'tip') == 'tip' else 0)
    result.update(eye_z_m=float(eye), target_z_m=float(target))
    intervals = detail_intervals(distance, options)
    ds_endpoints, _ = detail.sample(np.array([start[0], end[0]]), np.array([start[1], end[1]])) if intervals else (np.array([np.nan, np.nan]), None)
    # An eye inside a DSM roof/canopy cannot represent an outdoor view from this point.
    uncertain_endpoint = any(a <= 0 <= b for a, b in intervals) and np.isfinite(ds_endpoints[0]) and ds_endpoints[0] >= eye - options.get('tolerance', 0.25)
    uncertain_endpoint |= any(a <= 1 <= b for a, b in intervals) and np.isfinite(ds_endpoints[1]) and ds_endpoints[1] >= target - options.get('tolerance', 0.25)
    breaks, candidates = ray_breaks(start, end, terrain, detail, intervals, event)
    low, high = breaks[:-1], breaks[1:]
    middle = (low + high) / 2
    x = start[0] + (end[0] - start[0]) * middle
    y = start[1] + (end[1] - start[1]) * middle
    delta = (end[0] - start[0], end[1] - start[1])
    dtm, dtm_sources, valid_dtm = sample_ray_cells(terrain, x, y, candidates[0], delta)
    required = np.zeros(middle.shape, dtype=bool)
    for a, b in intervals:
        required |= (middle >= a) & (middle <= b)
    dsm = np.full(middle.shape, np.nan)
    dsm_sources = np.full(middle.shape, -1, dtype=np.int32)
    valid_dsm = np.zeros(middle.shape, dtype=bool)
    if required.any():
        dsm[required], dsm_sources[required], valid_dsm[required] = sample_ray_cells(
            detail, x[required], y[required], candidates[1], delta)
    widths = high - low
    result.update(samples=len(middle), detail_required_percent=float(100 * widths[required].sum()),
                  detail_valid_percent=float(100 * widths[required & valid_dsm].sum()),
                  terrain_valid_percent=float(100 * widths[valid_dtm].sum()))
    obstacles = np.fmax(dtm, dsm)
    # Minimum clearance on each constant-height cell interval, including Earth bulge.
    radius = 6371000 / (1 - options.get('refraction', 1 / 7)) if options.get('curvature', True) else math.inf
    if math.isfinite(radius):
        vertex = 0.5 - (target - eye) * radius / distance ** 2
        test_t = np.clip(np.full(low.shape, vertex), low, high)
    else:
        test_t = low if target >= eye else high
    line = eye + (target - eye) * test_t
    bulge = distance ** 2 * test_t * (1 - test_t) / (2 * radius)
    clearance = line - bulge - obstacles
    valid = np.isfinite(clearance)
    tolerance = options.get('tolerance', 0.25)
    blocked = np.flatnonzero(valid & (clearance < -tolerance))
    result['clearance_m'] = float(clearance[valid].min()) if valid.any() else None
    missing = bool((~valid_dtm | (required & ~valid_dsm)).any())
    model_mismatch = bool((required & valid_dsm & valid_dtm & (dsm < dtm - 3)).any())
    result['model_mismatch'] = model_mismatch
    result['used_files'] = {
        'NMT': [terrain.records[i]['path'] for i in np.unique(dtm_sources[dtm_sources >= 0])],
        'NMPT': [detail.records[i]['path'] for i in np.unique(dsm_sources[dsm_sources >= 0])],
    }
    if uncertain_endpoint:
        result.update(status='uncertain_geometry', reason='Punkt oka lub cel wewnątrz powierzchni NMPT; wybierz punkt na zewnątrz budynku / korony drzewa')
    elif len(blocked):
        index = int(blocked[0])
        detail_block = np.isfinite(dsm[index]) and (not np.isfinite(dtm[index]) or dsm[index] > dtm[index] + 1e-6)
        result.update(status='blocked_detail' if detail_block else 'blocked_terrain',
                      reason='Przeszkoda przekracza linię widzenia o więcej niż tolerancja',
                      blocker_distance_m=float(distance * middle[index]),
                      blocker_xy=[float(x[index]), float(y[index])], missing_elsewhere=missing)
    elif missing:
        result['reason'] = 'Brak NMT na trasie lub NMPT we fragmencie, w którym było wymagane; nie przyjęto wysokości 0'
    elif model_mismatch or (valid & (clearance <= tolerance)).any():
        result.update(status='uncertain_geometry', reason='Różnica modeli NMT/NMPT >3 m lub linia blisko przeszkody (tolerancja wysokości)')
    elif not intervals:
        result.update(status='visible_terrain_only', reason='Przeanalizowano tylko NMT; drzewa i zabudowa nie są sprawdzone')
    elif result['detail_required_percent'] < 100 - 1e-7:
        result.update(status='potential_visible_partial_detail', reason='Brak przeszkód w sprawdzonym modelu; NMPT poza wybranymi odcinkami nie było wymagane')
    else:
        result.update(status='visible_modeled', reason='Brak przeszkód w pełnym modelu NMT/NMPT wzdłuż linii')
    return result


def write_results(folder, receivers, turbines, results):
    """OGR writes GeoPackage without creating project-owned layers in a task."""
    path = folder / 'widocznosc.gpkg'
    dataset = ogr.GetDriverByName('GPKG').CreateDataSource(str(path))
    if dataset is None:
        raise ValueError('Nie można utworzyć GeoPackage')
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(2180)
    try:
        for name, points in [('obserwatorzy', receivers), ('turbiny', turbines)]:
            layer = dataset.CreateLayer(name, srs, ogr.wkbPoint)
            for field, kind in [('source_id', ogr.OFTString), ('reprezent', ogr.OFTInteger), ('piasta_m', ogr.OFTReal), ('srednica_m', ogr.OFTReal)]:
                layer.CreateField(ogr.FieldDefn(field, kind))
            layer.StartTransaction()
            for point in points:
                feature = ogr.Feature(layer.GetLayerDefn())
                feature.SetField('source_id', point['id'])
                feature.SetField('reprezent', int(point['representative']))
                if 'hub' in point:
                    feature.SetField('piasta_m', point['hub'])
                    feature.SetField('srednica_m', point['diameter'])
                geometry = ogr.Geometry(ogr.wkbPoint)
                geometry.AddPoint_2D(point['x'], point['y'])
                feature.SetGeometry(geometry)
                if layer.CreateFeature(feature) != 0:
                    raise ValueError('Błąd zapisu punktów GeoPackage')
            layer.CommitTransaction()
        fields = [('receiver_id', ogr.OFTString), ('turbine_id', ogr.OFTString), ('status', ogr.OFTString),
                  ('opis', ogr.OFTString), ('reason', ogr.OFTString), ('distance_m', ogr.OFTReal),
                  ('detail_required_percent', ogr.OFTReal), ('detail_valid_percent', ogr.OFTReal),
                  ('terrain_valid_percent', ogr.OFTReal), ('clearance_m', ogr.OFTReal),
                  ('blocker_distance_m', ogr.OFTReal), ('eye_z_m', ogr.OFTReal), ('target_z_m', ogr.OFTReal)]
        layer = dataset.CreateLayer('linie_widzenia', srs, ogr.wkbLineString)
        for name, kind in fields:
            layer.CreateField(ogr.FieldDefn(name, kind))
        layer.StartTransaction()
        with (folder / 'wyniki.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            names = [name for name, _ in fields]
            writer = csv.DictWriter(stream, names, delimiter=';')
            writer.writeheader()
            for result in results:
                row = {name: result.get(name) for name in names}
                row['opis'] = LABELS[result['status']]
                writer.writerow(row)
                feature = ogr.Feature(layer.GetLayerDefn())
                for name, value in row.items():
                    if value is not None:
                        feature.SetField(name, value)
                geometry = ogr.Geometry(ogr.wkbLineString)
                for point in [result['start'], result['end']]:
                    geometry.AddPoint_2D(*point)
                feature.SetGeometry(geometry)
                if layer.CreateFeature(feature) != 0:
                    raise ValueError('Błąd zapisu linii GeoPackage')
        layer.CommitTransaction()
    finally:
        dataset = None
    return str(path)


class VisibilityEngine:
    def __init__(self, turbines, turbine_crs, receivers, receiver_crs, context, options,
                 notify=lambda _: None, log=lambda _: None):
        self.sources = (turbines, turbine_crs, receivers, receiver_crs)
        self.context, self.options, self.notify, self.log = context, options, notify, log
        self.cancel_event = threading.Event()
        self.started = time.monotonic()
        self.analysis_started = None
        self.report_dir = None
        self.report = dict(version=VERSION, started_at=now(), state='running', options=options, crs='EPSG:2180',
                           results=[], input_issues=[], downloads=[], raster_errors=[], rasters={})

    def event(self, message):
        self.log(message)
        if self.report_dir:
            with (self.report_dir / 'events.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(dict(time=now(), message=message), ensure_ascii=False) + '\n')

    def progress(self, stage, done=0, total=0):
        elapsed = time.monotonic() - self.started
        analysis_elapsed = time.monotonic() - self.analysis_started if self.analysis_started else 0
        self.notify(dict(kind='analysis', stage=stage, done=done, total=total, elapsed=elapsed,
                         eta=(total - done) * analysis_elapsed / done if done else None,
                         counts=dict(Counter(r['status'] for r in self.report['results']))))

    def checkpoint(self):
        self.report.update(elapsed_seconds=time.monotonic() - self.started,
                           counts=dict(Counter(r['status'] for r in self.report['results'])))
        atomic_json(self.report_dir / 'report.json', self.report)

    def download(self, resource, pairs):
        geometries = []
        margin = 5 if resource == 'NMT' else 2  # Include centres of crossed cells, also for a 5 m DTM.
        for receiver, turbine in pairs:
            check_cancel(self.cancel_event)
            start, end = np.array([receiver['x'], receiver['y']]), np.array([turbine['x'], turbine['y']])
            distance = float(np.linalg.norm(end - start))
            ranges = [(0, 1)] if resource == 'NMT' else detail_intervals(distance, self.options)
            for low, high in ranges:
                a, b = start + (end - start) * low, start + (end - start) * high
                if np.linalg.norm(b - a) < 0.01:
                    geometry = QgsGeometry.fromPointXY(QgsPointXY(*a))
                else:
                    geometry = QgsGeometry.fromPolylineXY([QgsPointXY(*a), QgsPointXY(*b)])
                geometries.append(geometry.buffer(margin, 4))
        if not geometries:
            return
        options = dict(resources=[resource], radius=0, folders={resource: self.options['folders'][resource]},
                       report_folder=str(self.report_dir / ('pobieranie_' + resource)),
                       pixels=self.options.get('pixels', 1024), workers=self.options.get('workers', 2),
                       reuse=True, feature_ids=None,
                       resource_settings={resource: dict(resolution=0, height=self.options['height'],
                                                         strict_resolution=False, alternate_height=False)})
        self.event(f'{resource}: pobieranie / kontrola kafli tylko dla korytarzy linii, z ponownym użyciem zgodnych plików')

        def notify(stats):
            previous = sum(d['bytes_received'] for d in self.report['downloads'])
            self.notify(dict(stats, kind='download', resource=resource, all_bytes=previous + stats['bytes']))

        engine = Engine(GeometrySource(geometries), QgsCoordinateReferenceSystem('EPSG:2180'),
                        self.context, options, notify, self.event)
        engine.cancel_event = self.cancel_event
        report = engine.run()
        self.report['downloads'].append(dict(resource=resource, state=report['state'], report_dir=report.get('report_dir'),
                                             bytes_received=report.get('network_bytes', engine.bytes_received),
                                             corridor_buffer_m=margin,
                                             fatal_error=report.get('fatal_error')))
        if report['state'] == 'failed':
            self.event(f'{resource}: problem pobierania, analiza użyje dostępnych plików i oznaczy braki')
        check_cancel(self.cancel_event)

    def run(self):
        terrain, detail = None, None
        receivers, turbines = [], []
        try:
            self.report_dir = Path(self.options['report_folder']) / ('widocznosc_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
            self.report_dir.mkdir(parents=True)
            self.report['report_dir'] = str(self.report_dir)
            self.checkpoint()
            self.progress('Przygotowanie turbin i odbiorców')
            source, crs, receiver_source, receiver_crs = self.sources
            turbines, issues = read_points(source, crs, self.context, 'turbines', self.options, self.cancel_event)
            receivers, receiver_issues = read_points(receiver_source, receiver_crs, self.context, 'receivers', self.options, self.cancel_event)
            self.report.update(turbines=turbines, receivers=receivers, input_issues=issues + receiver_issues)
            if len(turbines) * len(receivers) > MAX_PAIRS:
                raise ValueError(f'Maksymalnie {MAX_PAIRS} par na zadanie; ogranicz obiekty przez zaznaczenie')
            pairs = [(receiver, turbine) for receiver in receivers for turbine in turbines]
            inside = [(r, t) for r, t in pairs if math.hypot(r['x'] - t['x'], r['y'] - t['y']) <= self.options['radius']]
            self.report.update(pairs_total=len(pairs), pairs_within_radius=len(inside))
            self.event(f'Pary: {len(pairs)}, w promieniu: {len(inside)}. NMPT: {self.options.get("use_nmpt", True)}, tryb {self.options.get("detail_mode", "local")}')
            if self.options.get('auto_download', True):
                self.download('NMT', inside)
                if self.options.get('use_nmpt', True):
                    self.download('NMPT', inside)
            self.progress('Indeksowanie rastrów z folderów')
            terrain = RasterStore(self.options['folders']['NMT'], 'NMT', self.options['height'], self.cancel_event)
            detail = RasterStore(self.options['folders']['NMPT'], 'NMPT', self.options['height'], self.cancel_event)
            for resource, store in [('NMT', terrain), ('NMPT', detail)]:
                self.report['rasters'][resource] = store.records
            last_checkpoint = time.monotonic()
            self.analysis_started = time.monotonic()
            for number, (receiver, turbine) in enumerate(pairs):
                check_cancel(self.cancel_event)
                self.progress(f'Linia {number + 1}/{len(pairs)}: odbiorca {receiver["id"]} → turbina {turbine["id"]}', number, len(pairs))
                try:
                    result = analyze_pair(receiver, turbine, terrain, detail, self.options, self.cancel_event)
                except Canceled:
                    raise
                except Exception as exc:
                    result = dict(receiver_id=receiver['id'], turbine_id=turbine['id'],
                                  start=[receiver['x'], receiver['y']], end=[turbine['x'], turbine['y']],
                                  distance_m=math.hypot(receiver['x'] - turbine['x'], receiver['y'] - turbine['y']),
                                  status='unknown_required_data', reason='Błąd tej linii: ' + str(exc))
                    self.event(result['reason'])
                self.report['results'].append(result)
                if time.monotonic() - last_checkpoint >= 5:
                    self.checkpoint()
                    last_checkpoint = time.monotonic()
            self.report['state'] = 'completed_with_gaps' if self.report['input_issues'] or any(
                r['status'] in ('unknown_required_data', 'uncertain_geometry') for r in self.report['results']) else 'completed'
        except Canceled:
            self.report['state'] = 'canceled'
        except Exception as exc:
            self.report.update(state='failed', fatal_error=str(exc))
            self.event('Błąd analizy: ' + str(exc))
        finally:
            for store in (terrain, detail):
                if store is not None:
                    self.report['raster_errors'].extend(store.errors)
                    store.close()
            if self.report_dir:
                try:
                    if receivers and turbines:
                        self.report['gpkg'] = write_results(self.report_dir, receivers, turbines, self.report['results'])
                    self.checkpoint()
                    self.write_markdown()
                except Exception as exc:
                    self.report.update(state='failed', fatal_error=f'Błąd zapisu wyników: {exc}')
                    self.checkpoint()
            self.progress('Zakończono: ' + self.report['state'], len(self.report['results']), self.report.get('pairs_total', 0))
        return self.report

    def write_markdown(self):
        lines = ['# Analiza widoczności turbin — NMPT', '', f'Wersja: {VERSION}; stan: **{self.report["state"]}**',
                 f'Czas: {self.report["elapsed_seconds"]:.1f} s; układ poziomy: EPSG:2180; wysokości: {self.options["height"]}.',
                 '', '## Konfiguracja', '',
                 f'Promień analizy: {self.options["radius"]:g} m; oko nad NMT: {self.options["eye"]:g} m.',
                 f'NMPT włączone: {self.options.get("use_nmpt", True)}; zakres: {self.options.get("detail_mode", "local")}; '
                 f'lokalny promień: {self.options.get("detail_radius", 1000):g} m; centra: {self.options.get("detail_centers", "both")}.',
                 f'Cel: {self.options.get("target", "tip")}; krzywizna: {self.options.get("curvature", True)}; '
                 f'k: {self.options.get("refraction", 1 / 7):.6f}; tolerancja wysokości: {self.options.get("tolerance", 0.25):g} m.',
                 f'Pobieranie automatyczne: {self.options.get("auto_download", True)}; transfer łączny: '
                 f'{sum(d["bytes_received"] for d in self.report["downloads"]) / 1e6:.3f} MB.',
                 '', '## Wyniki', '']
        for status, count in self.report['counts'].items():
            lines.append(f'- {LABELS[status]}: {count}')
        if self.report.get('fatal_error'):
            lines.extend(['', self.report['fatal_error']])
        lines.extend(['', '## Jak interpretować', '',
                      'Obliczono pojedyncze linie: oko nad gruntem NMT → piasta / najwyższy punkt zasięgu łopaty. ',
                      'Widoczność wybranego punktu nie oznacza widoczności całego wirnika ani udziału widocznej powierzchni.',
                      'NMPT jest nieprzezroczystą powierzchnią 2,5D (teren, korony drzew, dachy); nie odwzorowuje prześwitów i sezonowości.',
                      'W trybie lokalnym NMPT poza wskazanymi odcinkami nie jest sprawdzane; wynik potencjalny nie potwierdza widoczności.',
                      'Brak danych na wymaganej części trasy daje stan nieznany. Znana przeszkoda może przesłaniać linię mimo braków dalej.',
                      'Oko/cel wewnątrz NMPT daje niejednoznaczną geometrię; dla budynku wskaż punkt obserwacji na zewnątrz.',
                      'Dla poligonu użyto JEDNEGO punktu wewnętrznego, nie wszystkich miejsc działki / elewacji.',
                      'Procenty dotyczą długości modelowanej linii, nie prawdopodobieństwa ani pewności wyniku.',
                      'Krzywizna Ziemi i refrakcja są zapisane w options; tolerancja jest progiem obliczeniowym, nie błędem pomiaru.',
                      'Brak automatycznych transformacji wysokości; obce/niezgodne rastry są pomijane z powodem w report.json.',
                      'Nie wykonano ray tracingu siatek 3D ani pełnej rastrowej mapy widoczności dla każdego punktu obszaru.', '',
                      '## Pliki', '', '`widocznosc.gpkg`: obserwatorzy, turbiny, linie_widzenia; `wyniki.csv`: tabela.',
                      '`report.json`: konfiguracja, punkty, wyniki, użyte pliki i problemy. `events.jsonl`: przebieg.',
                      'Podfoldery pobieranie_NMT / pobieranie_NMPT: szczegółowe raporty transferów, gdy były włączone.', '',
                      '## Dane wymagające uwagi', ''])
        for issue in self.report['input_issues']:
            lines.append(f'- {issue}')
        for error in self.report['raster_errors']:
            lines.append(f'- {error["file"]}: {error["reason"]}')
        (self.report_dir / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
