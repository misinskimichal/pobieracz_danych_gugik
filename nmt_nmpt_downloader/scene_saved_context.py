"""Retain actual exported context when reopening an atlas without its original project layers."""
import json
from pathlib import Path

import numpy as np


def building_mask(buildings, target):
    """Older scenes have real footprints but no separate surface replacement mask."""
    from osgeo import gdal, ogr
    from .atlas import srs2180
    if len(target['x']) < 2 or len(target['y']) < 2:
        return [[0] * len(target['x']) for _ in target['y']]
    dx, dy = target['x'][1] - target['x'][0], target['y'][0] - target['y'][1]
    raster = gdal.GetDriverByName('MEM').Create('', len(target['x']), len(target['y']), 1, gdal.GDT_Byte)
    raster.SetGeoTransform((target['x'][0] - dx / 2, dx, 0, target['y'][0] + dy / 2, 0, -dy))
    raster.SetProjection(srs2180().ExportToWkt())
    vector = ogr.GetDriverByName('Memory').CreateDataSource('')
    layer = vector.CreateLayer('footprints', srs2180(), ogr.wkbPolygon)
    for building in buildings:
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(ogr.CreateGeometryFromJson(json.dumps(dict(type='Polygon', coordinates=building['rings']))))
        layer.CreateFeature(feature)
    if buildings:
        gdal.RasterizeLayer(raster, [1], layer, burn_values=[1], options=['ALL_TOUCHED=TRUE'])
    return raster.ReadAsArray().tolist()


def read_scene_context(filename):
    try:
        with Path(filename).open(encoding='utf-8') as stream:
            for line in stream:
                if line.startswith('const scene='):
                    return json.loads(line[len('const scene='):].rstrip().removesuffix(';'))
    except (OSError, ValueError, TypeError):
        return None
    return None


def reuse_scene_context(current, previous, provided_roles=()):
    if not previous or any(previous.get(k) != current.get(k) for k in ('resource', 'origin', 'height_system')):
        return False
    if not previous.get('trees') and not previous.get('buildings'):
        return False
    provided_roles = set(provided_roles)
    trees = not provided_roles.intersection({'lasy', 'drzewa'}) and bool(previous.get('trees'))
    houses = 'budynki_3d' not in provided_roles and bool(previous.get('buildings'))
    if not trees and not houses:
        return False

    def resample(field, target):
        if not field or len(field) != len(previous['y']) or len(field[0]) != len(previous['x']):
            return [[0] * len(target['x']) for _ in target['y']]
        x, y = np.asarray(previous['x']), -np.asarray(previous['y'])
        xx, yy = np.asarray(target['x']), -np.asarray(target['y'])

        def nearest(axis, values):
            if len(axis) < 2:
                return np.zeros(len(values), int)
            i = np.clip(np.searchsorted(axis, values), 1, len(axis) - 1)
            return np.where(abs(values - axis[i - 1]) < abs(values - axis[i]), i - 1, i)
        cols, rows = nearest(x, xx), nearest(y, yy)
        values = np.asarray(field, np.uint8)[np.ix_(rows, cols)].copy()
        values[:, (xx < x[0]) | (xx > x[-1])] = 0
        values[(yy < y[0]) | (yy > y[-1]), :] = 0
        return values.tolist()

    if trees:
        current['trees'] = [tree for tree in previous.get('trees', []) if tree['x']**2 + tree['y']**2 <= current['radius']**2]
        current['forest'] = resample(previous.get('forest'), current)
    if houses:
        current['buildings'] = [building for building in previous.get('buildings', [])
                                if all(p[0]**2 + p[1]**2 <= current['radius']**2 for ring in building['rings'] for p in ring)]
        current['building_mask'] = resample(previous.get('building_mask'), current) if previous.get('building_mask') else building_mask(current['buildings'], current)
    for view in current.get('detail_views', []):
        patch = view.get('patch')
        if patch:
            if trees:
                patch['forest'] = resample(previous.get('forest'), patch)
            if houses:
                patch['building_mask'] = resample(previous.get('building_mask'), patch) if previous.get('building_mask') else building_mask(current['buildings'], patch)
    roles = ({'lasy', 'drzewa', 'korony_lasu'} if trees else set()) | ({'budynki_3d'} if houses else set())
    current['context_summary'] = [s for s in current.get('context_summary', []) if s['role'] not in roles] + [s for s in previous.get('context_summary', []) if s['role'] in roles]
    current['context_notes'] += ['Zachowano obiekty ostatniej zapisanej sceny dla brakujących warstw projektu. Maski podglądu przeliczono na bieżącą siatkę.']
    current['context_reused'] = True
    return True
