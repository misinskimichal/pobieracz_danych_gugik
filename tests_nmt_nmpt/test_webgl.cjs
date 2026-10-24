// Pure geometry/projection checks; QGIS users do not need Node.js.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {heightColor,multiply,lookAt,projection,terrainTile,vertexShader,fragmentShader}=require('../nmt_nmpt_downloader/scene_webgl.js');
assert.deepEqual(vertexShader.match(/varying\s+mediump\s+\w+\s+\w+;/g),fragmentShader.match(/varying\s+mediump\s+\w+\s+\w+;/g),'Varying precision must match for strict GLSL ES/WebGL linkers');
const s={x:[-1,0,1],y:[1,0,-1],radius:1,forest:[[0,0,0],[0,1,0],[0,0,0]]};
const heights=[[0,0,0],[0,null,0],[0,0,0]];
const hole=terrainTile(s,heights,0,0,2,2,0,1,'height');
assert.equal(hole.indices.length,6,'Exactly two corner triangles remain around a central gap');
assert(!Array.from(hole.indices).includes(4),'No triangle uses the missing vertex');
assert(Array.from(hole.vertices).every(Number.isFinite));
const high=Array.from({length:129},()=>Array(129).fill(12));
const big={x:Array.from({length:129},(_,i)=>i),y:Array.from({length:129},(_,i)=>-i),radius:100};
const tile=terrainTile(big,high,0,0,128,128,0,20,'height');
assert(tile.indices instanceof Uint16Array);
assert.equal(tile.indices.length,128*128*6);
assert(Math.max(...tile.indices.subarray(0,1024))<65536);
assert(Array.from(tile.indices).every(i=>i<129*129));
const full=Array.from({length:3},()=>Array(3).fill(0));
const green=terrainTile(s,full,0,0,2,2,0,1,'cover');
assert(Math.abs(green.vertices[4*12+6]-.15)<1e-6);
const eye=[2,3,4],view=lookAt(eye,[0,0,0]);
const transformed=[0,1,2,3].map(r=>view[r]*eye[0]+view[4+r]*eye[1]+view[8+r]*eye[2]+view[12+r]);
assert(transformed.slice(0,3).every(v=>Math.abs(v)<1e-6));
for(const ortho of [true,false])for(const fov of [15,45,90]){
 const matrix=multiply(projection(fov,1.5,3,ortho),view);
 assert(Array.from(matrix).every(Number.isFinite));
}
assert.notDeepEqual(heightColor(0),heightColor(1));
if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify({vertexShader,fragmentShader}));
console.log('PASS: mesh gaps, safe UInt16 patches, forest colors, finite camera matrices, orthographic and perspective FOV');
