const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const constants=['TEXTURE_2D','RGBA','UNSIGNED_BYTE','TEXTURE_MIN_FILTER','TEXTURE_MAG_FILTER','LINEAR','TEXTURE_WRAP_S','TEXTURE_WRAP_T','CLAMP_TO_EDGE','ARRAY_BUFFER','ELEMENT_ARRAY_BUFFER','STATIC_DRAW','TRIANGLES','LINES','FLOAT','UNSIGNED_SHORT','VERTEX_SHADER','FRAGMENT_SHADER','COMPILE_STATUS','LINK_STATUS','UNPACK_FLIP_Y_WEBGL','DEPTH_TEST','POLYGON_OFFSET_FILL','COLOR_BUFFER_BIT','DEPTH_BUFFER_BIT'];
let id=0,bound={},buffers={},matrix=null,draws=[],depth=false;
const methods={};constants.forEach((key,i)=>methods[key]=i+1);
Object.assign(methods,{
 createBuffer:()=>++id,createShader:()=>++id,createProgram:()=>++id,createTexture:()=>++id,
 bindBuffer:(target,buffer)=>bound[target]=buffer,
 bufferData:(target,data)=>{assert(Array.from(data).every(Number.isFinite));buffers[bound[target]]=data.slice()},
 getAttribLocation:(_,name)=>['aPosition','aNormal','aColor','aUv','aTextured'].indexOf(name),
 getUniformLocation:(_,name)=>name,getShaderParameter:()=>true,getProgramParameter:()=>true,
 uniformMatrix4fv:(_,transpose,values)=>{assert.equal(values.length,16);assert(Array.from(values).every(Number.isFinite));matrix=Array.from(values)},
 drawElements:(mode,count)=>draws.push({mode,count,vertices:bound[methods.ARRAY_BUFFER],indices:bound[methods.ELEMENT_ARRAY_BUFFER],depth}),
 drawArrays:(mode,first,count)=>draws.push({mode,count,vertices:bound[methods.ARRAY_BUFFER],depth}),
 enable:what=>{if(what===methods.DEPTH_TEST)depth=true},disable:what=>{if(what===methods.DEPTH_TEST)depth=false},
});
const gl=new Proxy(methods,{get:(target,name)=>name in target?target[name]:()=>{}}),elements={},frames=[];
const ids=['title','info','profile','fallback','bearing','tilt','vertical','sun','projection','fov','material','cover','trees','lines','texture-option','status','view','low','high','bval','tval','vval','fval','reset','save'];
for(const key of ids)elements[key]={value:{tilt:28,vertical:1,sun:300,projection:'perspective',fov:45,material:'height'}[key]??225,checked:true,handlers:{},addEventListener(name,cb){this.handlers[name]=cb}};
Object.assign(elements.view,{clientWidth:1600,clientHeight:1000,getContext:()=>gl,setPointerCapture(){}});
const payload=process.argv[2]?JSON.parse(fs.readFileSync(process.argv[2],'utf8')):{resource:'NMPT',turbine:'demo',radius:100,profile_radius:100,step_m:50,analysis_step_m:1,azimuth:225,x:[-50,0,50],y:[50,0,-50],ground:[[90,100,null],[90,100,110],[90,95,100]],surface:[[90,115,null],[90,105,110],[90,95,100]],forest:[[0,1,0],[0,1,0],[0,0,0]],trees:[{x:0,y:0,ground:100,height:15}],ground_z:100,hub:30,diameter:20,eye:91.7,observer:[-70,-70],status:['widoczna','widoczna','widoczna']};
const context={console,document:{getElementById:key=>elements[key]},window:{devicePixelRatio:1,addEventListener(){}},requestAnimationFrame:cb=>frames.push(cb),scene:payload,textureData:null};
vm.runInNewContext(fs.readFileSync('nmt_nmpt_downloader/scene_webgl.js','utf8'),context);frames.shift()();
assert(elements.status.textContent.startsWith('Gotowe'),elements.status.textContent);
assert(draws.some(d=>d.mode===methods.TRIANGLES&&d.indices));
assert(draws.some(d=>d.mode===methods.LINES&&!d.depth),'Visibility lines are an explicitly unoccluded overlay');
for(const d of draws){assert(buffers[d.vertices].length%12===0);if(d.indices)assert(Array.from(buffers[d.indices]).every(i=>i<buffers[d.vertices].length/12))}
const initial=matrix.slice();elements.bearing.value=90;elements.bearing.handlers.input();draws=[];frames.shift()();assert.notDeepEqual(matrix,initial);
elements.projection.value='ortho';elements.projection.handlers.input();frames.shift()();assert.notDeepEqual(matrix,initial);
elements.material.value='cover';elements.material.handlers.input();frames.shift()();assert(elements.status.textContent.startsWith('Gotowe'));
elements.cover.checked=false;elements.cover.handlers.input();frames.shift()();assert(elements.status.textContent.startsWith('Gotowe'));
elements.reset.onclick();frames.shift()();assert.equal(elements.bearing.value,payload.azimuth);
// Optional exact GPU replay data for development-only verification of a synthetic scene.
if(process.argv[3]){
 elements.cover.checked=true;elements.material.value='cover';elements.cover.handlers.input();draws=[];frames.shift()();
 const out=process.argv[3];fs.mkdirSync(out,{recursive:true});const used=new Set(draws.flatMap(d=>d.indices?[d.vertices,d.indices]:[d.vertices]));
 for(const key of used)fs.writeFileSync(`${out}/buffer_${key}.bin`,Buffer.from(buffers[key].buffer,buffers[key].byteOffset,buffers[key].byteLength));
 fs.writeFileSync(`${out}/frame.json`,JSON.stringify({matrix,draws,methods,vertical:+elements.vertical.value,texture:payload.texture_bounds,radius:payload.radius}));
}
console.log('PASS: WebGL runtime, finite buffers, tree/turbine geometry, depth test, camera, FOV, materials and terrain toggle');
