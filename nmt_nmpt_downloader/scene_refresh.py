"""Rebuild views from completed analysis rasters; never download or rerun viewsheds."""
import copy
from pathlib import Path

import numpy as np
from osgeo import gdal

from .atlas import Grid, NODATA
from .atlas_details import write_details
from .core import VERSION, atomic_json, check_cancel


def refresh_scenes(report, view_options, event, context=None, scene_contexts=None, notify=lambda _: None):
    result = copy.deepcopy(report)
    if not result.get('products') or not result.get('turbines'):
        raise ValueError('Wczytaj report.json zakończonego atlasu')
    number = int(view_options.get('view_turbine', 1)) - 1
    if not 0 <= number < len(result['turbines']):
        raise ValueError('Numer turbiny do sceny jest poza zestawem z raportu')
    turbine = result['turbines'][number]
    options = dict(result['options'], **{key: value for key, value in view_options.items()
                                         if key.startswith('scene_') or key in ('view_turbine', 'view_azimuth')})
    options['demo'] = bool(result['options'].get('demo'))
    details = []
    for product in result['products']:
        check_cancel(event)
        resource = product['resource']
        notify(resource + ': odświeżanie 3D z zapisanych rastrów; bez pobierania i obliczeń widoczności')
        grid = Grid.around([turbine], product['radius'], product['resolution'])
        root = Path(product['paths']['count']).parent
        paths = dict(ground=root / 'terrain.tif', surface=Path(product['paths'].get('elevation', root / 'terrain.tif')))
        arrays, valid = {}, {}
        for role, path in paths.items():
            if not path.is_file():
                raise ValueError('Brak modelu do odświeżenia sceny: ' + str(path))
            dataset = gdal.Open(str(path))
            if dataset is None:
                raise ValueError('Nie można odczytać modelu: ' + str(path))
            gt = dataset.GetGeoTransform()
            xoff = round((grid.xmin - gt[0]) / gt[1])
            yoff = round((gt[3] - grid.ymax) / -gt[5])
            if xoff < 0 or yoff < 0 or xoff+grid.width > dataset.RasterXSize or yoff+grid.height > dataset.RasterYSize:
                raise ValueError('Zapisany model nie obejmuje koła tej turbiny')
            band = dataset.GetRasterBand(1)
            array = band.ReadAsArray(xoff, yoff, grid.width, grid.height)
            mask = band.GetMaskBand().ReadAsArray(xoff, yoff, grid.width, grid.height)
            arrays[role] = array
            valid[role] = (mask != 0) & np.isfinite(array) & (array != NODATA)
            band, dataset = None, None
        source = next((t for t in product.get('turbines', []) if str(t['id']) == str(turbine['id'])), {})
        height = source.get('ground_z_m')
        if height is None:
            row = min(grid.height-1, max(0, int((grid.ymax-turbine['y'])/grid.step)))
            col = min(grid.width-1, max(0, int((turbine['x']-grid.xmin)/grid.step)))
            height = float(arrays['ground'][row, col]) if valid['ground'][row, col] else float('nan')
        details.append(write_details(result['report_dir'], product, grid, turbine, arrays['ground'], valid['ground'],
                                     arrays['surface'], valid['surface'], height, options, event, scene_contexts, context))
    result['details'], result['scene_view_options'] = details, view_options
    result['scene_version'] = VERSION
    result.pop('scene_texture_error', None)
    result.pop('presentation_error', None)
    atomic_json(Path(result['report_dir']) / 'report.json', result)
    return result
