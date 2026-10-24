// Development smoke test. The plugin does not require Node.js at runtime.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const template = fs.readFileSync('nmt_nmpt_downloader/scene3d_canvas.html', 'utf8');
const source = template.match(/<script>([\s\S]*?)<\/script>/)[1];
let commands = [], frames = [];
const ctx = new Proxy({}, {get: (_, name) => (...args) => {
  for (const arg of args) if (typeof arg === 'number') assert(Number.isFinite(arg), name);
  commands.push([name, ...args]);
}, set: () => true});
const elements = {};
for (const id of ['title', 'info', 'profile', 'full-scene', 'bearing', 'tilt', 'vertical', 'cover', 'reset', 'view', 'low', 'high', 'bval', 'tval', 'vval']) {
  elements[id] = {value: id === 'tilt' ? 25 : id === 'vertical' ? 1 : 225,
    checked: true, handlers: {}, addEventListener(name, callback) {this.handlers[name] = callback;}};
}
Object.assign(elements.view, {clientWidth: 1200, clientHeight: 700, getContext: () => ctx, setPointerCapture() {}});
const payload = {resource: 'NMPT', turbine: 'demo', radius: 100, step_m: 100, analysis_step_m: 1, azimuth: 225,
  x: [-100, 0, 100], y: [100, 0, -100], ground: [[90, 100, null], [90, 100, 110], [90, 95, 100]],
  surface: [[90, 115, null], [90, 105, 110], [90, 95, 100]], ground_z: 100,
  hub: 30, diameter: 20, eye: 91.7, observer: [-70, -70], status: ['widoczna', 'widoczna', 'widoczna']};
const context = {console, document: {getElementById: id => elements[id]},
  window: {devicePixelRatio: 1, addEventListener() {}}, requestAnimationFrame: cb => frames.push(cb)};
vm.runInNewContext(source.replace('/*SCENE_DATA*/', JSON.stringify(payload)), context);
frames.shift()();
const initial = JSON.stringify(commands);
assert(commands.some(c => c[0] === 'fill'));
assert(elements.title.textContent.includes('NMPT'));
commands = [];
elements.bearing.value = 90;
elements.bearing.handlers.input();
frames.shift()();
assert.notEqual(JSON.stringify(commands), initial, 'Camera rotation must change projected geometry');
commands = [];
elements.cover.checked = false;
elements.cover.handlers.input();
frames.shift()();
assert(commands.some(c => c[0] === 'fill'));
elements.view.handlers.wheel({preventDefault() {}, deltaY: -200});
frames.shift()();
elements.reset.onclick();
frames.shift()();
assert.equal(elements.bearing.value, 225);
console.log('PASS: finite 3D projection, gaps, camera rotation, terrain toggle, zoom and reset');
