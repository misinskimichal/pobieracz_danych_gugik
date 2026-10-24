"""Bounded, georeferenced image blocks shared by QGIS export and browser meshes."""
import base64
import json
import math
from pathlib import Path
# Only constructs output trees; no external XML is parsed.
from xml.etree import ElementTree as ET  # nosec B405

from qgis.PyQt.QtCore import QRectF
from qgis.PyQt.QtGui import QImage, QPainter


def image_plan(x, y, origin, bounds, resolution=.25):
    """At most 8x8 images, 64 MP; every internal image edge is a mesh edge."""
    resolution = float(resolution)
    if not math.isfinite(resolution) or not .05 <= resolution <= 10:
        raise ValueError('Rozdzielczość zdjęcia musi wynosić 0,05–10 m/px')
    if len(x) < 2 or len(y) < 2:
        return []
    step = max(abs(x[1]-x[0]), abs(y[1]-y[0]))
    cells = max(math.ceil(max(len(x)-1, len(y)-1)/8), min(128, max(1, math.floor(1024*resolution/step))))
    output = []
    for row in range(0, len(y)-1, cells):
        for col in range(0, len(x)-1, cells):
            r1, c1 = min(row+cells, len(y)-1), min(col+cells, len(x)-1)
            box = [bounds[0] if col == 0 else x[col]+origin[0],
                   bounds[1] if r1 == len(y)-1 else y[r1]+origin[1],
                   bounds[2] if c1 == len(x)-1 else x[c1]+origin[0],
                   bounds[3] if row == 0 else y[row]+origin[1]]
            requested = max(box[2]-box[0], box[3]-box[1])/resolution
            pixels = min(1024, max(128, 2**math.ceil(math.log2(max(1, requested)))))
            w, h = box[2]-box[0], box[3]-box[1]
            output.append(dict(id=len(output), row0=row, row1=r1, col0=col, col1=c1,
                               bounds=box, pixels=pixels,
                               width_px=max(1, round(pixels*w/max(w, h))), height_px=max(1, round(pixels*h/max(w, h))),
                               resolution_m=max(box[2]-box[0], box[3]-box[1])/pixels))
    return output


def save_image_block(report, item, block, image):
    """A PNG + world file and CRS sidecar; the VRT supplies portable full CRS."""
    from .scene_texture import texture_quality
    # A small real photo block may be uniform water/snow. Validate the mosaic globally.
    info = texture_quality(image, allow_flat=True)
    image = image.convertToFormat(QImage.Format_RGBA8888)
    folder = Path(report['report_dir']) / ('ortofoto_' + item['model'])
    folder.mkdir(exist_ok=True)
    path = folder / f'kafel_{block["id"]:03}.png'
    temporary = path.with_suffix('.tmp.png')
    if not image.save(str(temporary), 'PNG'):
        raise ValueError('Nie można zapisać kafla ortofotomapy')
    temporary.replace(path)
    x0, y0, x1, y1 = block['bounds']
    dx, dy = (x1-x0)/image.width(), (y1-y0)/image.height()
    path.with_suffix('.pgw').write_text(f'{dx:.12f}\n0\n0\n{-dy:.12f}\n{x0+dx/2:.12f}\n{y1-dy/2:.12f}\n')
    from .atlas import srs2180
    metadata = ET.Element('PAMDataset')
    ET.SubElement(metadata, 'SRS').text = srs2180().ExportToWkt()
    ET.SubElement(metadata, 'GeoTransform').text = ','.join(map(str, [x0, dx, 0, y1, 0, -dy]))
    ET.ElementTree(metadata).write(str(path)+'.aux.xml', encoding='utf-8', xml_declaration=True)
    return dict(block, path=str(path), width=image.width(), height=image.height(), coverage_fraction=info['coverage_fraction'])


def finish_image_blocks(report, item, blocks, errors=None):
    """Write a local mosaic and embed the exact per-block image/extent in HTML."""
    folder = Path(report['report_dir'])
    errors = errors or []
    item['texture_tile_errors'] = errors
    if not blocks:
        return
    bounds = item['scene_bounds']
    dx = max((b['bounds'][2]-b['bounds'][0])/b['width'] for b in blocks)
    dy = max((b['bounds'][3]-b['bounds'][1])/b['height'] for b in blocks)
    nx, ny = math.ceil((bounds[2]-bounds[0])/dx), math.ceil((bounds[3]-bounds[1])/dy)
    # Keep outer bounds exact, including partial final blocks.
    dx, dy = (bounds[2]-bounds[0])/nx, (bounds[3]-bounds[1])/ny
    vrt = ET.Element('VRTDataset', rasterXSize=str(nx), rasterYSize=str(ny))
    ET.SubElement(vrt, 'SRS').text = 'EPSG:2180'
    ET.SubElement(vrt, 'GeoTransform').text = ','.join(map(str, [bounds[0], dx, 0, bounds[3], 0, -dy]))
    for band, color in enumerate(['Red', 'Green', 'Blue', 'Alpha'], 1):
        node = ET.SubElement(vrt, 'VRTRasterBand', dataType='Byte', band=str(band))
        ET.SubElement(node, 'ColorInterp').text = color
        for block in blocks:
            source = ET.SubElement(node, 'SimpleSource', resampling='bilinear')
            ET.SubElement(source, 'SourceFilename', relativeToVRT='1').text = str(Path(block['path']).relative_to(folder)).replace('\\', '/')
            ET.SubElement(source, 'SourceBand').text = str(band)
            ET.SubElement(source, 'SrcRect', xOff='0', yOff='0', xSize=str(block['width']), ySize=str(block['height']))
            b = block['bounds']
            ET.SubElement(source, 'DstRect', xOff=str((b[0]-bounds[0])/dx), yOff=str((bounds[3]-b[3])/dy),
                          xSize=str((b[2]-b[0])/dx), ySize=str((b[3]-b[1])/dy))
    path = folder / ('ortofoto_' + item['model'] + '.vrt')
    ET.ElementTree(vrt).write(path, encoding='utf-8', xml_declaration=True)
    embedded = []
    for block in blocks:
        image = 'data:image/png;base64,' + base64.b64encode(Path(block['path']).read_bytes()).decode('ascii')
        embedded.append(dict(id=block['id'], bounds=block['bounds'], row0=block['row0'], row1=block['row1'],
                             col0=block['col0'], col1=block['col1'], image=image))
    scene = Path(item['scene'])
    text = scene.read_text(encoding='utf-8')
    marker = '/*SCENE_TEXTURE_TILES*/[]'
    if marker not in text:
        raise ValueError('Odśwież scenę nową wersją, aby zapisać kafle zdjęcia')
    temporary = scene.with_suffix('.tmp.html')
    text = text.replace(marker, json.dumps(embedded, separators=(',', ':')))
    text = text.replace('/*SCENE_TEXTURE_ISSUES*/[]', json.dumps(errors, ensure_ascii=False).replace('<', '\\u003c'))
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(scene)
    item.update(texture_tiles=blocks, texture_vrt=str(path))
    item.setdefault('texture_info', {}).update(tiles=len(blocks), mosaic_width=nx, mosaic_height=ny,
                                               effective_resolution_m=round(max(dx, dy), 4),
                                               tile_errors=len(errors), local_mosaic=str(path))


def make_preview(item, blocks, pixels=2048):
    """Small locator image. It is deliberately separate from full-resolution tiles."""
    b = item['scene_bounds']
    w, h = b[2]-b[0], b[3]-b[1]
    image = QImage(max(1, round(pixels*w/max(w, h))), max(1, round(pixels*h/max(w, h))), QImage.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    for block in blocks:
        box = block['bounds']
        rect = QRectF((box[0]-b[0])/w*image.width(), (b[3]-box[3])/h*image.height(),
                      (box[2]-box[0])/w*image.width(), (box[3]-box[1])/h*image.height())
        painter.drawImage(rect, QImage(block['path']))
    painter.end()
    return image
