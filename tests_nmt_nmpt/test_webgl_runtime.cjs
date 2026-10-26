const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const constants=['TEXTURE_2D','TEXTURE0','TEXTURE1','TEXTURE2','REPEAT','BLEND','SRC_ALPHA','ONE_MINUS_SRC_ALPHA','RGBA','UNSIGNED_BYTE','TEXTURE_MIN_FILTER','TEXTURE_MAG_FILTER','LINEAR','LINEAR_MIPMAP_LINEAR','TEXTURE_WRAP_S','TEXTURE_WRAP_T','CLAMP_TO_EDGE','ARRAY_BUFFER','ELEMENT_ARRAY_BUFFER','STATIC_DRAW','TRIANGLES','LINES','FLOAT','UNSIGNED_SHORT','VERTEX_SHADER','FRAGMENT_SHADER','COMPILE_STATUS','LINK_STATUS','UNPACK_FLIP_Y_WEBGL','DEPTH_TEST','POLYGON_OFFSET_FILL','COLOR_BUFFER_BIT','DEPTH_BUFFER_BIT','MAX_TEXTURE_SIZE'];
let id=0,bound={},buffers={},matrix=null,draws=[],depth=false,gpuError=0,failUpload=false,uploadedTexture=null,locatorPhotos=0,photoUniform=null;
const methods={};constants.forEach((key,i)=>methods[key]=i+1);
Object.assign(methods,{
 createBuffer:()=>++id,createShader:()=>++id,createProgram:()=>++id,createTexture:()=>++id,
 bindBuffer:(target,buffer)=>bound[target]=buffer,
 bufferData:(target,data)=>{assert(Array.from(data).every(Number.isFinite));buffers[bound[target]]=data.slice()},
 getAttribLocation:(_,name)=>['aPosition','aNormal','aColor','aUv','aTextured'].indexOf(name),
 getUniformLocation:(_,name)=>name,getShaderParameter:()=>true,getProgramParameter:()=>true,
 uniformMatrix4fv:(_,transpose,values)=>{assert.equal(values.length,16);assert(Array.from(values).every(Number.isFinite));matrix=Array.from(values)},
 uniform1f:(key,value)=>{if(key==='uUseTexture')photoUniform=value},
 drawElements:(mode,count)=>draws.push({mode,count,vertices:bound[methods.ARRAY_BUFFER],indices:bound[methods.ELEMENT_ARRAY_BUFFER],depth}),
 drawArrays:(mode,first,count)=>draws.push({mode,count,vertices:bound[methods.ARRAY_BUFFER],depth}),
 enable:what=>{if(what===methods.DEPTH_TEST)depth=true},disable:what=>{if(what===methods.DEPTH_TEST)depth=false},
});
const gl=new Proxy(methods,{get:(target,name)=>name in target?target[name]:()=>{}}),elements={},frames=[];
methods.NO_ERROR=0;methods.getError=()=>{const value=gpuError;gpuError=0;return value};
methods.getParameter=key=>key===methods.MAX_TEXTURE_SIZE?2048:undefined;
methods.texImage2D=(...args)=>{if(args.length===6){uploadedTexture=args[5];gpuError=failUpload?1285:0}};
const ids=['title','info','profile','fallback','bearing','tilt','vertical','sun','projection','fov','material','cover','trees','buildings','surface-mode','forest-objects','photo-shade','photo-top','diagnostics','viewpoint','lines','photo','show-photo','context-status','status','view','low','high','bval','tval','vval','fval','reset','save','camera','eye-height','locator','eye-status','texture-status','look-turbine','bearing-label','download-texture'];
for(const key of ids)elements[key]={value:{tilt:28,vertical:1,sun:300,projection:'perspective',fov:45,material:'height'}[key]??225,checked:true,style:{display:'none'},handlers:{},appendChild(){},addEventListener(name,cb){this.handlers[name]=cb}};
Object.assign(elements.view,{clientWidth:1600,clientHeight:1000,getContext:()=>gl,setPointerCapture(){}});
Object.assign(elements.locator,{width:320,height:320,getContext:()=>new Proxy({drawImage(){locatorPhotos++}},{get:(target,key)=>target[key]||(()=>{}),set:()=>true}),getBoundingClientRect:()=>({left:0,top:0,width:320,height:320})});
const payload=process.argv[2]?JSON.parse(fs.readFileSync(process.argv[2],'utf8')):{resource:'NMPT',turbine:'demo',radius:100,profile_radius:100,step_m:50,analysis_step_m:1,azimuth:225,x:[-50,0,50],y:[50,0,-50],ground:[[90,100,null],[90,100,110],[90,95,100]],surface:[[90,115,null],[90,105,110],[90,95,100]],forest:[[0,1,0],[0,1,0],[0,0,0]],trees:[{x:0,y:0,ground:100,height:15}],ground_z:100,hub:30,diameter:20,eye:91.7,observer:[-70,-70],status:['widoczna','widoczna','widoczna']};
if(!process.argv[2])payload.buildings=[{rings:[[[10,10],[20,10],[20,20],[10,20],[10,10]]],roof_triangles:[[[10,10],[20,10],[20,20]],[[10,10],[20,20],[10,20]]],ground:100,roof:108}];
const images=[];class TestImage{constructor(){images.push(this);this.naturalWidth=4096;this.naturalHeight=2048}set src(value){this.source=value}}
const mockContext=()=>new Proxy({createLinearGradient:()=>({addColorStop(){}})},{get:(target,key)=>target[key]||(()=>{}),set:()=>true});
const context={console,document:{getElementById:key=>elements[key],createElement:key=>key==='option'?{}:{getContext:mockContext}},window:{devicePixelRatio:1,addEventListener(){}},requestAnimationFrame:cb=>frames.push(cb),scene:payload,textureData:'data:image/png;base64,fixture',Image:TestImage};
vm.runInNewContext(fs.readFileSync('nmt_nmpt_downloader/scene_appearance.js','utf8'),context);
vm.runInNewContext(fs.readFileSync('nmt_nmpt_downloader/scene_webgl.js','utf8'),context);frames.shift()();
assert(elements.status.textContent.startsWith('Gotowe'),elements.status.textContent);
if(elements.camera.value==='eye'){assert.equal(+elements.vertical.value,1);elements.reset.onclick();frames.shift()();elements.lines.checked=true;elements.lines.handlers.input();frames.shift()()}
assert(draws.some(d=>d.mode===methods.TRIANGLES&&d.indices));
assert(draws.some(d=>d.mode===methods.LINES&&!d.depth),'Visibility lines are an explicitly unoccluded overlay');
for(const d of draws){assert(buffers[d.vertices].length%12===0);if(d.indices)assert(Array.from(buffers[d.indices]).every(i=>i<buffers[d.vertices].length/12))}
const initial=matrix.slice();elements.bearing.value=90;elements.bearing.handlers.input();draws=[];frames.shift()();assert.notDeepEqual(matrix,initial);
elements.projection.value='ortho';elements.projection.handlers.input();frames.shift()();assert.notDeepEqual(matrix,initial);
elements.material.value='cover';elements.material.handlers.input();frames.shift()();assert(elements.status.textContent.startsWith('Gotowe'));
elements.cover.checked=false;elements.cover.handlers.input();frames.shift()();assert(elements.status.textContent.startsWith('Gotowe'));
elements.reset.onclick();frames.shift()();assert.equal(elements.bearing.value,payload.azimuth);
elements.camera.value='eye';elements.camera.handlers.input();frames.shift()();
assert.equal(elements.camera.value,'eye',elements['eye-status'].textContent);
assert.equal(+elements.vertical.value,1);assert.equal(elements.projection.value,'perspective');
assert.equal(elements.lines.checked,false);assert(elements['eye-status'].textContent.includes('NMT'));
const eyeMatrix=matrix.slice();elements.bearing.value=(+elements.bearing.value+25)%360;elements.bearing.handlers.input();frames.shift()();assert.notDeepEqual(matrix,eyeMatrix);
elements.view.onpointerdown({clientX:100,clientY:100,pointerId:1});elements.view.onpointermove({clientX:100,clientY:600});frames.shift()();assert(+elements.tilt.value<0,'Eye mode must allow looking down');elements.view.onpointerup();
elements.view.handlers.keydown({key:'ArrowUp',shiftKey:false,preventDefault(){}});if(frames.length)frames.shift()();
if(!process.argv[2]){elements.locator.handlers.pointerdown({clientX:32,clientY:288});if(frames.length)frames.shift()();assert(elements['eye-status'].textContent.includes('X=-40.00'))}
elements.reset.onclick();frames.shift()();
images[0].onerror();assert(elements['texture-status'].textContent.includes('Nie można'));
images[0].onload();frames.shift()();assert.equal(elements.photo.checked,true);assert.equal(elements.photo.disabled,false);assert(elements['texture-status'].textContent.includes('rysowanie na modelu WŁĄCZONE'));assert.equal(photoUniform,1);
elements.material.value='cover';elements.material.handlers.input();frames.shift()();assert.equal(photoUniform,1,'Changing the palette must not turn off the photograph');
assert(elements['texture-status'].textContent.includes('WŁĄCZONE'));
elements.photo.checked=false;elements.photo.handlers.input();frames.shift()();assert.equal(photoUniform,0);assert(elements['texture-status'].textContent.includes('WYŁĄCZONE NA MODELU'));
elements.photo.checked=true;elements.photo.handlers.input();frames.shift()();assert.equal(photoUniform,1);
if(!process.argv[2]){
 elements.cover.checked=true;elements.cover.handlers.input();frames.shift()();
 assert(elements.status.textContent.includes('1 brył budynków'));
 const construction=draws.filter(d=>d.mode===methods.TRIANGLES&&!d.indices).at(-1);
 const built=Array.from(buffers[construction.vertices]).filter((_,i)=>i%12===11);
 assert.equal(built.filter(v=>v===1).length,6,'Both roof triangles use the orthophoto; walls, tree and turbine remain untextured');
 elements.buildings.checked=false;elements.buildings.handlers.input();frames.shift()();assert(elements.status.textContent.includes('0 brył budynków'));
 elements['surface-mode'].value='objects';elements['surface-mode'].handlers.input();frames.shift()();assert.equal(elements.cover.checked,false);assert.equal(photoUniform,1);assert(elements.status.textContent.includes('1 brył budynków'));assert(elements['context-status'].textContent.includes('przerwy między symbolami'));
}
assert.equal(uploadedTexture.width,2048);assert.equal(uploadedTexture.height,2048,'Each texture dimension must fit the device and allow mipmaps');
assert.equal(elements['download-texture'].href,context.textureData);assert.equal(elements['download-texture'].style.display,'');
assert(locatorPhotos>0,'Decoded image must also appear in the location picker');
images[0].naturalWidth=512;images[0].naturalHeight=512;gpuError=1280;images[0].onload();frames.shift()();
assert.equal(uploadedTexture,images[0]);assert.equal(elements.photo.disabled,false,'An earlier drawing error must not be attributed to image upload');
// Optional exact GPU replay data for development-only verification of a synthetic scene.
if(process.argv[3]){
 elements.cover.checked=true;elements.photo.checked=true;elements.cover.handlers.input();draws=[];frames.shift()();
 if(process.argv[4]==='eye'){const b=payload.texture_bounds||[payload.x[0],payload.y[payload.y.length-1],payload.x[payload.x.length-1],payload.y[0]],point=payload.camera_observer;assert(point);draws=[];elements.locator.handlers.pointerdown({clientX:(point[0]-b[0])/(b[2]-b[0])*320,clientY:(b[3]-point[1])/(b[3]-b[1])*320});frames.shift()();assert.equal(elements.camera.value,'eye')}
 if(process.argv[5]==='objects'){draws=[];elements['surface-mode'].value='objects';elements['surface-mode'].handlers.input();frames.shift()()}
 const out=process.argv[3];fs.mkdirSync(out,{recursive:true});const used=new Set(draws.flatMap(d=>d.indices?[d.vertices,d.indices]:[d.vertices]));
 for(const key of used)fs.writeFileSync(`${out}/buffer_${key}.bin`,Buffer.from(buffers[key].buffer,buffers[key].byteOffset,buffers[key].byteLength));
 fs.writeFileSync(`${out}/frame.json`,JSON.stringify({matrix,draws,methods,vertical:+elements.vertical.value,texture:payload.texture_bounds,radius:payload.radius,camera:elements.camera.value,eye_info:elements['eye-status'].textContent,material:elements.material.value,photo:elements.photo.checked}));
}
failUpload=true;const photosBefore=locatorPhotos;images[0].onload();frames.shift()();
assert.equal(elements.photo.disabled,true);assert(elements['texture-status'].textContent.includes('1285'));
assert(locatorPhotos>photosBefore,'A failed GPU upload must preserve the photo on the location picker');
assert.equal(elements['download-texture'].href,context.textureData);
console.log('PASS: WebGL runtime, geometry, camera, photo download, device texture limit, stale GL errors and GPU failure diagnostics');
