"""Classify a preview with optional BDOT layers. No invented obstacle heights."""
import math

import numpy as np
from osgeo import gdal, ogr
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeatureRequest,
                       QgsGeometry, QgsRectangle, QgsWkbTypes, QgsTessellator)

from .core import check_cancel


def building_preview(geometry, grid, turbine, radius, ground, ground_valid, surface, surface_valid):
    """Bounded flat-roof prism from a real footprint and measured model heights."""
    from .atlas import srs2180
    bounds = geometry.boundingBox()
    if any((x-turbine['x'])**2 + (y-turbine['y'])**2 > radius**2
           for x in (bounds.xMinimum(), bounds.xMaximum()) for y in (bounds.yMinimum(), bounds.yMaximum())):
        return None
    x0, x1 = math.floor((bounds.xMinimum()-grid.xmin)/grid.step), math.ceil((bounds.xMaximum()-grid.xmin)/grid.step)
    y0, y1 = math.floor((grid.ymax-bounds.yMaximum())/grid.step), math.ceil((grid.ymax-bounds.yMinimum())/grid.step)
    if x0 < 0 or y0 < 0 or x1 > grid.width or y1 > grid.height or x1 <= x0 or y1 <= y0:
        return None
    stride = max(1, math.ceil(max(x1-x0, y1-y0)/256))
    ys, xs = np.arange(y0, y1, stride), np.arange(x0, x1, stride)
    vector = ogr.GetDriverByName('Memory').CreateDataSource('')
    layer = vector.CreateLayer('footprint', srs2180(), ogr.wkbUnknown)
    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetGeometry(ogr.CreateGeometryFromWkb(bytes(geometry.asWkb())))
    layer.CreateFeature(feature)
    raster = gdal.GetDriverByName('MEM').Create('', len(xs), len(ys), 1, gdal.GDT_Byte)
    step = grid.step*stride
    raster.SetGeoTransform((grid.xmin+(x0+.5)*grid.step-step/2, step, 0,
                            grid.ymax-(y0+.5)*grid.step+step/2, 0, -step))
    raster.SetProjection(srs2180().ExportToWkt())
    if gdal.RasterizeLayer(raster, [1], layer, burn_values=[1]) != 0:
        return None
    mask = raster.ReadAsArray() != 0
    good = mask & ground_valid[np.ix_(ys, xs)] & surface_valid[np.ix_(ys, xs)]
    if not mask.any() or good.sum() < .8*mask.sum():
        return None
    terrain, cover = ground[np.ix_(ys, xs)][good], surface[np.ix_(ys, xs)][good]
    base, roof = float(np.min(terrain)), float(np.max(cover))
    if not math.isfinite(base+roof) or not 2 <= roof-float(np.median(terrain)) <= 150:
        return None
    local = QgsGeometry(geometry)
    local.translate(-turbine['x'], -turbine['y'])
    local.convertToStraightSegment()
    rings = [[[point.x(), point.y()] for point in ring] for ring in local.asPolygon()]
    if not rings or sum(len(ring) for ring in rings) > 512:
        return None
    tessellator = QgsTessellator(0, 0, False, False, False, True)
    tessellator.addPolygon(local.constGet(), 0)
    vertices = tessellator.data()
    if not vertices or len(vertices) % 9 or len(vertices) > 512*9:
        return None
    triangles = [[[float(vertices[i+j]), float(-vertices[i+j+2])] for j in (0, 3, 6)]
                 for i in range(0, len(vertices), 9)]
    return dict(rings=rings, roof_triangles=triangles, ground=base, roof=roof,
                height=roof-base, method='obrys budynku; płaski dach na maksimum NMPT, grunt minimum NMT')


def scene_context(contexts, transform_context, grid, turbine, radius, rows, cols,
                  ground, ground_valid, surface, surface_valid, event):
    from .atlas import srs2180
    forest = np.zeros((len(rows), len(cols)), np.uint8)
    trees, buildings, summaries = [], [], []
    target = QgsCoordinateReferenceSystem('EPSG:2180')
    bounds = QgsRectangle(turbine['x'] - radius, turbine['y'] - radius,
                          turbine['x'] + radius, turbine['y'] + radius)
    for role, (source, crs) in contexts.items():
        check_cancel(event)
        forward = QgsCoordinateTransform(crs, target, transform_context)
        backward = QgsCoordinateTransform(target, crs, transform_context)
        request = QgsFeatureRequest().setFilterRect(backward.transformBoundingBox(bounds))
        info = dict(role=role, features=0, skipped=0, truncated=False,
                    method='obrysy budynków: uproszczone bryły z wysokości NMT/NMPT' if role == 'budynki_3d' else
                    'BDOT: klasyfikacja pokrycia; wysokości z NMT/NMPT')
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
            elif role == 'budynki_3d' and QgsWkbTypes.geometryType(geometry.wkbType()) == QgsWkbTypes.PolygonGeometry:
                if len(buildings) >= 500:
                    info['truncated'] = True
                    break
                if not geometry.isGeosValid():
                    info['skipped'] += 1
                    continue
                parts = geometry.asGeometryCollection() if geometry.isMultipart() else [geometry]
                accepted = False
                for part in parts:
                    check_cancel(event)
                    if len(buildings) >= 500:
                        info['truncated'] = True
                        break
                    item = building_preview(part, grid, turbine, radius, ground, ground_valid, surface, surface_valid)
                    if item:
                        buildings.append(item)
                        accepted = True
                info['features' if accepted else 'skipped'] += 1
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
    if 'lasy' in contexts and 'drzewa' not in contexts:
        # Illustrative samples inside actual forest polygons, not detected individual trees.
        spacing = max(1, math.ceil(8/(grid.step*(int(cols[1]-cols[0]) if len(cols) > 1 else 1))))
        check_cancel(event)
        ys, xs = rows[::spacing], cols[::spacing]
        gx = grid.xmin+(xs+.5)*grid.step-turbine['x']
        gy = grid.ymax-(ys+.5)*grid.step-turbine['y']
        heights = surface[np.ix_(ys, xs)]-ground[np.ix_(ys, xs)]
        mask = (forest[::spacing, ::spacing] != 0) & ground_valid[np.ix_(ys, xs)] & surface_valid[np.ix_(ys, xs)]
        mask &= (gy[:, None]**2 + gx[None, :]**2 <= radius**2) & np.isfinite(heights) & (heights >= 2) & (heights <= 80)
        candidates = np.flatnonzero(mask)
        indices = candidates[np.linspace(0, len(candidates)-1, min(2000, len(candidates)), dtype=int)] if candidates.size else []
        for index in indices:
            r, c = divmod(int(index), len(xs))
            trees.append(dict(x=float(gx[c]), y=float(gy[r]), ground=float(ground[ys[r], xs[c]]),
                              height=float(heights[r, c]), source='forest_sample'))
        summaries.append(dict(role='korony_lasu', features=len(trees), skipped=0, truncated=len(candidates) > 2000,
                              method='ilustracyjne próbki wewnątrz lasów; wysokości NMPT−NMT; nie inwentaryzacja drzew'))
    return forest.tolist(), trees, buildings, summaries
