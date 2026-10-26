"""Optional real Chromium check: rendering, editing masks and downloading full-size PNG/JSON.

Dev-only dependencies: requests, websocket-client, Pillow. No Google requests.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
from PIL import Image
import requests
import websocket


def main():
    source, output = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
    output.mkdir(exist_ok=True, parents=True)
    downloads = output/'downloads'
    downloads.mkdir(exist_ok=True)

    class Page(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def do_GET(self):
            data = source.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log = (output/'chromium.log').open('w')
    process = subprocess.Popen([
        '/usr/lib/chromium/chromium', '--headless=new', '--no-sandbox', '--no-zygote',
        '--disable-dev-shm-usage', '--disable-extensions', '--disable-background-networking',
        '--no-first-run', '--remote-allow-origins=*', '--remote-debugging-port=0',
        '--user-data-dir='+str(output/'profile'), 'about:blank'], stdout=log, stderr=log, env=os.environ.copy())
    connection = None
    try:
        port_file = output/'profile/DevToolsActivePort'
        deadline = time.monotonic()+15
        while not port_file.exists():
            assert time.monotonic() < deadline, 'Chromium startup timeout'
            time.sleep(.1)
        port = int(port_file.read_text().splitlines()[0])
        pages = requests.get(f'http://127.0.0.1:{port}/json/list', timeout=3).json()
        connection = websocket.create_connection(next(p['webSocketDebuggerUrl'] for p in pages if p['type'] == 'page'), timeout=30)
        number, errors, network = 0, [], []

        def call(method, params=None):
            nonlocal number
            number += 1
            connection.send(json.dumps(dict(id=number, method=method, params=params or {})))
            while True:
                message = json.loads(connection.recv())
                if message.get('method') == 'Runtime.exceptionThrown':
                    errors.append(message)
                if message.get('method') == 'Network.requestWillBeSent':
                    network.append(message['params']['request']['url'])
                if message.get('id') == number:
                    assert 'error' not in message, message
                    return message.get('result', {})

        def evaluate(code):
            result = call('Runtime.evaluate', dict(expression=code, returnByValue=True, awaitPromise=True))
            assert 'exceptionDetails' not in result, result
            return result.get('result', {}).get('value')

        call('Runtime.enable')
        call('Page.enable')
        call('Network.enable')
        call('Browser.setDownloadBehavior', dict(behavior='allow', downloadPath=str(downloads)))
        call('Emulation.setDeviceMetricsOverride', dict(width=1600, height=1200, deviceScaleFactor=1, mobile=False))
        result = call('Page.navigate', dict(url=f'http://127.0.0.1:{server.server_port}/photo'))
        assert not result.get('errorText'), result
        deadline = time.monotonic()+30
        while not evaluate('document.getElementById("photo")?.photoDiagnostics?.().loaded'):
            assert time.monotonic() < deadline, errors
            time.sleep(.1)

        def frame(name, code=''):
            data = evaluate('(async()=>{'+code+';await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);return document.getElementById("photo").toDataURL("image/png")})()')
            path = output/(name+'.png')
            path.write_bytes(base64.b64decode(data.split(',', 1)[1]))
            return np.asarray(Image.open(path).convert('RGB')).astype(np.int16)

        def changed(a, b):
            return int(np.count_nonzero(np.max(np.abs(a-b), axis=2) > 5))

        occluded = frame('model_occlusion')
        assert evaluate('document.getElementById("photo").photoDiagnostics().hidden') > 0
        before = frame('original', 'document.getElementById("turbines").checked=false;document.getElementById("turbines").dispatchEvent(new Event("input"))')
        unmasked = frame('turbines', 'document.getElementById("turbines").checked=true;document.getElementById("occlusion").checked=false;document.getElementById("occlusion").dispatchEvent(new Event("input"))')
        assert changed(before, unmasked) > 500
        assert changed(occluded, unmasked) > 500
        backwards = frame('behind', 'document.getElementById("heading").value=180;document.getElementById("heading").dispatchEvent(new Event("input"))')
        assert changed(before, backwards) == 0
        assert evaluate('document.getElementById("photo").photoDiagnostics().inFrame') == 0
        restored = frame('restored', 'document.getElementById("heading").value=0;document.getElementById("heading").dispatchEvent(new Event("input"))')
        assert changed(restored, unmasked) == 0
        if os.environ.get('PHOTO_CHECK_LOCK'):
            assert evaluate('document.getElementById("mode").value') == 'locked'
            original_pose = evaluate('document.getElementById("photo").photoDiagnostics().pose')
            evaluate('document.getElementById("photo").scrollIntoView({block:"start"})')
            box = evaluate('(()=>{const r=document.getElementById("photo").getBoundingClientRect();return {x:r.left+r.width*.4,y:r.top+Math.min(r.height*.3,120)}})()')
            call('Input.dispatchMouseEvent', dict(type='mousePressed', x=box['x'], y=box['y'], button='left', clickCount=1))
            call('Input.dispatchMouseEvent', dict(type='mouseMoved', x=box['x']+100, y=box['y']+30, button='left', buttons=1))
            call('Input.dispatchMouseEvent', dict(type='mouseReleased', x=box['x']+100, y=box['y']+30, button='left', clickCount=1))
            assert evaluate('document.getElementById("photo").photoDiagnostics().pose') == original_pose
            assert evaluate('document.getElementById("photo").photoDiagnostics().strokes') == 0
        evaluate('document.getElementById("photo").scrollIntoView({block:"start"});document.getElementById("mode").value="hide";document.getElementById("brush").value=100')
        location = evaluate('(()=>{const c=document.getElementById("photo"),r=c.getBoundingClientRect(),p=c.photoDiagnostics().pose,t=photoScene.targets[0],q=PhotoMontageMath.project([t.x,t.y,t.ground+t.hub],photoScene.camera,p,c.width,c.height,photoScene.curvature);return {x:r.left+q.x/c.width*r.width,y:r.top+q.y/c.height*r.height}})()')
        call('Input.dispatchMouseEvent', dict(type='mousePressed', x=location['x']-100, y=location['y'], button='left', clickCount=1))
        call('Input.dispatchMouseEvent', dict(type='mouseMoved', x=location['x']+100, y=location['y'], button='left', buttons=1))
        call('Input.dispatchMouseEvent', dict(type='mouseReleased', x=location['x']+100, y=location['y'], button='left', clickCount=1))
        masked = frame('manual_foreground')
        assert changed(masked, unmasked) > 100
        assert evaluate('document.getElementById("photo").photoDiagnostics().strokes') == 1
        real_mask = frame('manual_foreground_without_tint', 'document.getElementById("show-mask").checked=false;document.getElementById("show-mask").dispatchEvent(new Event("input"))')
        assert changed(real_mask, unmasked) > 100
        evaluate('document.getElementById("settings").click();document.getElementById("save").click()')
        deadline = time.monotonic()+20
        while not list(downloads.glob('fotomontaz_*.png')) or not list(downloads.glob('dopasowanie_*.json')):
            assert time.monotonic() < deadline, list(downloads.iterdir())
            time.sleep(.1)
        saved_image = next(downloads.glob('fotomontaz_*.png'))
        with Image.open(saved_image) as saved:
            expected = evaluate('[document.getElementById("photo").photoDiagnostics().sourceWidth,document.getElementById("photo").photoDiagnostics().sourceHeight]')
            assert list(saved.size) == expected
        settings = json.loads(next(downloads.glob('dopasowanie_*.json')).read_text())
        assert settings['photo_id'] and settings['source_sha256']
        assert len(settings['mask_strokes']) == 1
        undone = frame('undo', 'document.getElementById("undo").click()')
        assert changed(undone, unmasked) == 0
        evaluate('window.scrollTo(0,0)')
        screenshot = call('Page.captureScreenshot', dict(format='png', captureBeyondViewport=False))
        (output/'viewer.png').write_bytes(base64.b64decode(screenshot['data']))
        assert not errors, errors
        assert not [url for url in network if url.startswith(('http:', 'https:')) and not url.startswith(f'http://127.0.0.1:{server.server_port}/')], network
        result = dict(rendered_turbine_pixels=changed(before, unmasked), model_mask_difference=changed(occluded, unmasked),
                      manual_mask_difference=changed(real_mask, unmasked), png_dimensions=expected,
                      browser_errors=errors, external_http_requests=0)
        (output/'result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
    finally:
        if connection:
            connection.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        server.shutdown()
        log.close()


if __name__ == '__main__':
    main()
