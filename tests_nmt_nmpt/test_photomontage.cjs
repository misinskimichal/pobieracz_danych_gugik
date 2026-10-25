'use strict';
const assert=require('node:assert/strict');
const M=require('../nmt_nmpt_downloader/photo_montage.js');
const near=(a,b,tolerance=1e-8)=>assert.ok(Math.abs(a-b)<tolerance,`${a} != ${b}`);
const camera={x:500000,y:500000,z:100},pose={heading:0,pitch:0,roll:0,fov:90};
let p=M.project([500000,501000,100],camera,pose,1200,800);
near(p.x,600);near(p.y,400);
p=M.project([501000,501000,100],camera,pose,1200,800);near(p.x,1200);
p=M.project([500000,501000,200],camera,pose,1200,800);near(p.y,340);
assert.equal(M.project([500000,499000,100],camera,pose,1200,800),null);
for(const heading of [0,90,180,359])for(const pitch of [-40,0,25])for(const roll of [-20,0,15]){
  const pose={heading,pitch,roll,fov:65};
  for(const [x,y] of [[600,400],[100,200],[1000,700]]){
    const direction=M.ray(x,y,pose,1200,800);
    const point=[camera.x+direction[0]*2000,camera.y+direction[1]*2000,camera.z+direction[2]*2000];
    const projected=M.project(point,camera,pose,1200,800);
    near(projected.x,x,1e-7);near(projected.y,y,1e-7);
  }
}
const horizon={bearings:[-.1,0,.1],angles:[.2,.3,.4],unknown:[false,false,false]};
near(M.horizonAngle(horizon,.05),.35);
near(M.horizonAngle(horizon,Math.PI*2+.05),.35);
assert.equal(M.horizonAngle(horizon,2),null);
assert.equal(M.horizonAngle({...horizon,unknown:[false,true,false]},0),null);
const turbine={x:0,y:1000,ground:100,hub:120,diameter:160};
for(const yaw of [0,45,90,180]){
  const mesh=M.geometry(turbine,yaw,0),points=mesh.flatMap(f=>f.points);
  near(Math.max(...points.map(p=>p[2])),300); // ground + hub + rotor radius.
  near(Math.min(...points.map(p=>p[2])),100);
  assert.ok(points.every(p=>p.every(Number.isFinite)));
  assert.equal(mesh.length,25); // tower + six nacelle faces + three rotor blades.
}
console.log('PASS: analytic perspective, 108 projection/inverse cases, 360° horizon wrapping, missing data and turbine dimensions');
