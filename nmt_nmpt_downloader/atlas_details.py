"""Worker-only radial results, elevation profiles and bounded browser 3D scenes."""
import html
import json
import math
from pathlib import Path

import numpy as np
from osgeo import ogr

from .core import check_cancel

EARTH_DIAMETER = 12756274.0  # 2 * GRS80 semi-major axis, as used by GDAL for EPSG:2180.
STATES = {0: 'zasłonięta', 1: 'widoczna', 2: 'brak rozstrzygnięcia', 3: 'oko pod powierzchnią'}


def ray_points(grid, turbine, radius, azimuth):
    """Cell-centre sampling along a bearing; bearings clockwise from grid north."""
    distance = np.linspace(0, radius, max(2, int(math.ceil(2 * radius / grid.step)) + 1))
    angle = math.radians(azimuth)
    x = turbine['x'] + distance * math.sin(angle)
    y = turbine['y'] + distance * math.cos(angle)
    cols = np.clip(((x - grid.xmin) / grid.step).astype(int), 0, grid.width - 1)
    rows = np.clip(((grid.ymax - y) / grid.step).astype(int), 0, grid.height - 1)
    return distance, x, y, rows, cols


class RayWriter:
    """Per-turbine states, never inferred from the cumulative count map."""
    def __init__(self, folder, spacing, event, limit=200000):
        self.path = Path(folder) / 'promienie.gpkg'
        self.ds = ogr.GetDriverByName('GPKG').CreateDataSource(str(self.path))
        self.spacing, self.event, self.limit = max(1, min(90, float(spacing))), event, limit
        self.summaries = []

    def add_model(self, resource):
        from .atlas import srs2180
        self.layer = self.ds.CreateLayer('promienie_' + resource, srs2180(), ogr.wkbLineString)
        for name, kind in [('turbina', ogr.OFTString), ('azymut', ogr.OFTReal), ('od_m', ogr.OFTReal),
                           ('do_m', ogr.OFTReal), ('piasta', ogr.OFTInteger), ('koniec', ogr.OFTInteger),
                           ('dolny', ogr.OFTInteger), ('opis', ogr.OFTString)]:
            self.layer.CreateField(ogr.FieldDefn(name, kind))
        self.summary = dict(model=resource, features=0, spacing_degrees=self.spacing, truncated=False)
        self.summaries.append(self.summary)

    def write(self, grid, turbine, radius, result):
        inside, visible, uncertain, quality = result
        self.layer.StartTransaction()
        try:
            for azimuth in np.arange(0, 360, self.spacing):
                check_cancel(self.event)
                distance, x, y, rows, cols = ray_points(grid, turbine, radius, azimuth)
                levels = []
                for v, u in zip(visible, uncertain):
                    state = np.where(u[rows, cols], 2, v[rows, cols].astype(np.uint8))
                    state[quality[rows, cols] == 4] = 3
                    state[~inside[rows, cols]] = 2
                    levels.append(state)
                states = np.stack(levels, axis=1)
                starts = np.r_[0, np.flatnonzero(np.any(states[1:] != states[:-1], axis=1)) + 1]
                for start, stop in zip(starts, np.r_[starts[1:], len(distance)]):
                    if self.summary['features'] >= self.limit:
                        self.summary['truncated'] = True
                        return
                    low = 0 if start == 0 else (distance[start - 1] + distance[start]) / 2
                    high = radius if stop == len(distance) else (distance[stop - 1] + distance[stop]) / 2
                    angle = math.radians(azimuth)
                    geometry = ogr.Geometry(ogr.wkbLineString)
                    for d in (low, high):
                        geometry.AddPoint_2D(turbine['x'] + d * math.sin(angle), turbine['y'] + d * math.cos(angle))
                    tip, hub, bottom = map(int, states[start])
                    feature = ogr.Feature(self.layer.GetLayerDefn())
                    for name, value in dict(turbina=str(turbine['id']), azymut=float(azimuth), od_m=float(low),
                                            do_m=float(high), piasta=hub, koniec=tip, dolny=bottom, opis=STATES[hub]).items():
                        feature.SetField(name, value)
                    feature.SetGeometry(geometry)
                    if self.layer.CreateFeature(feature) != 0:
                        raise ValueError('Nie można zapisać promieni widoczności')
                    self.summary['features'] += 1
        finally:
            self.layer.CommitTransaction()

    def close(self):
        self.layer = None
        self.ds = None


def profile_data(ground, ground_valid, surface, surface_valid, grid, turbine, radius, ground_z, options):
    azimuth = float(options.get('view_azimuth', 225)) % 360
    distance, x, y, rows, cols = ray_points(grid, turbine, radius, azimuth)
    # Plot observer -> turbine. Samples are read from the same analysis grid, not the 3D preview mesh.
    distance = radius - distance[::-1]
    terrain = ground[rows, cols][::-1].astype(float)
    cover = np.maximum(ground[rows, cols], surface[rows, cols])[::-1].astype(float)
    valid_ground = ground_valid[rows, cols][::-1]
    valid = (ground_valid[rows, cols] & surface_valid[rows, cols])[::-1]
    bulge = (6 / 7) * distance * (radius - distance) / EARTH_DIAMETER if options.get('curvature', True) else np.zeros_like(distance)
    terrain[~valid_ground] = np.nan
    cover[~valid] = np.nan
    eye_z = terrain[0] + options['eye']
    targets = [ground_z + turbine['hub'] + delta for delta in (turbine['diameter'] / 2, 0, -turbine['diameter'] / 2)]
    lines = [eye_z + (target - eye_z) * distance / radius for target in targets]
    occupied = bool(valid[0] and np.isfinite(eye_z) and cover[0] > eye_z)
    status = []
    for line in lines:
        clearance = line[1:-1] - (cover + bulge)[1:-1]
        status.append('oko pod powierzchnią' if occupied else 'brak danych' if not np.isfinite(eye_z) or not np.isfinite(ground_z)
                      or not valid.all() else 'zasłonięta' if np.any(clearance < -0.01) else 'widoczna')
    return dict(azimuth=azimuth, distance=distance, terrain=terrain, surface=cover, bulge=bulge,
                lines=lines, eye_z=eye_z, target_z=targets, status=status,
                observer_x=float(x[-1]), observer_y=float(y[-1]))


def profile_svg(data, resource, turbine, path):
    """Plain SVG, portable on QGIS Windows builds without matplotlib or a browser service."""
    width, height, left, top, plot_w, plot_h = 1200, 520, 82, 88, 1080, 320
    terrain, surface, distance = data['terrain'] + data['bulge'], data['surface'] + data['bulge'], data['distance']
    finite = np.concatenate([a[np.isfinite(a)] for a in [terrain, surface] + data['lines']])
    low, high = (float(finite.min()) - 8, float(finite.max()) + 12) if finite.size else (0, 100)
    high = max(high, low + 20)

    def sx(d): return left + d / distance[-1] * plot_w
    def sy(z): return top + (high - z) / (high - low) * plot_h

    def polyline(values):
        parts, current = [], []
        for d, z in zip(distance, values):
            if np.isfinite(z):
                current.append(f'{sx(d):.2f},{sy(z):.2f}')
            elif current:
                parts.append(' '.join(current))
                current = []
        if current:
            parts.append(' '.join(current))
        return parts

    title = html.escape(f'{resource} · turbina {turbine["id"]} · kierunek do obserwatora {data["azimuth"]:g}°')
    if data.get('demo'):
        title = 'DANE SYNTETYCZNE · ' + title
    output = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
              '<defs><linearGradient id="terrain" x1="0" y1="1" x2="0" y2="0"><stop stop-color="#20875a"/><stop offset=".5" stop-color="#e9d95c"/><stop offset="1" stop-color="#d44946"/></linearGradient></defs>',
              '<rect width="1200" height="520" fill="#f1f6f8"/>',
              f'<text x="{left}" y="34" font-family="sans-serif" font-size="23" fill="#153747">Przekrój terenu i linie widzenia</text>',
              f'<text x="{left}" y="60" font-family="sans-serif" font-size="15" fill="#526b76">{title}</text>']
    for fraction in np.linspace(0, 1, 5):
        z = low + fraction * (high - low)
        yy = sy(z)
        output += [f'<path d="M{left},{yy}h{plot_w}" stroke="#d4e0e5"/>',
                   f'<text x="{left-10}" y="{yy+5}" text-anchor="end" font-family="sans-serif" font-size="12">{z:.0f} m</text>']
    for points in polyline(terrain):
        first, last = points.split()[0].split(',')[0], points.split()[-1].split(',')[0]
        output.append(f'<polygon points="{first},{top+plot_h} {points} {last},{top+plot_h}" fill="url(#terrain)"/>')
    for points in polyline(surface):
        output.append(f'<polyline points="{points}" fill="none" stroke="#285549" stroke-width="2"/>')
    for index, (line, label, color) in enumerate(zip(data['lines'], ['Koniec łopaty', 'Piasta', 'Dolny zasięg'], ['#9674d4', '#ed5b75', '#dd9d28'])):
        for points in polyline(line):
            output.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2" stroke-dasharray="8 5"/>')
        output.append(f'<text x="{left + index*365}" y="475" font-family="sans-serif" font-size="14" fill="{color}">{label}: {html.escape(data["status"][index])}</text>')
    if np.isfinite(data['target_z'][1]):
        xx = sx(distance[-1])
        base_z = data['target_z'][1] - turbine['hub']
        output += [f'<path d="M{xx},{sy(base_z)}V{sy(data["target_z"][1])}" stroke="#153747" stroke-width="4"/>',
                   f'<path d="M{xx},{sy(data["target_z"][0])}V{sy(data["target_z"][2])}" stroke="#153747" stroke-width="2" stroke-dasharray="3 3"/>',
                   f'<circle cx="{xx}" cy="{sy(data["target_z"][1])}" r="5" fill="#ffffff" stroke="#153747"/>']
    if np.isfinite(data['eye_z']):
        output.append(f'<circle cx="{sx(0)}" cy="{sy(data["eye_z"])}" r="5" fill="#153747" stroke="#ffffff"/>')
    for fraction in np.linspace(0, 1, 6):
        d = fraction * distance[-1]
        output.append(f'<text x="{sx(d)}" y="{top+plot_h+24}" text-anchor="middle" font-family="sans-serif" font-size="12">{d/1000:.2f} km</text>')
    output += [f'<text x="{left}" y="450" font-family="sans-serif" font-size="13">Obserwator → turbina. Linia ciągła: powierzchnia modelu; przerwy: brak danych. Skale pionowa i pozioma są różne.</text>',
               '<text x="82" y="504" font-family="sans-serif" font-size="12">To profil jednej trasy; może różnić się przy granicy cienia od aproksymacji rastrowej GDAL. Korekta krzywizny zgodna z opcją analizy.</text></svg>']
    Path(path).write_text('\n'.join(output), encoding='utf-8')


def write_details(folder, spec, grid, turbine, ground, ground_valid, surface, surface_valid, ground_z, options, event):
    """A small visual preview for one chosen turbine; never reduces the analysis resolution."""
    check_cancel(event)
    folder = Path(folder)
    data = profile_data(ground, ground_valid, surface, surface_valid, grid, turbine, spec['radius'], ground_z, options)
    data['demo'] = bool(options.get('demo'))
    profile_path = folder / ('profil_' + spec['resource'] + '.svg')
    profile_svg(data, spec['resource'], turbine, profile_path)
    # <= 129x129 vertices. NaN gaps remain open; downsampling only affects this preview.
    stride = max(1, int(math.ceil(max(grid.width, grid.height) / 128)))
    rows, cols = np.arange(0, grid.height, stride), np.arange(0, grid.width, stride)
    gy, gx = np.meshgrid(rows, cols, indexing='ij')
    x = grid.xmin + (cols + .5) * grid.step - turbine['x']
    y = grid.ymax - (rows + .5) * grid.step - turbine['y']
    inside = y[:, None] ** 2 + x[None, :] ** 2 <= spec['radius'] ** 2
    valid = ground_valid[gy, gx] & surface_valid[gy, gx] & inside

    def clean(array, good):
        return [[round(float(v), 2) if ok and np.isfinite(v) else None for v, ok in zip(line, mask)] for line, mask in zip(array, good)]

    payload = dict(resource=spec['resource'], turbine=str(turbine['id']), radius=spec['radius'], demo=bool(options.get('demo')),
                   step_m=grid.step * stride, analysis_step_m=grid.step, azimuth=data['azimuth'],
                   x=x.tolist(), y=y.tolist(), ground=clean(ground[gy, gx], ground_valid[gy, gx] & inside),
                   surface=clean(np.maximum(ground[gy, gx], surface[gy, gx]), valid),
                   ground_z=float(ground_z) if np.isfinite(ground_z) else None, hub=turbine['hub'], diameter=turbine['diameter'],
                   eye=float(data['eye_z']) if np.isfinite(data['eye_z']) else None,
                   observer=[data['observer_x'] - turbine['x'], data['observer_y'] - turbine['y']], status=data['status'])
    scene = folder / ('scena_3d_' + spec['resource'] + '.html')
    template = Path(__file__).with_name('scene3d.html').read_text(encoding='utf-8')
    # Avoid closing an inline script if a user-supplied source ID contains HTML.
    serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    scene.write_text(template.replace('/*SCENE_DATA*/', serialized), encoding='utf-8')
    return dict(model=spec['resource'], turbine=str(turbine['id']), profile=str(profile_path), scene=str(scene),
                azimuth=data['azimuth'], preview_step_m=grid.step * stride, profile_status=data['status'])
