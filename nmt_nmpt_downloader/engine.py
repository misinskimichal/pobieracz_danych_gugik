"""Bounded concurrent transfers, durable diagnostics, cancellation and cache validation."""
import concurrent.futures as futures
import json
import math
import os
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import requests
from .catalog import HEIGHTS, Variant, choose_variants, endpoints

from .core import (
    VERSION, SOURCES, STATUS_LABELS, NATIVE_RESOLUTION, Canceled, ServiceError, atomic_json, buffer_index, build_buffers,
    check_cancel, feature_geojson, inspect_raster, parse_description, plan_tiles,
    save_gap_mask, save_geotiff, tile_aoi, xml_root,
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Engine:
    def __init__(self, source, crs, context, options, notify=lambda _: None, log=lambda _: None):
        self.source, self.crs, self.context, self.options = source, crs, context, options
        self.notify, self.log = notify, log
        self.cancel_event = threading.Event()
        self.lock = threading.Lock()
        self.active = {}
        self.bytes_received = 0
        self.started = time.monotonic()
        self.transfer_started = None
        self.last_notify = 0
        self.last_checkpoint = time.monotonic()
        self.samples = []
        self.completed = 0
        self.total = 0
        self.estimated_tile_bytes = 0
        self.stage = 'Przygotowanie'
        self.records = []
        self.gaps = []
        self.report = {}
        self.report_dir = None
        self.folder_locks = []

    def emit_stats(self, force=False):
        now = time.monotonic()
        with self.lock:
            if not force and now - self.last_notify < 0.25:
                return
            self.last_notify = now
            elapsed = now - self.started
            transfer_elapsed = now - self.transfer_started if self.transfer_started else 0
            rate = self.bytes_received / transfer_elapsed if transfer_elapsed else 0
            average = sum(self.samples) / len(self.samples) if self.samples else self.estimated_tile_bytes
            # Transfer sizes for unrequested tiles cannot be known exactly before downloading.
            remaining = max(0, (self.total - self.completed) * average - sum(v['bytes'] for v in self.active.values()))
            data = {'stage': self.stage, 'done': self.completed, 'total': self.total,
                    'bytes': self.bytes_received, 'remaining_estimate': remaining,
                    'speed': rate, 'eta': remaining / rate if rate else None,
                    'elapsed': elapsed, 'active': list(self.active.values()),
                    'counts': dict(Counter(r['status'] for r in self.records))}
            partial = sum(min(0.95, v['bytes'] / max(1, v['expected'] or average)) for v in self.active.values())
            data['fraction_done'] = min(1.0, (self.completed + partial) / self.total) if self.total else 0
        self.notify(data)

    def event(self, message):
        self.log(message)
        if self.report_dir:
            with (self.report_dir / 'events.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'time': utc_now(), 'message': message}, ensure_ascii=False) + '\n')

    def _progress(self, tile, count=0, expected=None, phase=None):
        with self.lock:
            if self.transfer_started is None:
                self.transfer_started = time.monotonic()
            self.bytes_received += count
            item = self.active.setdefault(tile.name, {
                'file': tile.name, 'resource': tile.resource, 'bytes': 0, 'expected': None, 'phase': 'Pobieranie'})
            item['bytes'] += count
            if expected is not None:
                item['expected'] = expected
            if phase:
                item['phase'] = phase
        self.emit_stats()

    def _lock_folders(self):
        for folder in sorted(set(self.options['folders'][r] for r in self.options['resources'])):
            Path(folder).mkdir(parents=True, exist_ok=True)
            path = Path(folder) / '.nmt_nmpt_downloader.lock'
            try:
                descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError as exc:
                raise RuntimeError(f'Folder jest używany przez inne zadanie: {folder}. '
                                   'Po awarii sprawdź, czy pobieranie nie trwa, zanim usuniesz plik .nmt_nmpt_downloader.lock.') from exc
            self.folder_locks.append(path)
            with os.fdopen(descriptor, 'w') as stream:
                stream.write(json.dumps({'pid': os.getpid(), 'time': utc_now(), 'report': str(self.report_dir)}))

    def _describe(self, resource, height=None, endpoint=None):
        endpoint = endpoint or SOURCES[resource][0]
        coverage = SOURCES[resource][1] + '_' + (height or self.options.get('height', HEIGHTS[0]))
        error = None
        for attempt in range(3):
            check_cancel(self.cancel_event)
            try:
                with requests.get(endpoint, params={'SERVICE': 'WCS', 'VERSION': '1.0.0',
                                                    'REQUEST': 'DescribeCoverage', 'COVERAGE': coverage},
                                  timeout=(10, 60), stream=True) as response:
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_content(65536):
                        check_cancel(self.cancel_event)
                        content.extend(chunk)
                        if len(content) > 2_000_000:
                            raise ServiceError('DescribeCoverage przekracza limit rozmiaru')
                return parse_description(bytes(content), coverage)
            except (requests.RequestException, ServiceError, ValueError) as exc:
                error = exc
                if isinstance(exc, requests.HTTPError) and exc.response.status_code in (400, 401, 403, 404):
                    break
                if attempt < 2 and self.cancel_event.wait(2 ** attempt):
                    raise Canceled()
        raise ServiceError(str(error))

    def discover(self):
        variants, descriptions, errors = [], [], []
        with futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix='wcs-catalog') as pool:
            pending = {pool.submit(self._describe, resource, height, endpoint): (resource, height, endpoint)
                       for resource in self.options['resources'] for height in HEIGHTS for endpoint in endpoints(resource)}
            for future in futures.as_completed(pending):
                check_cancel(self.cancel_event)
                resource, height, endpoint = pending[future]
                try:
                    description = future.result()
                    variant = Variant(resource, height, description['native_resolution'], endpoint, description['coverage'])
                    variants.append(variant)
                    descriptions.append(dict(description, resource=resource, height=height, endpoint=endpoint))
                except Canceled:
                    raise
                except Exception as exc:
                    errors.append(dict(resource=resource, height=height, endpoint=endpoint, error=str(exc)))
        return variants, descriptions, errors

    def resource_settings(self, resource):
        return self.options.get('resource_settings', {}).get(resource, {
            'resolution': self.options.get('resolution', 0), 'height': self.options.get('height', HEIGHTS[0]),
            'strict_resolution': False, 'alternate_height': False})

    def _download_variants(self, planned, aoi, variants):
        attempts = []
        best = None
        for variant in variants:
            if self.cancel_event.is_set():
                break
            side = planned.pixels * planned.resolution
            tile = replace(planned, height=variant.height, resolution=variant.resolution,
                           pixels=round(side / variant.resolution), endpoint=variant.endpoint)
            result = self._download(tile, aoi)
            result.update(height=tile.height, native_resolution_m=variant.resolution,
                          requested_resolution_m=self.resource_settings(tile.resource)['resolution'])
            attempts.append(result)
            with self.lock:
                self.active.pop(tile.name, None)
            score = (result.get('coverage_percent') or 0, result['status'] in ('downloaded', 'reused', 'partial'))
            old_score = (best.get('coverage_percent') or 0, best['status'] in ('downloaded', 'reused', 'partial')) if best else (-1, False)
            if score > old_score:
                best = result
            if result['status'] in ('downloaded', 'reused', 'outside_pixels', 'canceled'):
                break
        if best is None:
            return dict(resource=planned.resource, bbox_2180=planned.bbox, file=None,
                        status='canceled', reason='Anulowano przed pobraniem')
        final = dict(best)
        final['alternatives'] = attempts
        final['files'] = sorted({a['file'] for a in attempts if a.get('file') and a['status'] in ('downloaded', 'reused', 'partial')})
        final['transfer_bytes'] = sum(a.get('transfer_bytes', 0) for a in attempts)
        final['fallback_used'] = len(attempts) > 1 or not math.isclose(
            best['resolution_m'], self.resource_settings(planned.resource)['resolution'] or best['resolution_m'])
        final['fallback_used'] |= best['height'] != self.resource_settings(planned.resource)['height']
        if self.cancel_event.is_set():
            final['status'] = 'canceled'
            final['reason'] = 'Anulowano podczas sprawdzania zamienników; zakończone pliki zachowano'
        return final

    def _download(self, tile, aoi):
        target = Path(self.options['folders'][tile.resource]) / tile.name
        temporary = target.with_name('.' + tile.name + '.' + uuid.uuid4().hex + '.asc.part')
        converted = temporary.with_suffix('.tif')
        result = {'resource': tile.resource, 'file': str(target), 'bbox_2180': tile.bbox,
                  'resolution_m': tile.resolution, 'coverage': tile.coverage,
                  'url': requests.Request('GET', tile.url, params=tile.params()).prepare().url,
                  'attempts': 0, 'transfer_bytes': 0, 'reused': False, 'errors': []}
        try:
            check_cancel(self.cancel_event)
            self._progress(tile, phase='Sprawdzanie pliku')
            if target.exists():
                stats, gap_mask = inspect_raster(target, tile, aoi, signature_required=True)
                if self.options['reuse']:
                    result.update(stats, reused=True, output_bytes=target.stat().st_size)
                    return self._finalize_tile(result, gap_mask, tile)
            for attempt in range(3):
                check_cancel(self.cancel_event)
                result['attempts'] = attempt + 1
                with self.lock:
                    self.active[tile.name]['bytes'] = 0
                    self.active[tile.name]['expected'] = None
                self._progress(tile, phase=f'Pobieranie (próba {attempt + 1}/3)')
                try:
                    with requests.get(tile.url, params=tile.params(), stream=True,
                                      timeout=(10, 90), headers={
                                          'Accept-Encoding': 'identity', 'User-Agent': 'QGIS-NMT-NMPT/1.0'}) as response:
                        response.raise_for_status()
                        expected = int(response.headers.get('Content-Length') or 0) or None
                        self._progress(tile, expected=expected)
                        received = 0
                        prefix = bytearray()
                        with temporary.open('wb') as stream:
                            for chunk in response.iter_content(65536):
                                check_cancel(self.cancel_event)
                                if not chunk:
                                    continue
                                stream.write(chunk)
                                received += len(chunk)
                                result['transfer_bytes'] += len(chunk)
                                if len(prefix) < 8192:
                                    prefix.extend(chunk[:8192 - len(prefix)])
                                self._progress(tile, count=len(chunk))
                                if received > tile.pixels * tile.pixels * 64 + 1_000_000:
                                    raise ServiceError('Odpowiedź przekracza limit rozmiaru kafla')
                        if expected and not response.headers.get('Content-Encoding') and received != expected:
                            raise requests.ConnectionError('Niekompletna odpowiedź HTTP')
                        if bytes(prefix).lstrip().startswith(b'<'):
                            xml_root(bytes(prefix))
                            raise ServiceError('Serwer zwrócił XML zamiast danych wysokościowych')
                        if not bytes(prefix).lstrip().lower().startswith(b'ncols'):
                            raise ServiceError('Odpowiedź nie jest numerycznym ASCII Grid')
                    self._progress(tile, phase='Walidacja i kompresja')
                    stats, gap_mask = inspect_raster(temporary, tile, aoi)
                    result.update(stats)
                    check_cancel(self.cancel_event)
                    if stats['requested_cells'] and stats['nodata_cells'] < stats['requested_cells']:
                        save_geotiff(temporary, converted, tile)
                        # Verify pixels, signature and georeferencing before publishing a complete file.
                        inspect_raster(converted, tile, aoi, signature_required=True)
                        converted.replace(target)
                        result['output_bytes'] = target.stat().st_size
                    else:
                        result['file'] = None
                    return self._finalize_tile(result, gap_mask, tile)
                except (requests.RequestException, ServiceError, ValueError, RuntimeError) as exc:
                    result['errors'].append(str(exc))
                    if isinstance(exc, requests.HTTPError) and exc.response is not None:
                        code = exc.response.status_code
                        if code < 500 and code not in (408, 429):
                            break
                    if attempt < 2:
                        self._progress(tile, phase='Ponowienie po błędzie')
                        if self.cancel_event.wait(2 ** attempt):
                            raise Canceled()
            result.update(status='failed', reason=result['errors'][-1])
        except Canceled:
            result.update(status='canceled', reason='Anulowano przez użytkownika')
        except Exception as exc:
            result.update(status='failed', reason=str(exc))
        finally:
            for path in [temporary, temporary.with_suffix('.prj'), Path(str(temporary) + '.aux.xml'), converted]:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        return result

    def _finalize_tile(self, result, gap_mask, tile):
        requested, missing = result['requested_cells'], result['nodata_cells']
        if not requested:
            result.update(status='outside_pixels', reason='Obszar nie obejmuje środka żadnego piksela tej rozdzielczości')
        elif missing == requested:
            result.update(status='missing', reason='Serwer zwrócił wyłącznie NoData w żądanym obszarze')
        elif missing:
            result.update(status='partial', reason='Część żądanego obszaru ma NoData')
        else:
            result.update(status='reused' if result['reused'] else 'downloaded', reason='')
        if missing:
            mask_path = self.report_dir / 'masks' / (tile.name[:-4] + '_braki.tif')
            save_gap_mask(mask_path, gap_mask, tile)
            result['gap_mask'] = str(mask_path)
        return result

    def _record(self, tile, aoi, record):
        self.records.append(record)
        self.completed += 1
        with self.lock:
            self.active.pop(tile.name, None)
            if record.get('transfer_bytes') and record.get('status') in ('downloaded', 'partial'):
                self.samples.append(record['transfer_bytes'] / max(1, record['attempts']))
                self.samples = self.samples[-30:]
        if record['status'] in ('missing', 'partial', 'failed', 'canceled', 'outside_pixels'):
            self.gaps.append(feature_geojson(aoi, self.context, {
                'resource': tile.resource, 'tile': tile.name, 'status': record['status'],
                'reason': record['reason'], 'diagnostic_extent_only': True,
                'gap_mask': record.get('gap_mask'), 'nodata_cells': record.get('nodata_cells'),
            }))
        self.event(f'{tile.name}: {STATUS_LABELS[record["status"]]}' + (': ' + record['reason'] if record.get('reason') else ''))
        self.emit_stats()
        if time.monotonic() - self.last_checkpoint >= 5:
            self._write_report('running')
            self.last_checkpoint = time.monotonic()

    def _write_report(self, state):
        counts = dict(Counter(r['status'] for r in self.records))
        self.report.update(state=state, updated_at=utc_now(), elapsed_seconds=round(time.monotonic() - self.started, 2),
                           transfer_bytes=self.bytes_received, planned_tiles=self.total,
                           completed_tiles=self.completed, counts=counts, tiles=self.records)
        atomic_json(self.report_dir / 'report.json', self.report)
        atomic_json(self.report_dir / 'obszary_problemowe.geojson', {'type': 'FeatureCollection', 'features': self.gaps})
        summary = '\n'.join(f'- {STATUS_LABELS[key]}: {value}' for key, value in sorted(counts.items()))
        resources_summary = []
        for resource in self.options['resources']:
            records = [r for r in self.records if r['resource'] == resource]
            totals = Counter(r['status'] for r in records)
            resource_counts = ', '.join(f'{STATUS_LABELS[k]}: {v}' for k, v in sorted(totals.items())) or 'brak kafli'
            size = sum(r.get('output_bytes', 0) for r in records) / 1_000_000
            resources_summary.append(f'- {resource}: {resource_counts}; pliki na dysku: {size:.2f} MB')
        lines = ['# NMT / NMPT — raport pobierania', '', f'Stan: **{state}**',
                 f'Rozpoczęto (UTC): {self.report["started_at"]}',
                 f'Kafle rozpatrzone: {self.completed} / {self.total}',
                 f'Pobrano przez sieć: {self.bytes_received / 1_000_000:.2f} MB (łącznie z ponowieniami)',
                 f'Czas: {self.report["elapsed_seconds"]:.1f} s', '', summary, '',
                 '## Zasoby', '', *resources_summary, '',
                 'GeoTIFF: EPSG:2180, Float32. Układ wysokościowy każdego pliku: pole height / coverage w JSON i nazwa pliku.',
                 'Zamienniki zachowują faktyczną rozdzielczość i układ. Nie wykonano transformacji wysokości ani łączenia układów.',
                 'MB oznacza 1 000 000 bajtów. ETA i pozostałe MB w interfejsie są szacunkowe.',
                 'Każdy plik obejmuje pełny kafel. Braki NoData zliczane są tylko wewnątrz bufora (środki pikseli).',
                 'GeoJSON wskazuje fragmenty kafli wymagające uwagi, a nie dokładny kształt dziur.',
                 'Dokładne braki NoData: rastry masks/*_braki.tif (1 = brak, 0 = poza brakami).',
                 'Błąd usługi/sieci oznacza niezweryfikowany obszar, nie dowiedziony brak danych.',
                 'NoData nie wyjaśnia przyczyny braku danych; raport nie przypisuje mu niepotwierdzonej przyczyny.', '',
                 '## Pominięte geometrie wejściowe', '']
        for issue in self.report.get('input_issues', []):
            lines.append(f'- Obiekt {issue["feature_id"]}: {issue["reason"]}')
        if self.report.get('fatal_error'):
            lines.extend(['', '## Błąd zadania', self.report['fatal_error']])
        lines.extend(['', '## Zastosowane zamienniki', ''])
        for record in self.records:
            if record.get('fallback_used'):
                lines.append(f'- {record["resource"]}: faktyczny piksel {record["resolution_m"]:g} m, '
                             f'układ {record["height"]}; pliki: {record.get("files", [])}')
        lines.extend(['', '## Braki i błędy', '', '| Zasób | Kafel / obszar EPSG:2180 | Stan | Powód |',
                      '|---|---|---|---|'])
        for record in self.records:
            if record['status'] not in ('downloaded', 'reused'):
                reason = record.get('reason', '').replace('|', '/').replace('\n', ' ')
                lines.append(f'| {record["resource"]} | {record["bbox_2180"]} | {record["status"]} | {reason} |')
        temp = self.report_dir / 'report.md.tmp'
        temp.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        temp.replace(self.report_dir / 'report.md')

    def run(self):
        state = 'failed'
        try:
            run_id = datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8]
            self.report_dir = Path(self.options['report_folder']) / ('raport_' + run_id)
            (self.report_dir / 'masks').mkdir(parents=True)
            self.report = {'version': VERSION, 'started_at': utc_now(), 'options': self.options,
                           'crs': 'EPSG:2180', 'sources': {}, 'input_issues': []}
            self._write_report('running')
            self._lock_folders()
            self.stage = 'Przygotowanie buforów'
            self.emit_stats(True)
            buffers, issues = build_buffers(
                self.source, self.crs, self.context, self.options.get('feature_ids'),
                self.options['radius'], self.cancel_event, self.event)
            self.report['input_issues'] = issues
            self.report['input_features_used'] = len(buffers)
            spatial_index = buffer_index(buffers)
            atomic_json(self.report_dir / 'obszar.geojson', {'type': 'FeatureCollection', 'features': [
                feature_geojson(g, self.context, {'buffer_index': i}) for i, g in enumerate(buffers)]})
            unavailable, resolutions, heights, pixel_counts, selections = {}, {}, {}, {}, {}
            self.stage = 'Weryfikacja usług WCS'
            self.emit_stats(True)
            variants, descriptions, catalog_errors = self.discover()
            self.report['source_catalog'] = descriptions
            self.report['catalog_errors'] = catalog_errors
            for resource in self.options['resources']:
                settings = self.resource_settings(resource)
                try:
                    choices = choose_variants([v for v in variants if v.resource == resource],
                                              settings['resolution'], settings['height'], settings['strict_resolution'],
                                              settings['alternate_height'])
                    selections[resource] = choices
                    preferred = choices[0]
                    self.report['sources'][resource] = preferred.as_dict()
                    fractions = [Fraction(str(v.resolution)).limit_denominator(1000000) for v in choices]
                    unit = math.lcm(*(v.numerator for v in fractions)) / math.gcd(*(v.denominator for v in fractions))
                    side = math.ceil(self.options['pixels'] * preferred.resolution / unit - 1e-9) * unit
                    resolutions[resource], heights[resource] = preferred.resolution, preferred.height
                    pixel_counts[resource] = round(side / preferred.resolution)
                    self.event(f'{resource}: wybrano {preferred.resolution:g} m, {preferred.height}; '
                               f'żądano {settings["resolution"] or "źródłowej"} m; wariantów: {len(choices)}')
                except Exception as exc:
                    unavailable[resource] = str(exc)
                    resolutions[resource] = settings['resolution'] or NATIVE_RESOLUTION[resource]
                    heights[resource] = settings['height']
                    pixel_counts[resource] = self.options['pixels']
                    self.event(f'{resource}: usługa niedostępna: {exc}')
            self.stage = 'Planowanie kafli'
            self.emit_stats(True)
            tiles = plan_tiles(buffers, self.options['resources'], heights, resolutions,
                               pixel_counts, self.cancel_event)
            self.total = len(tiles)
            self.estimated_tile_bytes = self.options['pixels'] ** 2 * 22
            self.event(f'Zaplanowano {self.total} unikalnych kafli. Równoległość: {self.options["workers"]}')
            self.report['resolutions_m'] = resolutions
            self.stage = 'Pobieranie'
            iterator = iter(tiles)
            pending = {}
            exhausted = False
            with futures.ThreadPoolExecutor(max_workers=self.options['workers'], thread_name_prefix='nmt-wcs') as pool:
                while pending or not exhausted:
                    while not exhausted and len(pending) < self.options['workers']:
                        try:
                            tile = next(iterator)
                        except StopIteration:
                            exhausted = True
                            break
                        aoi = tile_aoi(tile, buffers, spatial_index)
                        if self.cancel_event.is_set() or tile.resource in unavailable:
                            record = {'resource': tile.resource, 'bbox_2180': tile.bbox, 'file': None,
                                      'status': 'canceled' if self.cancel_event.is_set() else 'failed',
                                      'reason': 'Anulowano przed pobraniem' if self.cancel_event.is_set() else unavailable[tile.resource]}
                            self._record(tile, aoi, record)
                        else:
                            pending[pool.submit(self._download_variants, tile, aoi, selections[tile.resource])] = (tile, aoi)
                    if not pending:
                        continue
                    done, _ = futures.wait(pending, timeout=0.25, return_when=futures.FIRST_COMPLETED)
                    self.emit_stats()
                    for future in done:
                        tile, aoi = pending.pop(future)
                        self._record(tile, aoi, future.result())
            if self.cancel_event.is_set():
                state = 'canceled'
            elif any(r['status'] not in ('downloaded', 'reused') for r in self.records) or issues:
                state = 'completed_with_gaps'
            else:
                state = 'completed'
            self.event('Zadanie zakończone: ' + state)
        except Canceled:
            state = 'canceled'
        except Exception as exc:
            self.report['fatal_error'] = str(exc)
            self.log('Błąd zadania: ' + str(exc))
        finally:
            for path in self.folder_locks:
                try:
                    path.unlink()
                except OSError:
                    pass
            if self.report_dir:
                try:
                    self._write_report(state)
                except Exception as exc:
                    state = 'failed'
                    self.report['fatal_error'] = f'Nie udało się zapisać raportu: {exc}'
            self.report['state'] = state
            self.report['report_dir'] = str(self.report_dir) if self.report_dir else None
            self.stage = {'completed': 'Zakończono', 'completed_with_gaps': 'Zakończono z brakami / błędami',
                          'canceled': 'Anulowano', 'failed': 'Błąd zadania'}[state]
            self.emit_stats(True)
        return self.report
