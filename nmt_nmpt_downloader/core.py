"""Przestrzenny plan pobierania i walidacja danych. Bez zależności od interfejsu."""
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from lxml import etree
from osgeo import gdal, ogr, osr
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeatureRequest,
    QgsFeature, QgsGeometry, QgsRectangle, QgsSpatialIndex,
)

VERSION = '2.0.0'
PLUGIN_NAME = 'NMT i NMTP ściągacz'
STATUS_LABELS = {'downloaded': 'pobrane', 'reused': 'wcześniej pobrane', 'partial': 'częściowe braki',
                 'missing': 'brak danych', 'failed': 'błąd', 'canceled': 'anulowane',
                 'outside_pixels': 'obszar mniejszy od piksela'}
SOURCES = {
    'NMT': ('https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMT/GRID1/WCS/DigitalTerrainModel', 'DTM'),
    'NMPT': ('https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMPT/GRID1/WCS/DigitalSurfaceModel', 'DSM'),
}
NATIVE_RESOLUTION = {'NMT': 1.0, 'NMPT': 0.5}


class Canceled(Exception):
    pass


class ServiceError(Exception):
    pass


def check_cancel(event):
    if event.is_set():
        raise Canceled('Anulowano przez użytkownika')


def xml_root(content):
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(content, parser)
    errors = root.xpath('//*[local-name()="ServiceException" or local-name()="ExceptionText"]')
    if errors:
        raise ServiceError('; '.join(' '.join(e.itertext()).strip() for e in errors)[:2000])
    return root


def parse_description(content, coverage):
    root = xml_root(content)
    offerings = root.xpath('//*[local-name()="CoverageOffering"]')
    offering = next((o for o in offerings if o.xpath('./*[local-name()="name"]/text()') == [coverage]), None)
    if offering is None:
        raise ServiceError('DescribeCoverage nie zawiera zasobu ' + coverage)
    envelopes = offering.xpath('.//*[local-name()="Envelope" and @srsName="EPSG:2180"]')
    if not envelopes:
        raise ServiceError('Brak zasięgu usługi w EPSG:2180')
    coords = [list(map(float, p.text.split())) for p in envelopes[0] if p.text]
    vectors = offering.xpath('.//*[local-name()="offsetVector"]/text()')
    native = min(abs(float(v)) for text in vectors for v in text.split() if float(v))
    formats = offering.xpath('.//*[local-name()="formats"]/text()')
    if 'image/x-aaigrid' not in formats:
        raise ServiceError('Usługa nie udostępnia numerycznego ASCII Grid')
    return {'coverage': coverage, 'bounds': [*coords[0], *coords[1]], 'native_resolution': native}


@dataclass(frozen=True)
class Tile:
    resource: str
    height: str
    resolution: float
    x: int
    y: int
    pixels: int
    endpoint: str = ''

    @property
    def url(self):
        return self.endpoint or SOURCES[self.resource][0]

    @property
    def bbox(self):
        side = self.pixels * self.resolution
        return (self.x * side, self.y * side, (self.x + 1) * side, (self.y + 1) * side)

    @property
    def coverage(self):
        return SOURCES[self.resource][1] + '_' + self.height

    @property
    def name(self):
        res = format(self.resolution, 'g').replace('.', 'p')
        return f'{self.resource}_{self.height}_{res}m_{self.pixels}px_{self.x}_{self.y}.tif'

    @property
    def signature(self):
        return hashlib.sha256(json.dumps([self.url, self.coverage, self.bbox,
                                          self.resolution, self.pixels, 'EPSG:2180']).encode()).hexdigest()

    def params(self):
        return {'SERVICE': 'WCS', 'VERSION': '1.0.0', 'REQUEST': 'GetCoverage',
                'COVERAGE': self.coverage, 'CRS': 'EPSG:2180', 'RESPONSE_CRS': 'EPSG:2180',
                'BBOX': ','.join(format(v, '.6f') for v in self.bbox),
                'RESX': str(self.resolution), 'RESY': str(self.resolution), 'FORMAT': 'image/x-aaigrid'}


def build_buffers(source, source_crs, context, feature_ids, radius, event, notify):
    transform = QgsCoordinateTransform(source_crs, QgsCoordinateReferenceSystem('EPSG:2180'), context)
    request = QgsFeatureRequest()
    request.setSubsetOfAttributes([])
    if feature_ids is not None:
        request.setFilterFids(feature_ids)
    buffers, issues = [], []
    for number, feature in enumerate(source.getFeatures(request)):
        check_cancel(event)
        try:
            geom = QgsGeometry(feature.geometry())
            if geom.isEmpty():
                raise ValueError('Pusta geometria')
            geom.transform(transform)
            if not geom.isGeosValid():
                geom = geom.makeValid()
            if radius > 0:
                geom = geom.buffer(radius, 64)
            if geom.isEmpty() or geom.area() <= 0:
                raise ValueError('Geometria nie wyznacza obszaru; dla punktów/linii ustaw promień > 0')
            if not geom.isGeosValid():
                raise ValueError('Nieprawidłowa geometria po buforowaniu')
            bounds = geom.boundingBox()
            if not all(math.isfinite(v) for v in [bounds.xMinimum(), bounds.yMinimum(), bounds.xMaximum(), bounds.yMaximum()]):
                raise ValueError('Nieskończone współrzędne')
            buffers.append(geom)
        except Exception as exc:
            issues.append({'feature_id': feature.id(), 'reason': str(exc)})
        if number % 50 == 0:
            notify(f'Przygotowanie geometrii: {number + 1} obiektów')
    if not buffers:
        raise ValueError('Brak poprawnych obiektów do pobrania. ' + str(issues[:3]))
    return buffers, issues


def plan_tiles(buffers, resources, height, resolutions, pixels, event, limit=100000):
    """Deduplicated grid. Iterate per feature rather than across a huge global envelope."""
    tiles = {}
    for resource in resources:
        resource_pixels = pixels[resource] if isinstance(pixels, dict) else pixels
        side = resource_pixels * resolutions[resource]
        for geom in buffers:
            check_cancel(event)
            engine = QgsGeometry.createGeometryEngine(geom.constGet())
            engine.prepareGeometry()
            box = geom.boundingBox()
            xmin, xmax = math.floor(box.xMinimum() / side), math.floor(box.xMaximum() / side)
            ymin, ymax = math.floor(box.yMinimum() / side), math.floor(box.yMaximum() / side)
            if (xmax - xmin + 1) * (ymax - ymin + 1) > limit * 10:
                raise ValueError('Obszar zbyt duży. Zwiększ rozmiar piksela albo zmniejsz obszar.')
            for x in range(xmin, xmax + 1):
                check_cancel(event)
                for y in range(ymin, ymax + 1):
                    key = resource, x, y
                    if key in tiles:
                        continue
                    resource_height = height[resource] if isinstance(height, dict) else height
                    tile = Tile(resource, resource_height, resolutions[resource], x, y, resource_pixels)
                    square = QgsGeometry.fromRect(QgsRectangle(*tile.bbox))
                    if engine.intersects(square.constGet()) and geom.intersection(square).area() > 0:
                        tiles[key] = tile
                        if len(tiles) > limit:
                            raise ValueError(f'Przekroczono limit {limit} kafli. Zwiększ rozmiar piksela.')
    return sorted(tiles.values(), key=lambda t: (t.resource, t.y, t.x))


def buffer_index(buffers):
    index = QgsSpatialIndex()
    for number, geometry in enumerate(buffers):
        feature = QgsFeature(number)
        feature.setGeometry(geometry)
        index.addFeature(feature)
    return index


def tile_aoi(tile, buffers, index=None):
    square = QgsGeometry.fromRect(QgsRectangle(*tile.bbox))
    candidates = [buffers[i] for i in index.intersects(square.boundingBox())] if index is not None else buffers
    parts = [g.intersection(square) for g in candidates if g.boundingBox().intersects(square.boundingBox())]
    parts = [g for g in parts if not g.isEmpty() and g.area() > 0]
    result = QgsGeometry.unaryUnion(parts)
    if result.isEmpty():
        raise ValueError('Nie udało się wyznaczyć obszaru kafla')
    return result


def raster_aoi_mask(tile, aoi):
    """Rasterize once per request; also skip thin edge tiles with no requested cell centres."""
    expected = (tile.bbox[0], tile.resolution, 0, tile.bbox[3], 0, -tile.resolution)
    mask_ds = gdal.GetDriverByName('MEM').Create('', tile.pixels, tile.pixels, 1, gdal.GDT_Byte)
    mask_ds.SetGeoTransform(expected)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(2180)
    mask_ds.SetProjection(srs.ExportToWkt())
    vector = ogr.GetDriverByName('Memory').CreateDataSource('')
    layer = vector.CreateLayer('aoi', srs, ogr.wkbUnknown)
    feat = ogr.Feature(layer.GetLayerDefn())
    feat.SetGeometry(ogr.CreateGeometryFromWkb(bytes(aoi.asWkb())))
    layer.CreateFeature(feat)
    if gdal.RasterizeLayer(mask_ds, [1], layer, burn_values=[1]) != 0:
        raise ValueError('Nie udało się przygotować maski obszaru')
    return mask_ds.ReadAsArray().astype(bool)


def inspect_raster(path, tile, aoi, signature_required=False, mask=None):
    # GDAL error mode remains unchanged for the QGIS host process.
    ds = gdal.Open(str(path), gdal.GA_ReadOnly)
    if ds is None:
        raise ValueError('Nieprawidłowy lub niekompletny raster')
    if (ds.RasterXSize, ds.RasterYSize, ds.RasterCount) != (tile.pixels, tile.pixels, 1):
        raise ValueError('Wymiary rastra inne niż zamówione')
    expected = (tile.bbox[0], tile.resolution, 0, tile.bbox[3], 0, -tile.resolution)
    if any(abs(a - b) > 0.001 for a, b in zip(ds.GetGeoTransform(), expected)):
        raise ValueError('Błędne położenie albo rozdzielczość rastra')
    if signature_required and ds.GetMetadataItem('REQUEST_SIGNATURE') != tile.signature:
        raise ValueError('Plik bez zgodnej sygnatury wtyczki; zachowano istniejący plik')
    band = ds.GetRasterBand(1)
    values = band.ReadAsArray()
    if values is None:
        raise ValueError('Nie udało się odczytać pikseli')
    missing = ~np.isfinite(values)
    nodata = band.GetNoDataValue()
    if nodata is not None and math.isfinite(nodata):
        missing |= values == nodata
    del values
    # Count only pixels with centres inside the requested buffer, not outside edge tiles.
    if mask is None:
        mask = raster_aoi_mask(tile, aoi)
    requested = int(np.count_nonzero(mask))
    gap_mask = (missing & mask).astype(np.uint8)
    missing_count = int(np.count_nonzero(gap_mask))
    return {'requested_cells': requested, 'nodata_cells': missing_count,
            'coverage_percent': round(100 * (requested - missing_count) / requested, 4) if requested else None}, gap_mask


def save_geotiff(source, target, tile):
    output = gdal.Translate(str(target), str(source), format='GTiff', outputType=gdal.GDT_Float32,
                            outputSRS='EPSG:2180', creationOptions=['COMPRESS=DEFLATE', 'PREDICTOR=3', 'TILED=YES', 'NUM_THREADS=1'])
    if output is None:
        raise ValueError('Konwersja ASCII Grid → GeoTIFF nie powiodła się')
    # WCS ASCII may differ from the validated request grid by sub-millimetre roundoff.
    # Store the exact requested grid so adjacent tiles have no artificial numerical gaps.
    output.SetGeoTransform((tile.bbox[0], tile.resolution, 0, tile.bbox[3], 0, -tile.resolution))
    output.SetMetadataItem('REQUEST_SIGNATURE', tile.signature)
    output.SetMetadataItem('SOURCE_URL', tile.url)
    output.SetMetadataItem('COVERAGE', tile.coverage)
    output.SetMetadataItem('RESOURCE', tile.resource)
    output.SetMetadataItem('HEIGHT_SYSTEM', tile.height)
    output.SetMetadataItem('NATIVE_RESOLUTION', str(tile.resolution))
    output.SetMetadataItem('PLUGIN_VERSION', VERSION)
    output.FlushCache()
    output = None


def save_gap_mask(path, mask, tile):
    ds = gdal.GetDriverByName('GTiff').Create(
        str(path), tile.pixels, tile.pixels, 1, gdal.GDT_Byte, options=['COMPRESS=DEFLATE', 'TILED=YES'])
    if ds is None:
        raise ValueError('Nie udało się zapisać maski braków')
    ds.SetGeoTransform((tile.bbox[0], tile.resolution, 0, tile.bbox[3], 0, -tile.resolution))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(2180)
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).WriteArray(mask)
    ds.GetRasterBand(1).SetNoDataValue(0)
    ds = None


def feature_geojson(geom, context, properties):
    geom = QgsGeometry(geom)
    transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:2180'),
                                       QgsCoordinateReferenceSystem('EPSG:4326'), context)
    geom.transform(transform)
    return {'type': 'Feature', 'geometry': json.loads(geom.asJson(8)), 'properties': properties}


def atomic_json(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)
