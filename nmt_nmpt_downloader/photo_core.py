"""Local perspective photographs, bounded raster sampling and reproducible photomontages.

Worker-only preparation. Never downloads imagery or changes analysis products.
"""
import base64
from collections import OrderedDict
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import uuid

import numpy as np
from osgeo import gdal, osr
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QImageReader

from .core import VERSION, atomic_json, check_cancel

MAX_PHOTOS = 24
MAX_TARGETS = 200
MAX_RAY_SAMPLES = 8192
EARTH_DIAMETER = 12756274.0


def photo_config(value):
    """Validate a saved camera; headings refer to the EPSG:2180 map grid."""
    item = copy.deepcopy(value)
    identifier = str(item.get('id') or uuid.uuid4().hex)
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', identifier):
        raise ValueError('Nieprawidłowy identyfikator zdjęcia')
    item.update(id=identifier, name=str(item.get('name') or 'Zdjęcie')[:120])
    limits = dict(x=(-1000000, 2000000), y=(-1000000, 2000000), heading=(0, 360),
                  eye=(0.1, 1000), fov=(10, 140), pitch=(-85, 85), roll=(-45, 45))
    defaults = dict(eye=1.7, fov=65, pitch=0, roll=0, heading=0)
    for key, (low, high) in limits.items():
        number = float(item.get(key, defaults.get(key, float('nan'))))
        if not math.isfinite(number) or not low <= number <= high:
            raise ValueError('Nieprawidłowy parametr aparatu: ' + key)
        item[key] = number
    item['heading'] %= 360
    item['resource'] = str(item.get('resource', 'NMPT'))
    if item['resource'] not in ('NMT', 'NMPT'):
        raise ValueError('Wybierz model NMT albo NMPT')
    if not item.get('image_path'):
        raise ValueError('Wskaż plik zdjęcia JPG lub PNG')
    for key, low, high in [('yaw', 0, 360), ('phase', 0, 360), ('opacity', 0, 1)]:
        if key in item:
            number = float(item[key])
            if not math.isfinite(number) or not low <= number <= high:
                raise ValueError('Nieprawidłowe ustawienie: ' + key)
            item[key] = number
    if 'mask_strokes' in item:
        validate_mask(item['mask_strokes'])
    return item


def validate_mask(strokes):
    if not isinstance(strokes, list) or len(strokes) > 2000:
        raise ValueError('Nieprawidłowa lub zbyt duża maska')
    count = 0
    for stroke in strokes:
        if not isinstance(stroke, dict) or stroke.get('mode') not in ('hide', 'restore'):
            raise ValueError('Nieprawidłowy tryb maski')
        radius = float(stroke['radius'])
        if not math.isfinite(radius) or not 0 < radius <= 1:
            raise ValueError('Nieprawidłowy rozmiar pędzla')
        points = stroke['points']
        if not isinstance(points, list) or not 1 <= len(points) <= 10000:
            raise ValueError('Nieprawidłowe punkty maski')
        count += len(points)
        if count > 200000:
            raise ValueError('Maska przekracza limit 200 000 punktów')
        for point in points:
            if not isinstance(point, list) or len(point) != 2 or not all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in point):
                raise ValueError('Punkt maski poza zdjęciem')


def resolve_asset(root, value):
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path(root) / path


def inspect_photo(path):
    """Read headers only; actual image decoding takes place in the worker."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError('Zdjęcie nie istnieje albo przekracza 100 MB')
    reader = QImageReader(str(path))
    size = reader.size()
    if bytes(reader.format()).lower() not in (b'jpeg', b'jpg', b'png') or not reader.canRead():
        raise ValueError('Wybierz zwykłe zdjęcie JPG lub PNG. HEIC/HEIF wyeksportuj najpierw do JPG.')
    if size.width() <= 0 or size.height() <= 0 or size.width() * size.height() > 150000000:
        raise ValueError('Nieprawidłowy rozmiar zdjęcia lub więcej niż 150 MP')
    return dict(width=size.width(), height=size.height(), bytes=path.stat().st_size)


def decode_photo(path, destination):
    info = inspect_photo(path)
    width, height = info['width'], info['height']
    factor = min(1., 6000 / max(width, height), math.sqrt(24000000 / (width * height)))
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    reader.setScaledSize(QSize(max(1, round(width * factor)), max(1, round(height * factor))))
    image = reader.read()
    if image.isNull():
        raise ValueError('Nie można odczytać zdjęcia: ' + reader.errorString())
    if not image.save(str(destination), 'JPEG', 96):
        raise ValueError('Nie można zapisać lokalnego zdjęcia do wizualizacji')
    info.update(width=image.width(), height=image.height(), reduced=factor < 1, exif_rotated=True)
    return info


def exif_camera(path, width, height):
    """Optional 35 mm equivalent focal length: never guess the physical sensor size."""
    result = dict(fov_source='Domyślne 65° — dopasuj do zdjęcia', fov=65., metadata={})
    gdal.PushErrorHandler('CPLQuietErrorHandler')
    try:
        ds = gdal.OpenEx(str(path), gdal.OF_RASTER | gdal.OF_READONLY)
        metadata = dict(ds.GetMetadata() or {}, **(ds.GetMetadata('EXIF') or {})) if ds else {}
        ds = None
    except (RuntimeError, ValueError, TypeError):
        metadata = {}
    finally:
        gdal.PopErrorHandler()
    for key in ('EXIF_DateTimeOriginal', 'EXIF_Make', 'EXIF_Model', 'EXIF_FocalLength',
                'EXIF_FocalLengthIn35mmFilm', 'EXIF_Orientation', 'EXIF_GPSImgDirection', 'EXIF_GPSImgDirectionRef'):
        if key in metadata:
            result['metadata'][key] = str(metadata[key])[:200]
    raw = metadata.get('EXIF_FocalLengthIn35mmFilm', '')
    match = re.search(r'[0-9]+(?:\.[0-9]+)?', raw)
    if match and 5 <= float(match.group()) <= 1000:
        focal = float(match.group())
        sensor_width = math.hypot(36, 24) * width / math.hypot(width, height)
        fov = math.degrees(2 * math.atan(sensor_width / (2 * focal)))
        if 10 <= fov <= 140:
            result.update(fov=fov, fov_source='Wstępnie z EXIF: ogniskowa równoważna 35 mm; sprawdź kadr i korekcję telefonu')
    return result


class PhotoRaster:
    """Nearest cell samples with a bounded 16 MB LRU instead of loading the entire atlas."""
    def __init__(self, path):
        self.ds = gdal.Open(str(path))
        if self.ds is None:
            raise ValueError('Brak zapisanego modelu: ' + str(path))
        reference, expected = osr.SpatialReference(), osr.SpatialReference()
        reference.ImportFromWkt(self.ds.GetProjection())
        expected.ImportFromEPSG(2180)
        if not reference.IsSame(expected):
            raise ValueError('Model zdjęcia musi mieć CRS EPSG:2180')
        self.gt = self.ds.GetGeoTransform()
        if self.gt[1] <= 0 or self.gt[5] >= 0 or self.gt[2] or self.gt[4]:
            raise ValueError('Nieobsługiwana siatka zapisanego modelu')
        self.step = max(self.gt[1], -self.gt[5])
        self.cache = OrderedDict()

    def sample(self, x, y):
        x, y = np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
        shape = x.shape
        col = np.floor((x.ravel() - self.gt[0]) / self.gt[1]).astype(np.int64)
        row = np.floor((y.ravel() - self.gt[3]) / self.gt[5]).astype(np.int64)
        valid = (col >= 0) & (row >= 0) & (col < self.ds.RasterXSize) & (row < self.ds.RasterYSize)
        output = np.full(col.shape, np.nan, dtype=float)
        indexes = np.flatnonzero(valid)
        blocks = {}
        for index in indexes:
            blocks.setdefault((int(col[index] // 256), int(row[index] // 256)), []).append(index)
        band = self.ds.GetRasterBand(1)
        nodata = band.GetNoDataValue()
        for key, positions in blocks.items():
            if key not in self.cache:
                cx, cy = key[0] * 256, key[1] * 256
                w, h = min(256, self.ds.RasterXSize - cx), min(256, self.ds.RasterYSize - cy)
                values = band.ReadAsArray(cx, cy, w, h).astype(np.float32)
                mask = band.GetMaskBand().ReadAsArray(cx, cy, w, h) != 0
                good = mask & np.isfinite(values)
                if nodata is not None:
                    good &= values != nodata
                values[~good] = np.nan
                self.cache[key] = values
                if len(self.cache) > 64:
                    self.cache.popitem(last=False)
            values = self.cache[key]
            self.cache.move_to_end(key)
            pos = np.asarray(positions)
            output[pos] = values[row[pos] % 256, col[pos] % 256]
        return output.reshape(shape)

    def close(self):
        self.cache.clear()
        self.ds = None


def horizon_for_target(camera, target, cover, event, curvature):
    """Bounded fan to the tower distance; an estimate, not the formal atlas viewshed.

    A distance margin excludes cells touching the tower. A fan gap stays unknown.
    """
    dx, dy = target['x'] - camera['x'], target['y'] - camera['y']
    distance = math.hypot(dx, dy)
    radius = target['diameter'] / 2
    center = math.atan2(dx, dy)
    half_angle = math.asin(min(.99, (radius + 5) / distance)) + math.radians(.5)
    bearings = np.linspace(center - half_angle, center + half_angle, 65)
    stop = distance - max(cover.step * 1.5, 3.)
    start = max(cover.step * 1.5, 1.)
    if stop <= start:
        return None
    wanted = max(2, int(math.ceil((stop - start) / (cover.step * .5))) + 1)
    ranges = np.linspace(start, stop, min(MAX_RAY_SAMPLES, wanted))
    heights, unknown = [], []
    curve = (6 / 7) / EARTH_DIAMETER if curvature else 0.
    for bearing in bearings:
        check_cancel(event)
        values = cover.sample(camera['x'] + ranges * math.sin(bearing), camera['y'] + ranges * math.cos(bearing))
        finite = np.isfinite(values)
        unknown.append(not bool(finite.all()))
        heights.append(float(np.max(np.arctan2(values[finite] - camera['z'] - curve * ranges[finite]**2, ranges[finite])))
                       if finite.any() else None)
    return dict(bearings=bearings.tolist(), angles=heights, unknown=unknown, samples_per_ray=len(ranges),
                coarsened=wanted > MAX_RAY_SAMPLES, radial_step_m=float(ranges[1] - ranges[0]),
                distance_m=distance, method='65 rays, nearest raster cells, horizon before tower centre')


def prepare_photo(report, config, event, notify=lambda _: None, progress=lambda _: None):
    """Produce an offline HTML; configuration and image files remain with the atlas."""
    photo = photo_config(config)
    root = Path(report['report_dir']).resolve()
    source = resolve_asset(root, photo['image_path'])
    inspect_photo(source)
    product = next((p for p in report.get('products', []) if p['resource'] == photo['resource']), None)
    if not product:
        raise ValueError('Atlas nie ma wybranego modelu ' + photo['resource'])
    folder = root / 'zdjecia_terenowe' / photo['id']
    folder.mkdir(parents=True, exist_ok=True)
    staging = folder / ('przygotowanie_' + uuid.uuid4().hex)
    staging.mkdir()
    ground = cover = None
    try:
        notify('Zdjęcie: obrót EXIF i przygotowanie obrazu…')
        progress(2)
        info = decode_photo(source, staging / 'podglad.jpg')
        check_cancel(event)
        camera_info = exif_camera(source, info['width'], info['height'])
        if photo.get('fov_pending', False):
            photo['fov'] = camera_info['fov']
            photo['fov_source'] = camera_info['fov_source']
            photo['fov_pending'] = False
        model_root = Path(product['paths']['count']).parent
        ground = PhotoRaster(model_root / 'terrain.tif')
        cover = PhotoRaster(product['paths'].get('elevation', model_root / 'terrain.tif'))
        z = float(ground.sample(photo['x'], photo['y']))
        if not math.isfinite(z):
            raise ValueError('Brak NMT w miejscu aparatu. Wybierz właściwy model/zasięg albo popraw punkt na mapie.')
        camera = dict(x=photo['x'], y=photo['y'], z=z + photo['eye'])
        camera_surface = float(cover.sample(photo['x'], photo['y']))
        occupied = math.isfinite(camera_surface) and camera_surface > camera['z'] + .2
        warnings, targets, skipped = [], [], []
        if occupied:
            warnings.append('Według modelu oko aparatu jest pod dachem lub koroną. Automatyczne zasłanianie wyłączono; sprawdź punkt, wysokość i aktualność NMPT.')
        if info['reduced']:
            warnings.append('Obraz do HTML zmniejszono do limitu 6000 px / 24 MP; oryginał zachowano.')
        candidates = sorted(report.get('turbines', []), key=lambda t: math.hypot(t['x'] - photo['x'], t['y'] - photo['y']))
        if len(candidates) > MAX_TARGETS:
            warnings.append(f'Podgląd obejmuje {MAX_TARGETS} najbliższych turbin z {len(candidates)}. Pozostałe wymieniono jako pominięte.')
        known_ground = {str(t['id']): t.get('ground_z_m') for t in product.get('turbines', [])}
        for index, turbine in enumerate(candidates):
            check_cancel(event)
            if index >= MAX_TARGETS:
                skipped.append(dict(id=str(turbine['id']), reason='Limit 200 turbin fotomontażu'))
                continue
            progress(10 + 80 * index / max(1, min(len(candidates), MAX_TARGETS)))
            notify(f'Zdjęcie: teren i zasłanianie turbiny {index + 1}/{min(len(candidates), MAX_TARGETS)}…')
            distance = math.hypot(turbine['x'] - photo['x'], turbine['y'] - photo['y'])
            if distance < max(5, turbine['diameter'] / 2):
                skipped.append(dict(id=str(turbine['id']), reason='Aparat zbyt blisko turbiny dla tego podglądu'))
                continue
            height = known_ground.get(str(turbine['id']))
            if height is None or not math.isfinite(float(height)):
                height = float(ground.sample(turbine['x'], turbine['y']))
            if not math.isfinite(float(height)):
                skipped.append(dict(id=str(turbine['id']), reason='Brak NMT pod turbiną w wybranym modelu'))
                continue
            target = dict(id=str(turbine['id']), x=float(turbine['x']), y=float(turbine['y']),
                          ground=float(height), hub=float(turbine['hub']), diameter=float(turbine['diameter']), distance=distance)
            target['horizon'] = horizon_for_target(camera, target, cover, event, bool(report.get('options', {}).get('curvature', True)))
            if target['horizon'] and any(target['horizon']['unknown']):
                warnings.append('Turbina ' + target['id'] + ': niepełne dane na trasie. Braki nie są uznawane za przeszkodę ani za potwierdzoną widoczność.')
            if target['horizon'] and target['horizon']['coarsened']:
                warnings.append('Turbina ' + target['id'] + ': ograniczono próbkowanie długiej trasy; drobne przeszkody mogą zostać pominięte.')
            targets.append(target)
        if not targets:
            raise ValueError('Brak turbin z poprawną wysokością i odległością. Sprawdź zakres modelu i miejsce aparatu.')
        check_cancel(event)
        photo.update(image_info=info, exif=camera_info['metadata'], warnings=warnings, skipped=skipped,
                     prepared_version=VERSION, prepared_at_utc=datetime.now(timezone.utc).isoformat(),
                     height_datum=product.get('height'), camera_ground_z=z, dirty=False)
        original_name = 'oryginal' + ('.png' if source.suffix.lower() == '.png' else '.jpg')
        shutil.copyfile(source, staging / original_name)
        digest = hashlib.sha256()
        with (staging / original_name).open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                check_cancel(event)
                digest.update(block)
        photo.update(image_path=str((folder / original_name).relative_to(root)),
                     html=str((folder / 'fotomontaz.html').relative_to(root)), source_sha256=digest.hexdigest())
        image_bytes = (staging / 'podglad.jpg').read_bytes()
        # The portable HTML has no absolute path to the user's computer.
        public_photo = {key: value for key, value in photo.items() if key not in ('image_path', 'html')}
        payload = dict(version=VERSION, photo=public_photo, camera=camera, targets=targets,
                       curvature=bool(report.get('options', {}).get('curvature', True)), occupied=occupied,
                       image='data:image/jpeg;base64,' + base64.b64encode(image_bytes).decode('ascii'))
        atomic_json(staging / 'model_fotomontazu.json', {key: value for key, value in payload.items() if key != 'image'})
        from .photo_html import render_photo_html
        progress(95)
        (staging / 'fotomontaz.html').write_text(render_photo_html(payload), encoding='utf-8')
        atomic_json(staging / 'ustawienia.json', photo)
        check_cancel(event)
        # Replace completed files only after every stage succeeds. Existing results survive errors.
        for name in ['podglad.jpg', original_name, 'ustawienia.json', 'model_fotomontazu.json', 'fotomontaz.html']:
            (staging / name).replace(folder / name)
        progress(100)
        return photo
    finally:
        if ground:
            ground.close()
        if cover:
            cover.close()
        shutil.rmtree(staging, ignore_errors=True)
