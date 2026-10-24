"""Classify a preview with optional BDOT layers. No invented obstacle heights."""
import math

import numpy as np
from osgeo import gdal, ogr
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeatureRequest,
                       QgsGeometry, QgsRectangle, QgsWkbTypes)

from .core import check_cancel


def scene_context(contexts, transform_context, grid, turbine, radius, rows, cols,
                  ground, ground_valid, surface, surface_valid, event):
    from .atlas import srs2180
    forest = np.zeros((len(rows), len(cols)), np.uint8)
    trees, summaries = [], []
    target = QgsCoordinateReferenceSystem('EPSG:2180')
    bounds = QgsRectangle(turbine['x'] - radius, turbine['y'] - radius,
                          turbine['x'] + radius, turbine['y'] + radius)
    for role, (source, crs) in contexts.items():
        check_cancel(event)
        forward = QgsCoordinateTransform(crs, target, transform_context)
        backward = QgsCoordinateTransform(target, crs, transform_context)
        request = QgsFeatureRequest().setFilterRect(backward.transformBoundingBox(bounds))
        info = dict(role=role, features=0, skipped=0, truncated=False,
                    method='BDOT: klasyfikacja pokrycia; wysokości z NMT/NMPT')
        vector = ogr.GetDriverByName('Memory').CreateDataSource('')
        polygons = vector.CreateLayer('forest', srs2180(), ogr.wkbUnknown)
        for feature in source.getFeatures(request):
            check_cancel(event)
            if info['features'] + info['skipped'] >= (20000 if role == 'lasy' else 2000):
                info['truncated'] = True
                break
            geometry = QgsGeometry(feature.geometry())
            if geometry.isEmpty():
                info['skipped'] += 1
                continue
            geometry.transform(forward)
            if role == 'lasy' and QgsWkbTypes.geometryType(geometry.wkbType()) == QgsWkbTypes.PolygonGeometry:
                output = ogr.Feature(polygons.GetLayerDefn())
                output.SetGeometry(ogr.CreateGeometryFromWkb(bytes(geometry.asWkb())))
                polygons.CreateFeature(output)
                info['features'] += 1
            elif role == 'drzewa' and QgsWkbTypes.geometryType(geometry.wkbType()) == QgsWkbTypes.PointGeometry:
                for point in geometry.asMultiPoint() if geometry.isMultipart() else [geometry.asPoint()]:
                    row = math.floor((grid.ymax - point.y()) / grid.step)
                    col = math.floor((point.x() - grid.xmin) / grid.step)
                    if (point.x() - turbine['x']) ** 2 + (point.y() - turbine['y']) ** 2 > radius ** 2 or not (
                            0 <= row < grid.height and 0 <= col < grid.width and ground_valid[row, col] and surface_valid[row, col]):
                        info['skipped'] += 1
                        continue
                    height = float(surface[row, col] - ground[row, col])
                    if not math.isfinite(height) or not 2 <= height <= 80 or len(trees) >= 2000:
                        info['skipped'] += 1
                        if len(trees) >= 2000:
                            info['truncated'] = True
                        continue
                    trees.append(dict(x=point.x() - turbine['x'], y=point.y() - turbine['y'],
                                      ground=float(ground[row, col]), height=height))
                    info['features'] += 1
            else:
                info['skipped'] += 1
        if role == 'lasy' and info['features']:
            step = grid.step * (int(cols[1] - cols[0]) if len(cols) > 1 else 1)
            raster = gdal.GetDriverByName('MEM').Create('', len(cols), len(rows), 1, gdal.GDT_Byte)
            raster.SetGeoTransform((grid.xmin + (int(cols[0]) + .5) * grid.step - step / 2, step, 0,
                                    grid.ymax - (int(rows[0]) + .5) * grid.step + step / 2, 0, -step))
            raster.SetProjection(srs2180().ExportToWkt())
            if gdal.RasterizeLayer(raster, [1], polygons, burn_values=[1]) != 0:
                raise ValueError('Nie udało się przygotować pokrycia lasów dla sceny')
            forest = raster.ReadAsArray()
            raster = None
        vector = None
        summaries.append(info)
    return forest.tolist(), trees, summaries
