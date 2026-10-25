"""Exact public Street View references and optional official Static API access."""
import math
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import requests

from .core import check_cancel


def street_reference(url):
    parsed = urlparse(str(url).strip())
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or host not in ('google.com', 'www.google.com', 'maps.google.com', 'www.google.pl', 'google.pl') or parsed.username:
        raise ValueError('Wklej pełny adres HTTPS widoku z Google Maps. Krótki link otwórz najpierw w przeglądarce i skopiuj adres z paska.')
    text = unquote(parsed.path)
    query = parse_qs(parsed.query)
    at = re.search(r'@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?),([^/]+)', text)
    viewpoint = query.get('viewpoint', [''])[0]
    pano = query.get('pano', [''])[0]
    match = re.search(r'!1s([^!/?]+)', text)
    if match and ',3a' in text:
        pano = match.group(1)
    if query.get('map_action', [''])[0] != 'pano' and not (at and '3a' in at.group(3)):
        raise ValueError('To link do mapy, nie do Street View. Otwórz panoramę, ustaw kadr i skopiuj pełny adres widoku.')
    try:
        lat, lon = map(float, viewpoint.split(',')) if viewpoint else (float(at.group(1)), float(at.group(2)))
        values = dict(heading=0., pitch=0., fov=75.)
        if at:
            camera = at.group(3)
            for key, suffix in [('heading', 'h'), ('fov', 'y'), ('pitch', 't')]:
                number = re.search(r'(?:^|,)(-?\d+(?:\.\d+)?)' + suffix + r'(?:,|$)', camera)
                if number:
                    values[key] = 90 - float(number.group(1)) if key == 'pitch' else float(number.group(1))
        for key in values:
            if key in query:
                values[key] = float(query[key][0])
        if not all(math.isfinite(v) for v in [lat, lon, *values.values()]) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError('W linku brakuje poprawnej pozycji lub kierunku aparatu') from None
    values.update(heading=values['heading'] % 360, pitch=max(-85, min(85, values['pitch'])), fov=max(10, min(120, values['fov'])))
    if pano and not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', pano):
        raise ValueError('Nieprawidłowy identyfikator panoramy')
    params = dict(api=1, map_action='pano', viewpoint=f'{lat:.8f},{lon:.8f}', **values)
    if pano:
        params['pano'] = pano
    return dict(lat=lat, lon=lon, pano=pano, **values, url='https://www.google.com/maps/@?' + urlencode(params))


def fetch_street_frame(reference, key, destination, event, session=None):
    """A user's own API key is used only in requests, never in returned metadata or errors."""
    if not key.strip():
        raise ValueError('Podaj własny klucz Street View Static API w ustawieniach zaawansowanych')
    client = session or requests.Session()
    base = 'https://maps.googleapis.com/maps/api/streetview'
    selector = dict(pano=reference['pano']) if reference.get('pano') else dict(location=f'{reference["lat"]},{reference["lon"]}', radius=50)
    try:
        check_cancel(event)
        with client.get(base + '/metadata', params=dict(selector, key=key), timeout=(10, 30), stream=True) as response:
            if response.status_code != 200:
                raise ValueError(f'Google: odpowiedź HTTP {response.status_code}; sprawdź dostęp API i rozliczenia')
            content = response.content
            if len(content) > 512000:
                raise ValueError('Nieprawidłowa odpowiedź metadanych Google')
            import json
            metadata = json.loads(content)
        status = metadata.get('status')
        if status != 'OK':
            messages = dict(ZERO_RESULTS='Brak panoramy w tym miejscu', REQUEST_DENIED='Klucz nie ma dostępu do Street View Static API lub rozliczenia nie są aktywne', OVER_QUERY_LIMIT='Przekroczono limit API')
            raise ValueError('Google: ' + messages.get(status, 'usługa nie zwróciła panoramy'))
        params = dict(pano=metadata['pano_id'], size='640x480', heading=reference['heading'], pitch=reference['pitch'], fov=reference['fov'], key=key, return_error_code='true')
        check_cancel(event)
        with client.get(base, params=params, timeout=(10, 30), stream=True) as response:
            if response.status_code != 200:
                raise ValueError(f'Google: nie udało się pobrać kadru, HTTP {response.status_code}')
            image = bytearray()
            for chunk in response.iter_content(65536):
                check_cancel(event)
                image.extend(chunk)
                if len(image) > 16 * 1024 * 1024:
                    raise ValueError('Kadr przekracza limit 16 MB')
        location = metadata['location']
        updated = dict(reference, lat=float(location['lat']), lon=float(location['lng']), pano=metadata['pano_id'],
                       date=metadata.get('date'), copyright=metadata.get('copyright'), method='Google Street View Static API')
        updated['url'] = 'https://www.google.com/maps/@?' + urlencode(dict(api=1, map_action='pano', pano=updated['pano'],
                                                                           viewpoint=f'{updated["lat"]},{updated["lon"]}',
                                                                           heading=updated['heading'], pitch=updated['pitch'], fov=updated['fov']))
        temporary = Path(str(destination) + '.tmp.jpg')
        try:
            temporary.write_bytes(image)
            from .photo_core import inspect_photo
            inspect_photo(temporary)
            check_cancel(event)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return updated
    except requests.RequestException:
        raise ValueError('Nie można połączyć się z Google Street View Static API. Sprawdź sieć i ustawienia dostępu.') from None
    finally:
        if session is None:
            client.close()
