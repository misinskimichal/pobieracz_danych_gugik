"""Small analytical prototypes for correctly registered, metre-based height rasters.

Run with the GDAL/NumPy Python shipped with QGIS. These are analytical examples,
not additional features of plugin 1.1.0. Output files should use a separate folder.
"""
from pathlib import Path
import csv
import math

import numpy as np
from osgeo import gdal, osr


def open_metric_dem(path):
    ds = gdal.Open(str(path), gdal.GA_ReadOnly)
    if ds is None or ds.RasterCount != 1:
        raise ValueError('Oczekiwano jednokanałowego rastra wysokości')
    crs = osr.SpatialReference()
    if crs.ImportFromWkt(ds.GetProjection()) != 0 or not crs.IsProjected():
        raise ValueError('Oczekiwano poprawnego metrycznego CRS')
    if abs(crs.GetLinearUnits() - 1.0) > 1e-9:
        raise ValueError('Jednostką poziomą muszą być metry')
    gt = ds.GetGeoTransform()
    if abs(gt[2]) > 1e-9 or abs(gt[4]) > 1e-9 or gt[1] <= 0 or gt[5] >= 0:
        raise ValueError('Przykład wymaga regularnej siatki north-up')
    return ds


def heights_and_valid(ds):
    band = ds.GetRasterBand(1)
    values = band.ReadAsArray().astype(np.float32)
    valid = np.isfinite(values)
    nodata = band.GetNoDataValue()
    if nodata is not None and math.isfinite(nodata):
        valid &= values != nodata
    return values, valid


def write_float(path, reference, values, valid, product):
    target = gdal.GetDriverByName('GTiff').Create(
        str(path), reference.RasterXSize, reference.RasterYSize, 1, gdal.GDT_Float32,
        options=['TILED=YES', 'COMPRESS=DEFLATE', 'PREDICTOR=3'])
    if target is None:
        raise RuntimeError('Nie można utworzyć pliku wynikowego')
    target.SetGeoTransform(reference.GetGeoTransform())
    target.SetProjection(reference.GetProjection())
    target.SetMetadataItem('SOURCE_HEIGHT_SYSTEM', reference.GetMetadataItem('HEIGHT_SYSTEM') or '')
    target.SetMetadataItem('HEIGHT_REFERENCE', 'relative_above_ground')
    target.SetMetadataItem('PRODUCT', product)
    target.GetRasterBand(1).SetNoDataValue(-9999)
    target.GetRasterBand(1).WriteArray(np.where(valid, values, -9999).astype(np.float32))
    target.FlushCache()
    target = None


def make_ndsm(dtm_path, dsm_path, output):
    """DSM - DTM on the DTM grid; no implicit vertical-datum conversion."""
    dtm, dsm = open_metric_dem(dtm_path), open_metric_dem(dsm_path)
    height = dtm.GetMetadataItem('HEIGHT_SYSTEM')
    if not height or height != dsm.GetMetadataItem('HEIGHT_SYSTEM'):
        raise ValueError('Potwierdź i oznacz zgodny układ wysokościowy obu modeli')
    gt = dtm.GetGeoTransform()
    bounds = [gt[0], gt[3] + gt[5] * dtm.RasterYSize,
              gt[0] + gt[1] * dtm.RasterXSize, gt[3]]
    aligned = gdal.Warp('', dsm, format='MEM', dstSRS=dtm.GetProjection(),
                        outputBounds=bounds, width=dtm.RasterXSize, height=dtm.RasterYSize,
                        resampleAlg='bilinear', dstNodata=-9999, outputType=gdal.GDT_Float32)
    if aligned is None:
        raise RuntimeError('Nie udało się dopasować siatek')
    ground, valid_ground = heights_and_valid(dtm)
    surface, valid_surface = heights_and_valid(aligned)
    valid = valid_ground & valid_surface
    difference = surface - ground
    # Negative differences are retained for quality control rather than hidden.
    write_float(output, dtm, difference, valid, 'nDSM: NMPT-NMT')
    return {'valid_cells': int(valid.sum()), 'negative_cells': int(((difference < 0) & valid).sum())}


def terrain_slope(dtm_path, output):
    """Slope in degrees; not an assessment of soil bearing capacity."""
    ds = open_metric_dem(dtm_path)
    result = gdal.DEMProcessing(str(output), ds, 'slope', format='GTiff', scale=1.0,
                                computeEdges=True, creationOptions=['COMPRESS=DEFLATE'])
    if result is None:
        raise RuntimeError('Nie udało się obliczyć nachylenia')
    result = None


def terrain_viewshed(dtm_path, output, x, y, observer_agl=120, target_agl=1.7, radius=20000):
    """Terrain-only visibility. Buildings, tree occlusion and weather are not modeled."""
    ds = open_metric_dem(dtm_path)
    # For long distances the input must cover the entire analysis neighborhood.
    result = gdal.ViewshedGenerate(
        ds.GetRasterBand(1), 'GTiff', str(output), ['COMPRESS=DEFLATE'],
        float(x), float(y), float(observer_agl), float(target_agl),
        255, 0, 0, 0, 0.87, gdal.GVM_Edge, float(radius))
    if result is None:
        raise RuntimeError('Nie udało się obliczyć widoczności')
    result = None


def radio_clearance(profile_csv, frequency_ghz=3.5, mast_a_m=30, mast_b_m=30, effective_earth_factor=4/3):
    """Geometric line/Fresnel clearance, not a complete radio propagation model.

    CSV columns: s_m, dtm_m, dsm_m; heights in one vertical datum, no missing values.
    """
    with Path(profile_csv).open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    s = np.array([float(row['s_m']) for row in rows])
    ground = np.array([float(row['dtm_m']) for row in rows])
    surface = np.array([float(row['dsm_m']) for row in rows])
    if len(s) < 3 or not np.all(np.isfinite([s, ground, surface])) or s[0] != 0 or np.any(np.diff(s) <= 0):
        raise ValueError('Profil musi być kompletny, rosnący i zaczynać się od 0 m')
    if frequency_ghz <= 0 or effective_earth_factor <= 0:
        raise ValueError('Częstotliwość i współczynnik Ziemi muszą być dodatnie')
    length = s[-1]
    z_a, z_b = ground[0] + mast_a_m, ground[-1] + mast_b_m
    line = z_a + (z_b - z_a) * s / length
    wavelength = 299792458.0 / (frequency_ghz * 1e9)
    fresnel = np.sqrt(wavelength * s * (length - s) / length)
    earth_bulge = s * (length - s) / (2 * 6371000 * effective_earth_factor)
    reserve = line - (surface + earth_bulge + 0.6 * fresnel)
    return {'minimum_reserve_m': float(reserve.min()), 'sample_count': len(s),
            'all_sampled_points_clear': bool(np.all(reserve > 0))}


def make_terrain_mesh(dtm_path, output_vts, stride=4):
    """Requires pyvista (VTK); intentionally rejects holes rather than inventing elevations."""
    import pyvista as pv
    ds = open_metric_dem(dtm_path)
    z, valid = heights_and_valid(ds)
    if not np.all(valid[::stride, ::stride]):
        raise ValueError('Wybierz wycinek bez NoData lub zaplanuj jawne uzupełnienie dziur')
    gt = ds.GetGeoTransform()
    rows = np.arange(0, ds.RasterYSize, stride)
    cols = np.arange(0, ds.RasterXSize, stride)
    x, y = np.meshgrid(gt[0] + (cols + 0.5) * gt[1], gt[3] + (rows + 0.5) * gt[5])
    grid = pv.StructuredGrid(x, y, z[::stride, ::stride])
    grid.save(str(output_vts))
    return grid
