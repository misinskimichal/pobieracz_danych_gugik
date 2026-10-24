"""Bounded viewpoints and native-resolution detail windows; presentation only."""
import math
from pathlib import Path

import numpy as np

from .core import atomic_json, check_cancel


def view_points(options):
    points = options.get('scene_viewpoints') or []
    if len(points) > 12:
        raise ValueError(
            'Przygotuj do 12 punktów w jednym zestawie wizualizacji')
    output = []
    for index, point in enumerate(points):
        x, y = float(point['x']), float(point['y'])
        eye = float(point.get('eye', options.get('scene_eye', 1.7)))
        if not all(math.isfinite(value) for value in (x, y, eye)) or not .3 <= eye <= 100:
            raise ValueError(
                'Punkt wizualizacji musi mieć poprawne współrzędne i oko 0,3–100 m')
        output.append(dict(name=str(point.get('name')
                      or f'Punkt {index+1}')[:100], x=x, y=y, eye=eye))
    return output


def save_view_points(folder, points):
    path = Path(folder) / 'punkty_wizualizacji.geojson'
    atomic_json(path, dict(type='FeatureCollection', name='Punkty wizualizacji 3D',
                           crs=dict(type='name', properties=dict(
                               name='EPSG:2180')),
                           features=[dict(type='Feature', properties=dict(nazwa=p['name'], oko_m=p['eye']),
                                          geometry=dict(type='Point', coordinates=[p['x'], p['y']])) for p in points]))
    return str(path)


def default_point(options, grid, turbine, radius, ground, ground_valid, surface, surface_valid):
    camera = options.get('scene_observer')
    if camera:
        return dict(name='Wybrane miejsce', x=float(camera[0]), y=float(camera[1]), eye=float(options.get('scene_eye', 1.7)))
    for fraction in (.65, .4, .85):
        for offset in (0, 25, -25, 60, -60, 120, 180):
            angle = math.radians(
                float(options.get('view_azimuth', 225))+offset)
            x, y = turbine['x']+math.sin(angle)*radius * \
                fraction, turbine['y']+math.cos(angle)*radius*fraction
            row, col = int(
                (grid.ymax-y)/grid.step), int((x-grid.xmin)/grid.step)
            eye = float(options.get('scene_eye', 1.7))
            if (0 <= row < grid.height and 0 <= col < grid.width and ground_valid[row, col] and surface_valid[row, col]
                    and surface[row, col] <= ground[row, col]+eye+.02):
                return dict(name='Widok początkowy', x=x, y=y, eye=eye)
    return None


def detail_windows(points, grid, turbine, radius, rows, cols, ground, ground_valid,
                   surface, surface_valid, forest, buildings, detail_radius, event):
    """Edges align to coarse mesh vertices; no source upsampling and no NoData filling."""
    limit = max(30, min(400, float(detail_radius)))
    output = []
    for point in points:
        check_cancel(event)
        dx, dy = point['x']-turbine['x'], point['y']-turbine['y']
        item = dict(name=point['name'], point=[dx, dy],
                    eye=point['eye'], detail_radius=limit)
        col = math.floor((point['x']-grid.xmin)/grid.step)
        row = math.floor((grid.ymax-point['y'])/grid.step)
        if dx*dx+dy*dy >= radius*radius or not (0 <= row < grid.height and 0 <= col < grid.width):
            item['error'] = 'Punkt poza zakresem sceny; zwiększ promień sceny/analizy.'
        elif not ground_valid[row, col] or not surface_valid[row, col]:
            item['error'] = 'Brak poprawnego NMT/NMPT w miejscu obserwacji.'
        elif surface[row, col] > ground[row, col]+point['eye']+.1:
            item['error'] = 'Oko pod powierzchnią dachu lub korony; wybierz otwarte miejsce.'
        if item.get('error'):
            output.append(item)
            continue
        wanted = [row-limit/grid.step, row+limit/grid.step,
                  col-limit/grid.step, col+limit/grid.step]
        r0 = max(0, np.searchsorted(rows, wanted[0], side='right')-1)
        r1 = min(len(rows)-1, np.searchsorted(rows, wanted[1], side='left'))
        c0 = max(0, np.searchsorted(cols, wanted[2], side='right')-1)
        c1 = min(len(cols)-1, np.searchsorted(cols, wanted[3], side='left'))
        if r1 <= r0 or c1 <= c0:
            item['error'] = 'Za mały fragment poprawnego modelu wokół punktu.'
            output.append(item)
            continue
        step = max(1, math.ceil(max(rows[r1]-rows[r0], cols[c1]-cols[c0])/512))
        rr = np.unique(
            np.r_[np.arange(rows[r0], rows[r1], step), rows[r1]]).astype(int)
        cc = np.unique(
            np.r_[np.arange(cols[c0], cols[c1], step), cols[c1]]).astype(int)
        x = grid.xmin+(cc+.5)*grid.step-turbine['x']
        y = grid.ymax-(rr+.5)*grid.step-turbine['y']
        inside = y[:, None]**2+x[None, :]**2 <= radius**2
        valid_ground = ground_valid[np.ix_(rr, cc)] & inside
        valid = valid_ground & surface_valid[np.ix_(rr, cc)]

        def clean(array, good):
            return [[round(float(value), 2) if ok and np.isfinite(value) else None for value, ok in zip(line, mask)]
                    for line, mask in zip(array, good)]
        patch = dict(x=x.tolist(), y=y.tolist(), step_m=grid.step*step,
                     coarse=[int(r0), int(c0), int(r1), int(c1)],
                     ground=clean(ground[np.ix_(rr, cc)], valid_ground),
                     surface=clean(np.maximum(
                         ground[np.ix_(rr, cc)], surface[np.ix_(rr, cc)]), valid),
                     forest=forest[np.ix_(rr, cc)].tolist() if forest is not None else np.zeros(
                         valid.shape, np.uint8).tolist(),
                     building_mask=buildings[np.ix_(rr, cc)].tolist() if buildings is not None else np.zeros(valid.shape, np.uint8).tolist())
        item['patch'] = patch
        output.append(item)
    return output
