"""Optional project context: sampled road segments, building exteriors and receivers."""
from collections import OrderedDict
import csv
from itertools import chain
import math

import numpy as np
from osgeo import gdal, ogr
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeatureRequest,
                       QgsGeometry, QgsPointXY, QgsRectangle, QgsWkbTypes)

from .atlas import NOCOUNT, srs2180
from .core import check_cancel


class Sampler:
    def __init__(self, paths):
        self.ds = {name: gdal.Open(paths[name]) for name in ['count', 'hub', 'quality']}
        self.gt = self.ds['count'].GetGeoTransform()
        self.cache = OrderedDict()

    def close(self):
        self.cache.clear()
        self.ds.clear()

    def values(self, points):
        rows = []
        for point in points:
            col, row = math.floor((point.x() - self.gt[0]) / self.gt[1]), math.floor((point.y() - self.gt[3]) / self.gt[5])
            reference = self.ds['count']
            if not 0 <= col < reference.RasterXSize or not 0 <= row < reference.RasterYSize:
                continue
            key = col // 256, row // 256
            if key not in self.cache:
                x, y = key[0] * 256, key[1] * 256
                width, height = min(256, reference.RasterXSize - x), min(256, reference.RasterYSize - y)
                self.cache[key] = {name: ds.GetRasterBand(1).ReadAsArray(x, y, width, height) for name, ds in self.ds.items()}
                if len(self.cache) > 32:
                    self.cache.popitem(last=False)
            self.cache.move_to_end(key)
            values = self.cache[key]
            count = int(values['count'][row % 256, col % 256])
            if count != NOCOUNT:
                rows.append((count, int(values['hub'][row % 256, col % 256]), int(values['quality'][row % 256, col % 256])))
        return rows


def point_samples(geometry, step):
    kind = QgsWkbTypes.geometryType(geometry.wkbType())
    if kind == QgsWkbTypes.PointGeometry:
        return geometry.asMultiPoint() if geometry.isMultipart() else [geometry.asPoint()]
    line = geometry
    if kind == QgsWkbTypes.PolygonGeometry:
        line = geometry.buffer(2, 4).convertToType(QgsWkbTypes.LineGeometry, True)
    parts = line.asGeometryCollection() if line.isMultipart() else [line]
    points = []
    for part in parts:
        length = part.length()
        if length <= 0:
            continue
        count = min(256, max(2, math.ceil(length / step)))
        for number in range(count):
            point = part.interpolate((number + 0.5) * length / count)
            if not point.isEmpty():
                points.append(point.asPoint())
    return points


def road_segments(geometry, length=50):
    parts = geometry.asGeometryCollection() if geometry.isMultipart() else [geometry]
    for part in parts:
        vertices = part.asPolyline()
        for a, b in zip(vertices[:-1], vertices[1:]):
            distance = math.hypot(b.x() - a.x(), b.y() - a.y())
            count = max(1, math.ceil(distance / length))
            for number in range(count):
                p = QgsPointXY(a.x() + (b.x() - a.x()) * number / count, a.y() + (b.y() - a.y()) * number / count)
                q = QgsPointXY(a.x() + (b.x() - a.x()) * (number + 1) / count, a.y() + (b.y() - a.y()) * (number + 1) / count)
                yield QgsGeometry.fromPolylineXY([p, q])


def write_context(folder, products, turbines, contexts, context, event):
    path = folder / 'atlas.gpkg'
    dataset = ogr.GetDriverByName('GPKG').CreateDataSource(str(path))
    if dataset is None:
        raise ValueError('Nie można utworzyć atlas.gpkg')
    srs = srs2180()
    summary = []
    fields = [('source_id', ogr.OFTString), ('model', ogr.OFTString), ('probki', ogr.OFTInteger),
              ('widoczne_pct', ogr.OFTReal), ('niepewne_pct', ogr.OFTReal), ('turbin_max', ogr.OFTInteger),
              ('piast_max', ogr.OFTInteger), ('metoda', ogr.OFTString)]

    def layer(name, kind, extra_fields):
        result = dataset.CreateLayer(name, srs, kind)
        for key, dtype in extra_fields:
            result.CreateField(ogr.FieldDefn(key, dtype))
        return result

    def add(target, geometry, values):
        feature = ogr.Feature(target.GetLayerDefn())
        for key, value in values.items():
            feature.SetField(key, value)
        geom = ogr.CreateGeometryFromWkb(bytes(geometry.asWkb()))
        if target.GetGeomType() == ogr.wkbMultiPolygon:
            geom = ogr.ForceToMultiPolygon(geom)
        elif target.GetGeomType() == ogr.wkbMultiPoint:
            geom = ogr.ForceToMultiPoint(geom)
        feature.SetGeometry(geom)
        if target.CreateFeature(feature) != 0:
            raise ValueError('Błąd zapisu elementu atlasu')

    try:
        target = layer('turbiny', ogr.wkbPoint, [('source_id', ogr.OFTString), ('piasta_m', ogr.OFTReal), ('srednica_m', ogr.OFTReal)])
        for turbine in turbines:
            add(target, QgsGeometry.fromPointXY(QgsPointXY(turbine['x'], turbine['y'])),
                dict(source_id=turbine['id'], piasta_m=turbine['hub'], srednica_m=turbine['diameter']))
        with (folder / 'ekspozycja.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, [name for name, _ in fields] + ['rola'], delimiter=';')
            writer.writeheader()
            for product in products:
                check_cancel(event)
                resource = product['resource']
                circles = layer('kola_' + resource, ogr.wkbPolygon, [('source_id', ogr.OFTString), ('promien_m', ogr.OFTReal)])
                for turbine in turbines:
                    add(circles, QgsGeometry.fromPointXY(QgsPointXY(turbine['x'], turbine['y'])).buffer(product['radius'], 128),
                        dict(source_id=turbine['id'], promien_m=product['radius']))
                sampler = Sampler(product['paths'])
                try:
                    for role, item in contexts.items():
                        source, crs = item
                        forward = QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem('EPSG:2180'), context)
                        reverse = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:2180'), crs, context)
                        rectangle = QgsRectangle(*product['bounds'])
                        request = QgsFeatureRequest().setFilterRect(reverse.transformBoundingBox(rectangle))
                        iterator = source.getFeatures(request)
                        first = next(iterator, None)
                        kind = QgsWkbTypes.geometryType(first.geometry().wkbType()) if first else QgsWkbTypes.PointGeometry
                        ogr_kind = ogr.wkbMultiPoint if kind == QgsWkbTypes.PointGeometry else ogr.wkbMultiPolygon if kind == QgsWkbTypes.PolygonGeometry else ogr.wkbLineString
                        target = layer(role + '_' + resource, ogr_kind, fields)
                        target.StartTransaction()
                        processed, truncated = 0, False
                        for feature in chain([first] if first else [], iterator):
                            check_cancel(event)
                            geom = QgsGeometry(feature.geometry())
                            if geom.isEmpty():
                                continue
                            geom.transform(forward)
                            if not geom.isGeosValid():
                                geom = geom.makeValid()
                            segments = road_segments(geom) if role == 'drogi' else [geom]
                            for geometry in segments:
                                if processed >= 20000:
                                    truncated = True
                                    break
                                points = point_samples(geometry, max(product['resolution'], 10))
                                values = sampler.values(points)
                                if not values:
                                    continue
                                array = np.asarray(values)
                                row = dict(source_id=str(feature.id()), model=resource, probki=len(values),
                                           widoczne_pct=round(100 * float((array[:, 0] > 0).mean()), 2),
                                           niepewne_pct=round(100 * float((array[:, 2] >= 2).mean()), 2),
                                           turbin_max=int(array[:, 0].max()), piast_max=int(array[:, 1].max()),
                                           metoda='obrys zewnętrzny +2 m' if kind == QgsWkbTypes.PolygonGeometry else 'próbki linii / punkt')
                                add(target, geometry, row)
                                writer.writerow(dict(row, rola=role))
                                processed += 1
                            if truncated:
                                break
                        target.CommitTransaction()
                        summary.append(dict(model=resource, role=role, features=processed, truncated=truncated,
                                            sample_spacing_m=max(product['resolution'], 10)))
                finally:
                    sampler.close()
    finally:
        dataset = None
    return str(path), summary
