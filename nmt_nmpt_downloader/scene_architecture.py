"""Conservative measured roof fits. Facade appearance remains illustrative."""
import numpy as np


def fit_roof(xy, heights, rings, triangles, base, fallback, step):
    xy, heights = np.asarray(xy, float), np.asarray(heights, float)
    if len(heights) < 24:
        return dict(roof_model='flat_insufficient_samples')
    center = np.mean(np.asarray(rings[0][:-1], float), axis=0)
    points = xy-center
    outline = np.asarray(rings[0][:-1], float)-center
    covariance = np.cov(outline.T)
    _, axes = np.linalg.eigh(covariance)
    candidates = []

    def solve(design):
        good = np.isfinite(heights)
        for _ in range(3):
            coef = np.linalg.lstsq(design[good], heights[good], rcond=None)[0]
            residual = heights-design@coef
            median = np.median(residual[good])
            scale = max(.25, float(np.median(abs(residual[good]-median)))*1.4826)
            good = abs(residual-median) <= max(.6, 2.5*scale)
            if good.sum() < 20:
                return None
        return coef, float(np.sqrt(np.mean(residual[good]**2))), float(good.mean())
    flat_error = float(np.sqrt(np.mean((heights-np.median(heights))**2)))
    plane = solve(np.c_[np.ones(len(points)), points])
    if plane:
        coef, rmse, fraction = plane
        variation = float(np.ptp(np.c_[np.ones(len(outline)), outline]@coef))
        if 1 <= variation <= 12 and np.linalg.norm(coef[1:]) <= 1.5:
            candidates.append(dict(kind='plane', coef=coef, rmse=rmse, fraction=fraction))
    for direction in axes.T:
        projected, edge = points@direction, outline@direction
        low, high = float(edge.min()), float(edge.max())
        if high-low < 4:
            continue
        mid, half = (low+high)/2, (high-low)/2
        basis = np.clip(1-abs((projected-mid)/half), 0, 1)
        fitted = solve(np.c_[np.ones(len(points)), basis])
        if fitted:
            coef, rmse, fraction = fitted
            if 1 <= coef[1] <= 12 and coef[0] > base+2:
                candidates.append(dict(kind='gable', coef=coef, rmse=rmse, fraction=fraction,
                                       direction=direction, mid=mid, half=half))
    candidates = [c for c in candidates if c['rmse'] <= max(.75, step*.7) and c['rmse'] < flat_error*.6 and c['fraction'] >= .75]
    if not candidates:
        return dict(roof_model='flat_unresolved')
    model = min(candidates, key=lambda candidate: candidate['rmse'])

    def elevation(point):
        local = np.asarray(point)-center
        if model['kind'] == 'plane':
            value = float(np.r_[1., local]@model['coef'])
        else:
            factor = np.clip(1-abs((local@model['direction']-model['mid'])/model['half']), 0, 1)
            value = float(model['coef'][0]+model['coef'][1]*factor)
        return float(np.clip(value, base+2, fallback+.25))

    def signed(point):
        return float((np.asarray(point)-center)@model['direction']-model['mid'])

    def split(poly, positive):
        result = []
        previous = poly[-1]
        da = signed(previous)*(1 if positive else -1)
        for point in poly:
            db = signed(point)*(1 if positive else -1)
            if (da >= 0) != (db >= 0):
                fraction = da/(da-db)
                result.append([previous[k]+fraction*(point[k]-previous[k]) for k in range(2)])
            if db >= 0:
                result.append(point)
            previous, da = point, db
        return result
    faces = []
    for triangle in triangles:
        parts = [split(triangle, True), split(triangle, False)] if model['kind'] == 'gable' else [triangle]
        for part in parts:
            for i in range(1, len(part)-1):
                face = [part[0], part[i], part[i+1]]
                a, b = np.asarray(face[1])-face[0], np.asarray(face[2])-face[0]
                area = a[0]*b[1]-a[1]*b[0]
                if abs(float(area)) > 1e-6:
                    faces.append([[float(p[0]), float(p[1]), elevation(p)] for p in face])
    walls = []
    for ring in rings:
        for a, b in zip(ring, ring[1:]):
            middle = []
            if model['kind'] == 'gable' and signed(a)*signed(b) < 0:
                fraction = signed(a)/(signed(a)-signed(b))
                middle = [[a[k]+fraction*(b[k]-a[k]) for k in range(2)]]
            line = [a]+middle+[b]
            for p, q in zip(line, line[1:]):
                walls.append([[float(p[0]), float(p[1]), elevation(p)], [float(q[0]), float(q[1]), elevation(q)]])
    return dict(roof_model='nmpt_fit_'+model['kind'], roof_rmse_m=round(model['rmse'], 3),
                roof_faces=faces, wall_edges=walls)
