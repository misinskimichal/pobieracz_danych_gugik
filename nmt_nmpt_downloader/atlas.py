"""Circular, cumulative turbine viewsheds. Disk-backed products, explicit data uncertainty."""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import shutil
import threading
import time
import uuid

import numpy as np
from osgeo import gdal, ogr, osr
from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry, QgsPointXY

from .core import VERSION, Canceled, atomic_json, check_cancel
from .engine import Engine
from .visibility import GeometrySource, RasterStore, now, read_points

NOCOUNT = 65535
NODATA = -9999
BIAS = 2000000.0  # Avoid GDAL's zero clamp on absolute minimum target heights below sea level.
MAX_LOCAL_CELLS = 40000000
MAX_TOTAL_CELLS = 400000000
CREATE = ['TILED=YES', 'COMPRESS=DEFLATE', 'BIGTIFF=IF_SAFER', 'SPARSE_OK=YES']


@dataclass
class Grid:
    xmin: float
    ymax: float
    step: float
    width: int
    height: int

    @property
    def bounds(self):
        return (self.xmin, self.ymax - self.height * self.step,
                self.xmin + self.width * self.step, self.ymax)

    @property
    def gt(self):
        return (self.xmin, self.step, 0, self.ymax, 0, -self.step)

    @classmethod
    def around(cls, points, radius, step):
        xmin = math.floor((min(p['x'] for p in points) - radius) / step) * step
        ymax = math.ceil((max(p['y'] for p in points) + radius) / step) * step
        xmax = math.ceil((max(p['x'] for p in points) + radius) / step) * step
        ymin = math.floor((min(p['y'] for p in points) - radius) / step) * step
        return cls(xmin, ymax, step, round((xmax - xmin) / step), round((ymax - ymin) / step))

    def window_in(self, other):
        return round((self.xmin - other.xmin) / self.step), round((other.ymax - self.ymax) / self.step)

    def circle(self, point, radius):
        x = self.xmin + (np.arange(self.width) + 0.5) * self.step - point['x']
        y = self.ymax - (np.arange(self.height) + 0.5) * self.step - point['y']
        return y[:, None] ** 2 + x[None, :] ** 2 <= radius ** 2


def srs2180():
    result = osr.SpatialReference()
    result.ImportFromEPSG(2180)
    return result


def create_raster(path, grid, dtype=gdal.GDT_Float32, nodata=NODATA):
    ds = gdal.GetDriverByName('GTiff').Create(str(path), grid.width, grid.height, 1, dtype, CREATE)
    if ds is None:
        raise ValueError('Nie można zapisać rastra: ' + str(path))
    ds.SetGeoTransform(grid.gt)
    ds.SetProjection(srs2180().ExportToWkt())
    if nodata is not None:
        ds.GetRasterBand(1).SetNoDataValue(nodata)
    ds.SetMetadataItem('PLUGIN_VERSION', VERSION)
    ds.SetMetadataItem('ANALYSIS_PIXEL_M', str(grid.step))
    return ds


def write_array(path, grid, values, dtype=gdal.GDT_Float32, nodata=NODATA):
    ds = create_raster(path, grid, dtype, nodata)
    ds.GetRasterBand(1).WriteArray(values)
    ds.FlushCache()
    return ds


def warp_grid(path, source, grid, algorithm, callback):
    result = gdal.Warp(str(path), source, format='GTiff', dstSRS='EPSG:2180',
                       outputBounds=grid.bounds, width=grid.width, height=grid.height,
                       resampleAlg=algorithm, dstNodata=NODATA, outputType=gdal.GDT_Float32,
                       creationOptions=CREATE, warpMemoryLimit=64, callback=callback)
    if result is None:
        raise ValueError('Nie udało się przygotować modelu obliczeniowego')
    return result


class ModelSources:
    """Virtual data mosaics and binary quality mosaics; no full-area array in memory."""

    def __init__(self, store, folder, geometries, event, log, notify=lambda _: None, cache_folder=None):
        self.store, self.folder, self.event = store, folder, event
        folder.mkdir(parents=True, exist_ok=True)
        numbers = set()
        for geometry in geometries:
            numbers.update(store.index.intersects(geometry.boundingBox()))
        self.records = [store.records[i] for i in sorted(numbers, reverse=True)]  # Finest goes last in VRT.
        data_paths, valid_paths = [], []
        for number, record in enumerate(self.records):
            check_cancel(event)
            notify(f'Przygotowanie masek: plik {number + 1}/{len(self.records)}')
            path = record['path']
            source = gdal.Open(path, gdal.GA_ReadOnly)
            if source is None:
                log('Pominięto niedostępny plik: ' + path)
                continue
            grid = Grid(record['gt'][0], record['gt'][3], record['gt'][1], record['width'], record['height'])
            data_path = folder / f'data_{number}.vrt'
            normalized = gdal.Translate(str(data_path), source, format='VRT', outputType=gdal.GDT_Float32,
                                        unscale=True, outputBounds=[grid.bounds[0], grid.bounds[3], grid.bounds[2], grid.bounds[1]])
            if normalized is None:
                raise ValueError('Błąd przygotowania źródła: ' + path)
            normalized = None
            cache_key, valid_path = None, folder / f'valid_{number}.tif'
            if cache_folder is not None:
                # Sidecar masks and PAM metadata can change independently of the raster.
                sidecars = []
                for suffix in ['.msk', '.aux.xml']:
                    side = Path(path + suffix)
                    if side.is_file():
                        stat = side.stat()
                        sidecars.append((suffix, stat.st_size, stat.st_mtime_ns))
                identity = dict(version='validity-v1', record=record, sidecars=sidecars,
                                nodata=source.GetRasterBand(1).GetNoDataValue())
                cache_key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
                try:
                    cache_folder.mkdir(parents=True, exist_ok=True)
                    valid_path = cache_folder / (cache_key + '.tif')
                except OSError:
                    cache_key = None
            if cache_key and valid_path.is_file():
                cached = None
                try:
                    cached = gdal.Open(str(valid_path))
                    good_cache = cached is not None and cached.GetMetadataItem('VALIDITY_KEY') == cache_key and (
                        cached.RasterXSize, cached.RasterYSize) == (grid.width, grid.height) and cached.GetGeoTransform() == grid.gt
                except RuntimeError:
                    good_cache = False
                cached = None
                if good_cache:
                    source = None
                    data_paths.append(str(data_path))
                    valid_paths.append(str(valid_path))
                    notify(f'Użyto zapisanej maski: plik {number + 1}/{len(self.records)}')
                    continue
            final_valid_path = valid_path
            if cache_key:
                valid_path = folder / f'valid_{number}.tif'
            valid = create_raster(valid_path, grid, gdal.GDT_Byte, None)
            if cache_key:
                valid.SetMetadataItem('VALIDITY_KEY', cache_key)
            band = source.GetRasterBand(1)
            for y in range(0, grid.height, 512):
                for x in range(0, grid.width, 512):
                    check_cancel(event)
                    width, height = min(512, grid.width - x), min(512, grid.height - y)
                    values = band.ReadAsArray(x, y, width, height)
                    mask = band.GetMaskBand().ReadAsArray(x, y, width, height)
                    if values is None or mask is None:
                        raise ValueError('Błąd odczytu pikseli: ' + path)
                    physical = values * record['scale'] + record['offset']
                    good = (mask != 0) & np.isfinite(physical) & (physical >= -12000) & (physical <= 10000)
                    valid.GetRasterBand(1).WriteArray(good.astype(np.uint8), x, y)
            valid = None
            if cache_key:
                temporary = cache_folder / (cache_key + '.' + uuid.uuid4().hex + '.tmp.tif')
                try:
                    shutil.copy2(valid_path, temporary)
                    temporary.replace(final_valid_path)
                    valid_path = final_valid_path
                except OSError as exc:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        log('Nie można usunąć tymczasowej maski cache: ' + str(temporary))
                    log('Maska zostaje w folderze roboczym; zapis cache niedostępny: ' + str(exc))
            source = None
            data_paths.append(str(data_path))
            valid_paths.append(str(valid_path))
        self.data, self.valid = None, None
        if data_paths:
            self.data = gdal.BuildVRT(str(folder / 'data.vrt'), data_paths, resolution='highest', VRTNodata=NODATA)
            self.valid = gdal.BuildVRT(str(folder / 'valid.vrt'), valid_paths, resolution='highest')
            if self.data is None or self.valid is None:
                raise ValueError('Błąd mozaiki źródeł')

    def local(self, grid, name, algorithm, callback):
        if self.data is None:
            return np.full((grid.height, grid.width), np.nan, np.float32), np.zeros((grid.height, grid.width), bool)
        path = self.folder / (name + '.tif')
        dataset = warp_grid(path, self.data, grid, algorithm, callback)
        values = dataset.ReadAsArray()
        dataset = None
        path.unlink(missing_ok=True)
        quality = gdal.Warp(str(path), self.valid, format='GTiff', outputBounds=grid.bounds,
                            width=grid.width, height=grid.height, resampleAlg='min', outputType=gdal.GDT_Byte,
                            creationOptions=CREATE, srcNodata=255, dstNodata=255, warpMemoryLimit=64, callback=callback)
        if quality is None:
            raise ValueError('Błąd maski jakości danych')
        good = quality.ReadAsArray() == 1
        quality = None
        path.unlink(missing_ok=True)
        good &= np.isfinite(values) & (values != NODATA)
        return values, good

    def close(self):
        self.data, self.valid = None, None


def minimum_height(surface, grid, turbine, absolute_z, work, curve, event, notify=lambda _: None):
    """Reverse LOS by reciprocity: turbine at its actual height, receiver eye at every cell."""
    row = min(grid.height - 1, max(0, int((grid.ymax - turbine['y']) / grid.step)))
    col = min(grid.width - 1, max(0, int((turbine['x'] - grid.xmin) / grid.step)))
    # GDAL snaps the source to a raster cell; the absolute turbine height remains unchanged.
    source = write_array(work / 'surface.tif', grid, surface.astype(np.float64) + BIAS, gdal.GDT_Float64)
    last = [0.0]

    def progress(fraction, message, data):
        if event.is_set():
            return 0
        current = time.monotonic()
        if current - last[0] > 0.35:
            notify(fraction)
            last[0] = current
        return 1

    output = gdal.ViewshedGenerate(source.GetRasterBand(1), 'GTiff', str(work / 'height.tif'), CREATE,
                                   turbine['x'], turbine['y'], float(absolute_z - surface[row, col]), 0,
                                   1, 0, 0, 255, curve, gdal.GVM_Max, 0,
                                   callback=progress, heightMode=gdal.GVOT_MIN_TARGET_HEIGHT_FROM_DEM)
    source = None
    check_cancel(event)
    if output is None:
        raise ValueError('GDAL nie wykonał mapy widoczności: ' + gdal.GetLastErrorMsg())
    if (output.RasterXSize, output.RasterYSize) != (grid.width, grid.height):
        raise ValueError('GDAL zmienił nieoczekiwanie zasięg wyniku')
    heights = (output.ReadAsArray() - BIAS).astype(np.float32)
    output = None
    return heights


def circular_viewshed(ground, ground_valid, surface, surface_valid, grid, turbine, radius,
                      ground_at_turbine, eye, work, event, curvature=True, notify=lambda *args: None):
    inside = grid.circle(turbine, radius)
    valid = ground_valid & surface_valid
    missing = inside & ~valid
    has_missing = bool(missing.any())
    occupied = inside & valid & (surface > ground + eye)
    curve = 6 / 7 if curvature else 0
    eye_z = ground + eye
    known_surface = np.fmax(surface, ground)
    optimistic = np.where(valid, known_surface, -1000000).astype(np.float32)
    pessimistic = np.where(valid, known_surface, 1000000).astype(np.float32)
    # No artificial barrier around the bounding rectangle's corners outside the requested disk.
    optimistic[~inside] = -1000000
    pessimistic[~inside] = -1000000
    row = min(grid.height - 1, max(0, int((grid.ymax - turbine['y']) / grid.step)))
    col = min(grid.width - 1, max(0, int((turbine['x'] - grid.xmin) / grid.step)))
    source_valid = valid[row, col] and math.isfinite(ground_at_turbine)
    visible, uncertain = [], []
    for level, offset in [('tip', turbine['hub'] + turbine['diameter'] / 2),
                          ('hub', turbine['hub']), ('bottom', max(0.1, turbine['hub'] - turbine['diameter'] / 2))]:
        check_cancel(event)
        if not source_valid or ground_at_turbine + offset <= known_surface[row, col]:
            visible.append(np.zeros(inside.shape, bool))
            uncertain.append(inside & ~occupied)
            continue
        notify(level, 0)
        low = minimum_height(optimistic, grid, turbine, ground_at_turbine + offset, work, curve, event,
                             lambda f: notify(level, f / 2 if has_missing else f))
        maybe = (eye_z >= low) & inside & valid & ~occupied
        if has_missing:
            high = minimum_height(pessimistic, grid, turbine, ground_at_turbine + offset, work, curve, event,
                                  lambda f: notify(level, 0.5 + f / 2))
            certain = (eye_z >= high) & inside & valid & ~occupied
        else:
            certain = maybe
        visible.append(certain)
        uncertain.append(((maybe & ~certain) | missing) & inside & ~occupied)
    quality = np.zeros(inside.shape, np.uint8)
    quality[inside] = 1
    quality[np.logical_or.reduce(uncertain)] = 2
    quality[missing] = 3
    quality[occupied] = 4
    return inside, visible, uncertain, quality


class Product:
    def __init__(self, folder, spec, turbines):
        self.spec = spec
        self.grid = Grid.around(turbines, spec['radius'], spec['resolution'])
        self.paths, self.datasets = {}, {}
        self.turbines = []
        if self.grid.width * self.grid.height > MAX_TOTAL_CELLS:
            raise ValueError(f'{spec["resource"]}: zbyt duży wspólny raster. Zwiększ krok obliczeń albo wybierz mniej turbin.')
        self.folder = folder / spec['resource']
        self.folder.mkdir()
        for name in ['count', 'hub', 'bottom', 'unknown', 'scope', 'quality', 'rotor']:
            path = self.folder / (name + '.tif')
            byte = name in ('quality', 'rotor')
            self.paths[name] = str(path)
            self.datasets[name] = create_raster(path, self.grid, gdal.GDT_Byte if byte else gdal.GDT_UInt16, 0 if byte else NOCOUNT)
        self.state = 'running'

    def merge(self, grid, inside, visible, uncertain, quality):
        xoff, yoff = grid.window_in(self.grid)
        for name, addition in [('count', visible[0]), ('hub', visible[1]), ('bottom', visible[2]),
                               ('unknown', uncertain[0]), ('scope', inside)]:
            band = self.datasets[name].GetRasterBand(1)
            old = band.ReadAsArray(xoff, yoff, grid.width, grid.height)
            values = np.where(old == NOCOUNT, 0, old).astype(np.uint16)
            values += addition.astype(np.uint16)
            active = (old != NOCOUNT) | inside
            values[~active] = NOCOUNT
            band.WriteArray(values, xoff, yoff)
        band = self.datasets['quality'].GetRasterBand(1)
        old = band.ReadAsArray(xoff, yoff, grid.width, grid.height)
        band.WriteArray(np.maximum(old, quality), xoff, yoff)

    def finish(self, event, callback):
        counts = Counter()
        for y in range(0, self.grid.height, 256):
            callback(y / self.grid.height, '', None)
            for x in range(0, self.grid.width, 256):
                check_cancel(event)
                width, height = min(256, self.grid.width - x), min(256, self.grid.height - y)
                arrays = {name: self.datasets[name].GetRasterBand(1).ReadAsArray(x, y, width, height)
                          for name in ['count', 'hub', 'bottom', 'unknown', 'quality']}
                active = arrays['count'] != NOCOUNT
                rotor = np.zeros(active.shape, np.uint8)
                rotor[active] = 1
                rotor[active & (arrays['count'] > 0)] = 2
                rotor[active & (arrays['hub'] > 0)] = 3
                rotor[active & (arrays['bottom'] > 0)] = 4
                rotor[active & (arrays['count'] == 0) & (arrays['unknown'] > 0)] = 5
                self.datasets['rotor'].GetRasterBand(1).WriteArray(rotor, x, y)
                counts['cells'] += int(active.sum())
                counts['visible_cells'] += int((active & (arrays['count'] > 0)).sum())
                counts['unknown_cells'] += int((active & (arrays['quality'] >= 2) & (arrays['quality'] <= 3)).sum())
                counts['occupied_cells'] += int((active & (arrays['quality'] == 4)).sum())
        self.summary = dict(counts, area_km2=counts['cells'] * self.grid.step ** 2 / 1000000,
                            visible_km2=counts['visible_cells'] * self.grid.step ** 2 / 1000000)
        self.close()
        for path in self.paths.values():
            check_cancel(event)
            ds = gdal.Open(path, gdal.GA_Update)
            levels = [v for v in [2, 4, 8, 16, 32, 64] if min(ds.RasterXSize, ds.RasterYSize) // v >= 32]
            if levels:
                ds.BuildOverviews('NEAREST', levels, callback=callback)
            ds = None
        self.state = 'completed_with_gaps' if counts['unknown_cells'] else 'completed'
        return self.as_dict()

    def close(self):
        for name in list(self.datasets):
            self.datasets[name].FlushCache()
            self.datasets.pop(name)

    def as_dict(self):
        return dict(**self.spec, paths=self.paths, bounds=self.grid.bounds, columns=self.grid.width,
                    rows=self.grid.height, state=self.state, summary=getattr(self, 'summary', {}),
                    turbines=self.turbines)


class AtlasEngine:
    def __init__(self, source, crs, context, options, contexts=None, notify=lambda _: None, log=lambda _: None):
        self.source, self.crs, self.context = source, crs, context
        self.options, self.contexts = options, contexts or {}
        self.scene_contexts = {key: value for key, value in self.contexts.items() if key in ('lasy', 'drzewa', 'budynki_3d')}
        self.contexts = {key: value for key, value in self.contexts.items() if key not in ('lasy', 'drzewa', 'budynki_3d')}
        self.notify, self.log = notify, log
        self.cancel_event = threading.Event()
        self.started, self.report_dir = time.monotonic(), None
        self.phase_started = None
        self.report = dict(version=VERSION, state='running', started_at=now(), options=options,
                           products=[], downloads=[], input_issues=[], raster_errors=[], sources={},
                           algorithm='GDAL minimum absolute target height; reciprocity; three rotor heights; bounded NoData')

    def event(self, message):
        self.log(message)
        if self.report_dir and self.report_dir.is_dir():
            try:
                with (self.report_dir / 'events.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(dict(time=now(), message=message), ensure_ascii=False) + '\n')
            except OSError:
                pass

    def stats(self, stage, done=0, total=0, **extras):
        self.current_stage = stage
        fraction = extras.get('fraction_done', done / total if total else 0)
        elapsed = time.monotonic() - self.phase_started if self.phase_started else 0
        self.notify(dict(kind='atlas', stage=stage, done=done, total=total,
                         elapsed=time.monotonic() - self.started,
                         eta=elapsed * (1 - fraction) / fraction if fraction > 0 else None,
                         transfer_bytes=sum(d['transfer_bytes'] for d in self.report['downloads']), **extras))

    def callback(self, fraction, message, data):
        current = time.monotonic()
        if current - getattr(self, 'last_callback', 0) >= 0.5:
            self.last_callback = current
            self.stats(getattr(self, 'current_stage', 'Przygotowanie danych'), 0, 0,
                       operation_percent=round(fraction * 100))
        return 0 if self.cancel_event.is_set() else 1

    def checkpoint(self):
        self.report['elapsed_seconds'] = time.monotonic() - self.started
        atomic_json(self.report_dir / 'report.json', self.report)

    def download(self, turbines):
        plans = {}
        for spec in self.options['models']:
            for resource in (['NMT'] if spec['resource'] == 'NMT' else ['NMT', 'NMPT']):
                key = resource, spec['height']
                radius = spec['radius'] + 2 * spec['resolution'] + 5
                plans.setdefault(key, []).extend(QgsGeometry.fromPointXY(QgsPointXY(t['x'], t['y'])).buffer(radius, 64) for t in turbines)
        for (resource, height), geometries in plans.items():
            check_cancel(self.cancel_event)
            settings = dict(self.options['source_settings'][resource], height=height, alternate_height=False)
            opts = dict(resources=[resource], radius=0, folders={resource: self.options['folders'][resource]},
                        report_folder=str(self.report_dir / ('pobieranie_' + resource)),
                        pixels=self.options.get('pixels', 1024), workers=self.options.get('workers', 2),
                        reuse=True, feature_ids=None, resource_settings={resource: settings})
            self.event(f'Pobieranie {resource}, {height}: koła, {len(geometries)} obszarów; zgodne pliki będą użyte ponownie')

            def notify(stats):
                previous = sum(item['transfer_bytes'] for item in self.report['downloads'])
                self.notify(dict(stats, kind='download', resource=resource, all_bytes=previous + stats['bytes']))

            engine = Engine(GeometrySource(geometries), QgsCoordinateReferenceSystem('EPSG:2180'), self.context,
                            opts, notify, self.event)
            engine.cancel_event = self.cancel_event
            result = engine.run()
            self.report['downloads'].append(dict(resource=resource, height=height, state=result['state'],
                                                 report_dir=result.get('report_dir'), transfer_bytes=engine.bytes_received))
            self.checkpoint()
            check_cancel(self.cancel_event)

    def run(self):
        models, stores, products = [], [], []
        rays = None
        try:
            self.report_dir = Path(self.options['report_folder']) / ('atlas_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
            self.report_dir.mkdir(parents=True)
            work = self.report_dir / '.work'
            work.mkdir()
            self.report['report_dir'] = str(self.report_dir)
            self.checkpoint()
            self.event('Start atlasu widoczności pełnych kół NMT / NMPT')
            self.stats('Przygotowanie turbin i kół analizy')
            turbines, issues = read_points(self.source, self.crs, self.context, 'turbines', self.options, self.cancel_event)
            valid_turbines = []
            for turbine in turbines:
                if turbine['hub'] <= turbine['diameter'] / 2:
                    issues.append(dict(id=turbine['id'], reason='Wirnik sięga poziomu gruntu: popraw wysokość piasty / średnicę'))
                else:
                    valid_turbines.append(turbine)
            turbines = valid_turbines
            if not turbines:
                raise ValueError('Brak turbin o poprawnej wysokości piasty i średnicy wirnika')
            if len(turbines) > 1000:
                raise ValueError('Wybierz maksymalnie 1000 turbin na zadanie')
            if self.options.get('details', True) and not 1 <= int(self.options.get('view_turbine', 1)) <= len(turbines):
                raise ValueError('Numer turbiny do przekroju / 3D jest poza analizowanym zestawem')
            self.report.update(turbines=turbines, input_issues=issues)
            for spec in self.options['models']:
                if not 0.5 <= spec['resolution'] <= 1000 or not 1 <= spec['radius'] <= 200000:
                    raise ValueError('Nieprawidłowy krok lub promień analizy')
                if spec['resolution'] > spec['radius']:
                    raise ValueError('Krok obliczeń nie może być większy od promienia koła')
                grid = Grid.around([turbines[0]], spec['radius'], spec['resolution'])
                if grid.width * grid.height > MAX_LOCAL_CELLS:
                    raise ValueError(f'{spec["resource"]}: koło ma za dużo pikseli. Zwiększ krok obliczeń lub zmniejsz promień (limit {MAX_LOCAL_CELLS / 1e6:g} mln komórek na turbinę).')
                # Validate all output extents before a potentially large download.
                combined = Grid.around(turbines, spec['radius'], spec['resolution'])
                if combined.width * combined.height > MAX_TOTAL_CELLS:
                    raise ValueError(f'{spec["resource"]}: turbiny są zbyt rozproszone dla wybranego kroku. Zwiększ krok lub wybierz podzbiór.')
            if self.options.get('auto_download', True):
                self.download(turbines)
            self.report['details'], self.report['visualization_issues'] = [], []
            if self.options.get('rays', True):
                from .atlas_details import RayWriter
                rays = RayWriter(self.report_dir, self.options.get('ray_spacing', 10), self.cancel_event)
                self.report['rays_gpkg'] = str(rays.path)
                self.report['ray_summary'] = rays.summaries
            for spec in self.options['models']:
                check_cancel(self.cancel_event)
                resource = spec['resource']
                self.stats(f'{resource}: przygotowanie danych i masek NoData')
                geometries = [QgsGeometry.fromPointXY(QgsPointXY(t['x'], t['y'])).buffer(spec['radius'] + 3 * spec['resolution'], 64) for t in turbines]
                source_models = {}
                for kind in (['NMT'] if resource == 'NMT' else ['NMT', 'NMPT']):
                    store = RasterStore(self.options['folders'][kind], kind, spec['height'], self.cancel_event)
                    stores.append(store)
                    model = ModelSources(store, work / (resource + '_' + kind), geometries, self.cancel_event, self.event,
                                         lambda text: self.stats(resource + '/' + kind + ': ' + text),
                                         Path(self.options['report_folder']) / '.nmt_nmpt_cache' / 'validity')
                    models.append(model)
                    source_models[kind] = model
                    self.report['raster_errors'].extend(store.errors)
                    self.report['sources'][resource + '/' + kind] = model.records
                product = Product(self.report_dir, spec, turbines)
                products.append(product)
                self.report['products'].append(product.as_dict())
                if rays:
                    rays.add_model(resource)
                self.event(f'{resource}: rozpoczęto obliczenia {len(turbines)} kół, promień {spec["radius"]:g} m, krok {spec["resolution"]:g} m')
                self.phase_started = time.monotonic()
                for number, turbine in enumerate(turbines):
                    check_cancel(self.cancel_event)
                    stage = f'{resource}: turbina {number + 1}/{len(turbines)}, pełne koło {spec["radius"]:g} m'
                    self.stats(stage, number, len(turbines))
                    grid = Grid.around([turbine], spec['radius'], spec['resolution'])
                    terrain, terrain_valid = source_models['NMT'].local(grid, 'terrain', 'max' if resource == 'NMT' else 'bilinear', self.callback)
                    if resource == 'NMT':
                        surface, surface_valid = terrain, terrain_valid
                    else:
                        surface, surface_valid = source_models['NMPT'].local(grid, 'surface', 'max', self.callback)
                    dtm_store = source_models['NMT'].store
                    height, _ = dtm_store.sample(np.array([turbine['x']]), np.array([turbine['y']]))

                    def notify(level, fraction):
                        labels = {'tip': 'górna końcówka łopaty', 'hub': 'piasta', 'bottom': 'dolny zasięg wirnika'}
                        fraction_done = (number + (list(labels).index(level) + fraction) / 3) / len(turbines)
                        self.stats(stage + ' — ' + labels[level] + f' {100 * fraction:.0f}%', number, len(turbines), fraction_done=fraction_done)

                    try:
                        result = circular_viewshed(terrain, terrain_valid, surface, surface_valid, grid, turbine,
                                                   spec['radius'], float(height[0]), self.options['eye'], work,
                                                   self.cancel_event, self.options.get('curvature', True), notify)
                    except Canceled:
                        raise
                    except Exception as exc:
                        self.event(f'{resource}, turbina {turbine["id"]}: {exc}; pozostałe koła będą liczone dalej')
                        self.report['input_issues'].append(dict(resource=resource, id=turbine['id'], reason=str(exc)))
                        inside = grid.circle(turbine, spec['radius'])
                        empty = np.zeros(inside.shape, bool)
                        result = (inside, [empty, empty, empty], [inside, inside, inside], inside.astype(np.uint8) * 3)
                    product.merge(grid, *result)
                    if rays:
                        self.stats(stage + ' — zapisywanie promieni widoczności', number, len(turbines))
                        rays.write(grid, turbine, spec['radius'], result)
                    if self.options.get('details', True) and number == int(self.options.get('view_turbine', 1)) - 1:
                        from .atlas_details import write_details
                        self.stats(stage + ' — przekrój i siatka podglądu 3D', number, len(turbines))
                        try:
                            self.report['details'].append(write_details(self.report_dir, spec, grid, turbine, terrain,
                                                                        terrain_valid, surface, surface_valid, float(height[0]),
                                                                        self.options, self.cancel_event, self.scene_contexts, self.context))
                        except Canceled:
                            raise
                        except Exception as exc:
                            self.report['visualization_issues'].append(dict(model=resource, reason=str(exc)))
                            self.event('Wynik analizy zachowano; problem podglądu: ' + str(exc))
                    product.turbines.append(dict(id=turbine['id'], ground_z_m=float(height[0]) if np.isfinite(height[0]) else None))
                    self.report['products'][-1] = product.as_dict()
                    self.checkpoint()
                    self.event(f'{resource}: ukończono koło {number + 1}/{len(turbines)}')
                self.stats(f'{resource}: podsumowanie, cienie i piramidy rastrów')
                finished = product.finish(self.cancel_event, self.callback)
                # Shaded terrain for a complete presentation even without a base map in the project.
                shade_path = product.folder / 'hillshade.tif'
                ground_vrt = source_models['NMT'].data
                if ground_vrt is not None:
                    self.stats(resource + ': zapis kolorowego modelu wysokości')
                    terrain_path = product.folder / 'terrain.tif'
                    full = warp_grid(terrain_path, ground_vrt, product.grid, 'bilinear', self.callback)
                    shade = gdal.DEMProcessing(str(shade_path), full, 'hillshade', format='GTiff',
                                               creationOptions=CREATE, computeEdges=True, callback=self.callback)
                    if shade is None:
                        raise ValueError('Nie udało się przygotować cieniowania terenu')
                    full, shade = None, None
                    ground_vrt = None
                    finished['paths']['hillshade'] = str(shade_path)
                    finished['paths']['elevation'] = str(terrain_path)
                    if resource == 'NMPT' and source_models['NMPT'].data is not None:
                        elevation_path = product.folder / 'elevation.tif'
                        elevation = warp_grid(elevation_path, source_models['NMPT'].data, product.grid, 'max', self.callback)
                        elevation.FlushCache()
                        elevation = None
                        finished['paths']['elevation'] = str(elevation_path)
                    # Cache display statistics and pyramids in the worker, before QgsRasterLayer opens on the GUI thread.
                    scope = gdal.Open(finished['paths']['scope'])
                    for name in ['elevation', 'hillshade']:
                        self.stats(resource + ': piramidy i statystyki prezentacji — ' + name)
                        dataset = gdal.Open(finished['paths'][name], gdal.GA_Update)
                        band = dataset.GetRasterBand(1)
                        has_values = False
                        for y in range(0, product.grid.height, 256):
                            check_cancel(self.cancel_event)
                            for x in range(0, product.grid.width, 256):
                                w, h = min(256, product.grid.width - x), min(256, product.grid.height - y)
                                values = band.ReadAsArray(x, y, w, h)
                                values[scope.GetRasterBand(1).ReadAsArray(x, y, w, h) == NOCOUNT] = band.GetNoDataValue()
                                has_values |= bool(np.any(np.isfinite(values) & (values != band.GetNoDataValue())))
                                band.WriteArray(values, x, y)
                            self.callback(y / product.grid.height, '', None)
                        levels = [v for v in [2, 4, 8, 16, 32, 64] if min(dataset.RasterXSize, dataset.RasterYSize) // v >= 32]
                        if levels:
                            dataset.BuildOverviews('AVERAGE', levels, callback=self.callback)
                        if has_values:
                            band.GetStatistics(True, True)
                        else:
                            band.SetStatistics(0, 0, 0, 0)
                        band, dataset = None, None
                    scope = None
                self.report['products'][-1] = finished
                self.checkpoint()
                for model in source_models.values():
                    model.close()
            from .atlas_context import write_context
            if rays:
                rays.close()
            self.stats('Drogi, zabudowa i opcjonalni obserwatorzy — ocena ekspozycji')
            self.report['gpkg'], context_stats = write_context(self.report_dir, self.report['products'], turbines,
                                                               self.contexts, self.context, self.cancel_event)
            self.report['context_summary'] = context_stats
            from .atlas_links import write_shortcuts
            self.report['links_gpkg'] = write_shortcuts(self.report_dir, self.report)
            self.report['state'] = 'completed_with_gaps' if self.report['input_issues'] or any(
                p['state'] != 'completed' for p in self.report['products']) or any(
                item.get('truncated') for item in context_stats + self.report.get('ray_summary', [])) or self.report['visualization_issues'] else 'completed'
        except Canceled:
            self.report['state'] = 'canceled'
        except Exception as exc:
            if self.cancel_event.is_set():
                self.report['state'] = 'canceled'
            else:
                self.report.update(state='failed', fatal_error=str(exc))
                self.event('Błąd atlasu: ' + str(exc))
        finally:
            if rays:
                rays.close()
            for product in products:
                product.close()
            for model in models:
                model.close()
            for store in stores:
                store.close()
            if self.report_dir and self.report_dir.is_dir():
                try:
                    self.event('Zakończono atlas: ' + self.report['state'])
                    self.checkpoint()
                    self.write_markdown()
                except Exception as exc:
                    self.report.update(state='failed', fatal_error='Zapis raportu: ' + str(exc))
                if (self.report_dir / '.work').exists():
                    shutil.rmtree(self.report_dir / '.work', ignore_errors=True)
            self.stats('Zakończono: ' + self.report['state'])
        return self.report

    def write_markdown(self):
        lines = ['# Atlas widoczności turbin', '', f'Wersja {VERSION}; stan **{self.report["state"]}**.',
                 f'Czas: {self.report["elapsed_seconds"]:.1f} s; EPSG:2180.', '',
                 'Wynik odpowiada: z których miejsc otoczenia widać turbinę na wysokości końca łopaty, piasty i dolnego zasięgu wirnika.',
                 'Nie jest to obserwacja z poziomu gruntu pod turbiną. Obliczenia korzystają z wzajemności linii widzenia.', '',
                 '| Model | Promień [m] | Krok [m] | Obszar [km²] | Widoczna ≥1 turbina [km²] | Komórki z niepewnością |',
                 '|---|---:|---:|---:|---:|---:|']
        for product in self.report['products']:
            summary = product.get('summary', {})
            lines.append(f'| {product["resource"]} | {product["radius"]:g} | {product["resolution"]:g} | '
                         f'{summary.get("area_km2", 0):.3f} | {summary.get("visible_km2", 0):.3f} | {summary.get("unknown_cells", 0)} |')
        lines += ['', '## Ekspozycja ważnych miejsc', '']
        for item in self.report.get('context_summary', []):
            suffix = ' — osiągnięto limit; pozostałe geometrie nie zostały ocenione' if item.get('truncated') else ''
            lines.append(f'- {item["model"]} / {item["role"]}: {item["features"]} elementów{suffix}')
        lines += ['', '## Interpretacja', '',
                  '- count.tif / hub.tif / bottom.tif: liczba turbin widocznych na danej wysokości; 65535 poza analizą.',
                  '- rotor.tif: 1 brak widoczności, 2 co najmniej koniec łopaty, 3 co najmniej piasta, 4 także dolny zasięg wirnika, 5 nierozstrzygnięte. Nie jest to procent powierzchni wirnika.',
                  '- quality.tif: 1 model kompletny, 2 niepewna trasa, 3 brak danych w miejscu obserwacji, 4 oko wewnątrz powierzchni NMPT (dach/korona), 0 poza analizą.',
                  '- unknown.tif: liczba turbin z nierozstrzygniętą widocznością końca łopaty. count to liczba potwierdzona w modelu; przy niepewności jest dolnym ograniczeniem.',
                  '- scope.tif: liczba turbin w zadanym promieniu danego piksela. Nie sumuj powierzchni nakładających się kół.',
                  '- Krok obliczeń nie jest dokładnością pomiarową. Przeszkody są agregowane maksimum, aby nie uśrednić dachów i wąskich grzbietów.',
                  '- Braki propagowane są dwoma modelami skrajnymi: optymistycznym i pesymistycznym. Nie są zastępowane zerem jako znany teren.',
                  '- Oko jest nad gruntem NMT; w NMPT dachy i korony są nieprzezroczystą powierzchnią 2,5D.',
                  '- Analiza NMT opisuje rzeźbę terenu; nie potwierdza braku przesłaniania przez budynki lub drzewa.',
                  '- Trzy wysokości wirnika są trzema punktami. Nie wykonano siatkowego ray tracingu ani animacji wirnika.',
                  '- Krzywizna i refrakcja: współczynnik 6/7, jeśli włączone. Algorytm GDAL GVM_Max jest konserwatywną aproksymacją rastrową.',
                  '- Drogi i poligony są oceniane na próbkach; zabudowa/poligony po zewnętrznym obrysie, nie pod dachem.', '',
                  '- widoczne_pct: procent próbek z potwierdzoną widocznością co najmniej jednej turbiny (80% = np. 8 z 10 próbek). To nie procent powierzchni wirnika ani działki.',
                  '- niepewne_pct: procent próbek z niepewną trasą, brakiem danych lub okiem pod powierzchnią. Kategorie mogą się nakładać z potwierdzoną widocznością innych turbin.',
                  '- promienie.gpkg: odcinki dla konkretnej turbiny; piasta/koniec/dolny: 0 zasłonięta, 1 widoczna, 2 niepewna, 3 oko pod powierzchnią. Azymut od północy siatki EPSG:2180. Promienie są ilustracją próbek rastrowych, nie ciągłym pomiarem co do centymetra.',
                  '- elevation.tif / terrain.tif: barwy wysokości, zielony nisko, czerwony wysoko. Nie mylić z liczbą turbin.',
                  '- profil_*.svg i scena_3d_*.html: wybrana turbina i kierunek. Podgląd 3D ma rzadszą siatkę; nie zmienia kroku analizy. Profil czyta model obliczeniowy i uwzględnia opcjonalną krzywiznę.', '',
                  '## Dane i problemy', '']
        for item in self.report.get('details', []):
            lines.append(f'- {item["model"]}: [przekrój]({Path(item["profile"]).name}), [scena 3D]({Path(item["scene"]).name}); turbina {item["turbine"]}, azymut {item["azimuth"]:g}°.')
            lines.append(f'  Promień sceny: {item.get("scene_radius", 0):g} m; siatka {item.get("vertices", [])}; krok {item["preview_step_m"]:g} m.')
            for context in item.get('context_summary', []):
                lines.append(f'  BDOT / {context["role"]}: {context["features"]} użytych, {context["skipped"]} pominiętych; limit: {context["truncated"]}. Tylko prezentacja, wysokości z NMT/NMPT.')
        for item in self.report.get('ray_summary', []):
            lines.append(f'- Promienie {item["model"]}: {item["features"]} odcinków; krok {item["spacing_degrees"]:g}°; limit osiągnięty: {item["truncated"]}.')
        for item in self.report.get('visualization_issues', []):
            lines.append('- Problem podglądu: ' + str(item))
        if self.report.get('fatal_error'):
            lines.append(self.report['fatal_error'])
        for issue in self.report['input_issues'] + self.report['raster_errors']:
            lines.append('- ' + str(issue))
        (self.report_dir / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
