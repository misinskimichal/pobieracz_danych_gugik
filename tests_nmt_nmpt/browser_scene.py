"""Optional real Chromium/WebGL regression check; dev-only requests, websocket-client, Pillow."""
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
    source, output = Path(sys.argv[1]), Path(sys.argv[2])
    output.mkdir(exist_ok=True, parents=True)

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
        '--user-data-dir=' + str(output/'profile'), '--use-gl=angle', '--use-angle=swiftshader',
        '--enable-unsafe-swiftshader', 'about:blank'], stdout=log, stderr=log, env=os.environ.copy())
    connection = None
    try:
        port_file = output/'profile/DevToolsActivePort'
        deadline = time.monotonic()+15
        while not port_file.exists():
            if time.monotonic() > deadline:
                raise RuntimeError('Chromium failed to start')
            time.sleep(.1)
        port = int(port_file.read_text().splitlines()[0])
        pages = requests.get(f'http://127.0.0.1:{port}/json/list', timeout=3).json()
        connection = websocket.create_connection(next(p['webSocketDebuggerUrl'] for p in pages if p['type'] == 'page'), timeout=30)
        number = 0
        errors = []

        def call(method, params=None):
            nonlocal number
            number += 1
            connection.send(json.dumps(dict(id=number, method=method, params=params or {})))
            while True:
                message = json.loads(connection.recv())
                if message.get('method') == 'Runtime.exceptionThrown':
                    errors.append(message)
                if message.get('id') == number:
                    assert 'error' not in message, message
                    return message.get('result', {})

        def evaluate(code):
            result = call('Runtime.evaluate', dict(expression=code, returnByValue=True, awaitPromise=True))
            assert 'exceptionDetails' not in result, result
            return result.get('result', {}).get('value')

        call('Runtime.enable')
        call('Page.enable')
        trace = """window.__glFailures=[];
        for(const name of ['drawArrays','drawElements','uniform1f','uniform1i','uniform2fv','uniform3fv','uniform4fv','uniformMatrix4fv','vertexAttribPointer','texImage2D','generateMipmap']){
          const original=WebGLRenderingContext.prototype[name];
          WebGLRenderingContext.prototype[name]=function(...args){const result=original.apply(this,args),error=this.getError();if(error)window.__glFailures.push({name,error,stack:new Error().stack});return result};
        }"""
        if os.environ.get('SCENE_TRACE_GL'):
            call('Page.addScriptToEvaluateOnNewDocument', dict(source=trace))
        call('Emulation.setDeviceMetricsOverride', dict(width=1600, height=1100, deviceScaleFactor=1, mobile=False))
        nav = call('Page.navigate', dict(url=f'http://127.0.0.1:{server.server_port}/scene'))
        assert not nav.get('errorText'), nav
        deadline = time.monotonic()+45
        while True:
            state = evaluate('document.getElementById("view")?.sceneDiagnostics?.()')
            if state and state['preview_loaded'] and state['tiles_completed'] == state['tiles_expected']:
                break
            assert time.monotonic() < deadline, state
            time.sleep(.2)
        assert state['tiles_loaded'] == state['tiles_expected'] > 0, state
        assert not state['tile_errors'] and state['gl_error'] == 0, state

        def frame(name, code=''):
            data = evaluate('(async()=>{' + code + ';await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);return document.getElementById("view").toDataURL("image/png")})()')
            path = output/(name+'.png')
            path.write_bytes(base64.b64decode(data.split(',', 1)[1]))
            return np.asarray(Image.open(path).convert('RGB')).astype(np.int16)

        def wait_images():
            deadline = time.monotonic()+40
            while True:
                current = evaluate('document.getElementById("view").sceneDiagnostics()')
                if current['tiles_loaded'] == current['tiles_expected'] and current['tiles_completed'] == current['tiles_expected']:
                    assert not current['tile_errors'] and not current['gl_error'], current
                    return current
                assert time.monotonic() < deadline, current
                time.sleep(.1)
        photo = frame('eye_photo')
        colors = frame('eye_colors', 'document.getElementById("photo").checked=false;document.getElementById("photo").dispatchEvent(new Event("input"))')
        changed = np.count_nonzero(np.max(np.abs(photo-colors), axis=2) > 10)
        assert changed > 10000, changed
        frame('eye_photo_restored', 'document.getElementById("show-photo").click()')
        switches = []
        valid_views = evaluate('(scene.detail_views||[]).map((v,i)=>v.error?-1:i).filter(i=>i>=0)')
        if len(valid_views) > 1:
            target = valid_views[1]
            evaluate(f'document.getElementById("viewpoint").value={target};document.getElementById("viewpoint").dispatchEvent(new Event("change"))')
            switched = wait_images()
            assert switched['active_view'] == target
            assert switched['tiles_loaded'] < switched['export_tiles_expected'], switched
            frame('viewpoint_2')
            switches.append(switched)
            evaluate(f'document.getElementById("viewpoint").value={valid_views[0]};document.getElementById("viewpoint").dispatchEvent(new Event("change"))')
            switches.append(wait_images())
        assert evaluate('document.getElementById("view").sceneDiagnostics().forest_presentation')
        continuous = frame('continuous_nmpt', 'document.getElementById("forest-objects").checked=false;document.getElementById("forest-objects").dispatchEvent(new Event("input"))')
        assert np.count_nonzero(np.max(np.abs(photo-continuous), axis=2) > 10) > 1000
        frame('top_photo', 'document.getElementById("photo-top").click()')
        final = evaluate('document.getElementById("view").sceneDiagnostics()')
        if os.environ.get('SCENE_TRACE_GL'):
            failures = evaluate('window.__glFailures')
            assert not failures, failures[:5]
        assert not errors and final['gl_error'] == 0, (errors, final)
        (output/'result.json').write_text(json.dumps(dict(initial=state, final=final, changed_pixels=int(changed), exceptions=errors, view_switches=switches), indent=2))
        print('PASS: real Chromium/WebGL, local image tiles, eye-level photo pixel comparison, forest presentation and top view;', changed, 'changed pixels')
    finally:
        if connection:
            connection.close()
        server.shutdown()
        server.server_close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        log.close()


if __name__ == '__main__':
    main()
