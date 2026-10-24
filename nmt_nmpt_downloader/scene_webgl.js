/* Standalone WebGL 1. No external libraries, network requests or Uint32 index extension. */
'use strict';
function heightColor(t) {
  const stops=[[33/255,134/255,90/255],[228/255,212/255,94/255],[211/255,71/255,71/255]];
  const f=Math.max(0,Math.min(.999999,t))*2,i=Math.floor(f),u=f-i;
  return stops[i].map((v,k)=>v*(1-u)+stops[i+1][k]*u);
}
function multiply(a,b) {
  const out=new Float32Array(16);
  for(let c=0;c<4;c++)for(let r=0;r<4;r++)for(let k=0;k<4;k++)out[c*4+r]+=a[k*4+r]*b[c*4+k];
  return out;
}
function dot(a,b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]}
function normalize(a){const n=Math.hypot(...a)||1;return a.map(v=>v/n)}
function cross(a,b){return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]}
function lookAt(eye,target) {
  const z=normalize(eye.map((v,k)=>v-target[k])),x=normalize(cross([0,0,1],z)),y=cross(z,x);
  return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1]);
}
function projection(fov,aspect,distance,ortho,near=.005,far=100) {
  const f=1/Math.tan(fov*Math.PI/360);
  if(ortho){const h=distance/f,w=h*aspect;return new Float32Array([1/w,0,0,0,0,1/h,0,0,0,0,-2/(far-near),0,0,0,-(far+near)/(far-near),1])}
  return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)/(near-far),-1,0,0,2*far*near/(near-far),0]);
}
function surfaceAt(s,field,x,y){
  if(!Number.isFinite(x)||!Number.isFinite(y)||s.x.length<2||s.y.length<2||x*x+y*y>s.radius*s.radius)return null;
  const fx=(x-s.x[0])/(s.x[1]-s.x[0]),fy=(s.y[0]-y)/(s.y[0]-s.y[1]);
  if(fx<0||fy<0||fx>s.x.length-1||fy>s.y.length-1)return null;
  const c=Math.min(s.x.length-2,Math.floor(fx)),r=Math.min(s.y.length-2,Math.floor(fy)),u=fx-c,v=fy-r;
  const a=field[r][c],b=field[r+1][c],cc=field[r][c+1],d=field[r+1][c+1];
  if(u+v<=1)return [a,b,cc].some(z=>z===null)?null:a+(cc-a)*u+(b-a)*v;
  return [b,cc,d].some(z=>z===null)?null:d+(b-d)*(1-u)+(cc-d)*(1-v);
}
function eyePose(s,low,point,height,heading,pitch,cover=true){
  if(!Number.isFinite(height)||height<.3||height>100)return {error:'Wpisz wysokość oka od 0,3 do 100 m nad gruntem.'};
  const ground=surfaceAt(s,s.ground,point[0],point[1]),surface=surfaceAt(s,s.surface,point[0],point[1]);
  if(ground===null)return {error:'Brak gruntu NMT w tym miejscu lub punkt jest poza sceną. Wybierz bliższy punkt albo większy zasięg sceny.'};
  if(cover&&surface===null)return {error:'Brak NMPT w tym miejscu. Wybierz punkt z kompletnymi danymi.'};
  if(cover&&surface>ground+height+.02)return {error:'Oko znalazłoby się pod dachem lub koroną NMPT. Wybierz otwarte miejsce, drogę albo zmień wysokość oka.'};
  const angle=heading*Math.PI/180,tilt=pitch*Math.PI/180;
  const eye=[point[0]/s.radius,point[1]/s.radius,(ground+height-low)/s.radius];
  return {eye,target:[eye[0]+Math.sin(angle)*Math.cos(tilt),eye[1]+Math.cos(angle)*Math.cos(tilt),eye[2]+Math.sin(tilt)],ground,eyeZ:ground+height};
}
function terrainTile(s,heights,row0,col0,row1,col1,low,high,material) {
  const width=col1-col0+1,height=row1-row0+1,vertices=new Float32Array(width*height*12),indices=[];
  const bounds=s.texture_bounds||[s.x[0],s.y[s.y.length-1],s.x[s.x.length-1],s.y[0]];
  for(let r=row0;r<=row1;r++)for(let c=col0;c<=col1;c++){
    const z=heights[r][c],v=((r-row0)*width+c-col0)*12;if(z===null)continue;
    const l=Math.max(0,c-1),right=Math.min(s.x.length-1,c+1),up=Math.max(0,r-1),down=Math.min(s.y.length-1,r+1);
    const dx=((heights[r][right]??z)-(heights[r][l]??z))/(s.x[right]-s.x[l]||1);
    const dy=((heights[down][c]??z)-(heights[up][c]??z))/(s.y[down]-s.y[up]||1);
    let color=heightColor((z-low)/(high-low||1));
    if(material==='cover')color=s.forest&&s.forest[r][c]===1?[.15,.38,.21]:[.67,.71,.48];
    vertices.set([s.x[c]/s.radius,s.y[r]/s.radius,(z-low)/s.radius,...normalize([-dx,-dy,1]),...color,
      (s.x[c]-bounds[0])/(bounds[2]-bounds[0]||1),(s.y[r]-bounds[1])/(bounds[3]-bounds[1]||1),1],v);
  }
  for(let r=row0;r<row1;r++)for(let c=col0;c<col1;c++){
    const n=(r-row0)*width+c-col0;
    if(heights[r][c]!==null&&heights[r+1][c]!==null&&heights[r][c+1]!==null)indices.push(n,n+width,n+1);
    if(heights[r+1][c]!==null&&heights[r+1][c+1]!==null&&heights[r][c+1]!==null)indices.push(n+width,n+width+1,n+1);
  }
  return {vertices,indices:new Uint16Array(indices)};
}
const vertexShader=`
precision highp float;
attribute vec3 aPosition; attribute vec3 aNormal; attribute vec3 aColor; attribute vec2 aUv; attribute float aTextured;
uniform mat4 uMatrix; uniform float uVertical;
varying mediump vec3 vNormal; varying mediump vec3 vColor; varying mediump vec2 vUv; varying mediump float vTextured;
void main(){vec3 p=aPosition;p.z*=uVertical;gl_Position=uMatrix*vec4(p,1.0);vNormal=normalize(vec3(aNormal.xy,aNormal.z/uVertical));vColor=aColor;vUv=aUv;vTextured=aTextured;}
`;
const fragmentShader=`
precision mediump float;
uniform vec3 uSun; uniform sampler2D uTexture; uniform float uUseTexture;
varying mediump vec3 vNormal; varying mediump vec3 vColor; varying mediump vec2 vUv; varying mediump float vTextured;
void main(){vec3 color=vColor;if(uUseTexture>0.5&&vTextured>0.5){vec4 photo=texture2D(uTexture,vUv);color=mix(vColor,photo.rgb,photo.a);}float light=0.56+0.44*max(dot(normalize(vNormal),uSun),0.0);gl_FragColor=vec4(color*light,1.0);}
`;
function startScene(s,textureUrl) {
  const $=id=>document.getElementById(id),canvas=$('view'),gl=canvas.getContext('webgl',{antialias:true,preserveDrawingBuffer:true,alpha:false});
  $('title').textContent=`${s.resource} · turbina ${s.turbine} · szczegółowa scena 3D`;
  $('info').textContent=`${s.demo?'DANE SYNTETYCZNE · ':''}Wersja ${s.version||'2.x'} · promień sceny ${s.radius} m · siatka ${s.x.length}×${s.y.length} · krok 3D ${s.step_m} m · krok analizy ${s.analysis_step_m} m · profil ${s.profile_radius||s.radius} m`;
  $('profile').href=`profil_${s.resource}.svg`;$('fallback').href=`scena_3d_lekka_${s.resource}.html`;
  $('bearing').value=s.azimuth;$('cover').checked=s.resource==='NMPT';$('cover').disabled=s.resource!=='NMPT';
  $('camera').value='orbit';$('eye-height').value=s.eye_height||1.7;
  if(!gl){$('status').textContent='WebGL niedostępny. Otwórz lekki podgląd bez WebGL powyżej.';return}
  function shader(type,source){const sh=gl.createShader(type);gl.shaderSource(sh,source);gl.compileShader(sh);if(!gl.getShaderParameter(sh,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(sh));return sh}
  const program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,vertexShader));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fragmentShader));gl.linkProgram(program);
  if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));gl.useProgram(program);
  const attributes=[['aPosition',3,0],['aNormal',3,12],['aColor',3,24],['aUv',2,36],['aTextured',1,44]].map(([n,size,offset])=>({location:gl.getAttribLocation(program,n),size,offset}));
  const uniforms=Object.fromEntries(['uMatrix','uVertical','uSun','uTexture','uUseTexture'].map(n=>[n,gl.getUniformLocation(program,n)]));
  let zoom=1,drag=null,pending=false,dirty=true,batches=[],objects=[],rays=[],low=0,high=1,textureReady=false,textureImage=null,observerPoint=null;
  const locator=$('locator'),locatorCtx=locator.getContext('2d');
  $('texture-status').textContent=textureUrl?'Wczytywanie ortofotomapy…':'Brak osadzonej ortofotomapy. W QGIS wybierz jej źródło i kliknij Odśwież samą scenę 3D.';
  const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array([255,255,255,255]));
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
  if(textureUrl){const image=new Image();image.onload=()=>{
    textureImage=image;const download=$('download-texture');download.href=textureUrl;download.download=`tekstura_${s.resource}.png`;download.style.display='';schedule();
    try{
      if(gl.isContextLost&&gl.isContextLost())throw Error('utracono kontekst graficzny');
      // Earlier draw errors must not be misreported as an image upload error.
      for(let i=0;i<8&&gl.getError()!==gl.NO_ERROR;i++){}
      const width=image.naturalWidth||image.width,height=image.naturalHeight||image.height;
      const maximum=Number(gl.getParameter(gl.MAX_TEXTURE_SIZE))||2048;let input=image;
      if(width>maximum||height>maximum){const factor=Math.min(maximum/width,maximum/height),resized=document.createElement('canvas');resized.width=Math.max(1,Math.floor(width*factor));resized.height=Math.max(1,Math.floor(height*factor));resized.getContext('2d').drawImage(image,0,0,resized.width,resized.height);input=resized}
      gl.bindTexture(gl.TEXTURE_2D,texture);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,input);
      const error=gl.getError();if(error!==gl.NO_ERROR)throw Error(`błąd karty graficznej ${error}`);
      textureReady=true;$('texture-option').disabled=false;dirty=dirty||$('material').value==='cover';$('material').value='texture';
      $('texture-status').textContent=`Ortofotomapa ${width||'?'} × ${height||'?'} wczytana. Kliknij na mapce, aby wybrać miejsce patrzenia.`;schedule();
    }catch(error){textureReady=false;$('texture-option').disabled=true;$('texture-status').textContent='Zdjęcie jest w HTML i na mapce, ale nie udało się nałożyć go w 3D: '+error.message+'. Możesz pobrać PNG przyciskiem powyżej.';schedule()}
  };image.onerror=()=>{$('texture-status').textContent='Nie można odczytać osadzonej ortofotomapy. Odśwież scenę w QGIS i sprawdź źródło.'};image.src=textureUrl}
  function drawLocator(){
    if(!locatorCtx)return;
    const b=s.texture_bounds||[s.x[0],s.y[s.y.length-1],s.x[s.x.length-1],s.y[0]],w=locator.width,h=locator.height;
    function pixel(x,y){return [(x-b[0])/(b[2]-b[0])*w,(b[3]-y)/(b[3]-b[1])*h]}
    locatorCtx.clearRect(0,0,w,h);locatorCtx.fillStyle='#dce5e2';locatorCtx.fillRect(0,0,w,h);
    if(textureImage)locatorCtx.drawImage(textureImage,0,0,w,h);
    else{const stride=Math.max(1,Math.ceil(Math.max(s.x.length,s.y.length)/128));for(let r=0;r<s.y.length;r+=stride)for(let c=0;c<s.x.length;c+=stride){const z=s.ground[r][c];if(z===null)continue;const color=heightColor((z-low)/(high-low||1));locatorCtx.fillStyle=`rgb(${color.map(v=>Math.round(v*255)).join(',')})`;const p=pixel(s.x[c],s.y[r]);locatorCtx.fillRect(p[0]-1,p[1]-1,Math.max(2,w*stride/s.x.length+1),Math.max(2,h*stride/s.y.length+1))}}
    const target=pixel(0,0);locatorCtx.fillStyle='#ef4761';locatorCtx.beginPath();locatorCtx.arc(target[0],target[1],5,0,Math.PI*2);locatorCtx.fill();
    if(observerPoint){const p=pixel(...observerPoint),angle=+$('bearing').value*Math.PI/180;locatorCtx.fillStyle='#1987d6';locatorCtx.beginPath();locatorCtx.arc(p[0],p[1],5,0,Math.PI*2);locatorCtx.fill();locatorCtx.strokeStyle='#1987d6';locatorCtx.lineWidth=2;locatorCtx.beginPath();locatorCtx.moveTo(p[0],p[1]);locatorCtx.lineTo(p[0]+Math.sin(angle)*18,p[1]-Math.cos(angle)*18);locatorCtx.stroke()}
  }
  function setObserver(point,aim=true){
    const pose=eyePose(s,0,point,+$('eye-height').value,0,0,$('cover').checked);
    if(pose.error){$('eye-status').textContent=pose.error;return false}
    observerPoint=point.slice();
    if(aim){const distance=Math.hypot(...point),target=s.ground_z===null?pose.eyeZ:s.ground_z+s.hub;
      $('bearing').value=(Math.atan2(-point[0],-point[1])*180/Math.PI+360)%360;
      $('tilt').value=Math.max(-89,Math.min(89,Math.atan2(target-pose.eyeZ,distance)*180/Math.PI))}
    return true;
  }
  function defaultObserver(){
    if(s.camera_observer)return setObserver(s.camera_observer);
    for(const radius of [.65,.4,.85])for(const offset of [0,25,-25,60,-60,120,180]){const a=(s.azimuth+offset)*Math.PI/180;if(setObserver([Math.sin(a)*s.radius*radius,Math.cos(a)*s.radius*radius]))return true}
    return false;
  }
  function cameraMode(){
    const eye=$('camera').value==='eye';$('vertical').disabled=eye;$('projection').disabled=eye;
    $('bearing-label').textContent=eye?'Kierunek patrzenia':'Strona';$('tilt').min=eye?-89:8;$('tilt').max=eye?89:80;
    if(eye){$('vertical').value=1;$('projection').value='perspective';$('lines').checked=false;
      if(!(observerPoint?setObserver(observerPoint):defaultObserver())){$('camera').value='orbit';cameraMode();return}}
    else{$('bearing').value=s.azimuth;$('tilt').value=28}
    schedule();
  }
  locator.addEventListener('pointerdown',event=>{const rect=locator.getBoundingClientRect(),b=s.texture_bounds||[s.x[0],s.y[s.y.length-1],s.x[s.x.length-1],s.y[0]];
    const point=[b[0]+(event.clientX-rect.left)/rect.width*(b[2]-b[0]),b[3]-(event.clientY-rect.top)/rect.height*(b[3]-b[1])];
    $('tilt').min=-89;$('tilt').max=89;if(setObserver(point)){$('camera').value='eye';cameraMode();schedule()}});
  $('camera').addEventListener('input',cameraMode);$('eye-height').addEventListener('input',()=>{if(observerPoint)setObserver(observerPoint);schedule()});
  $('look-turbine').onclick=()=>{if(observerPoint)setObserver(observerPoint);$('camera').value='eye';cameraMode()};
  function upload(mesh,mode=gl.TRIANGLES){const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,mesh.vertices,gl.STATIC_DRAW);let index=null;if(mesh.indices){index=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,index);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,mesh.indices,gl.STATIC_DRAW)}return {buffer,index,count:mesh.indices?mesh.indices.length:mesh.vertices.length/12,mode}}
  function dispose(list){for(const b of list){gl.deleteBuffer(b.buffer);if(b.index)gl.deleteBuffer(b.index)}}
  function world(p){return [p[0]/s.radius,p[1]/s.radius,(p[2]-low)/s.radius]}
  function triangle(out,a,b,c,color){const normal=normalize(cross(b.map((v,k)=>v-a[k]),c.map((v,k)=>v-a[k])));for(const p of [a,b,c])out.push(...world(p),...normal,...color,0,0,0)}
  function cylinder(out,x,y,z,height,radius,color,cone=false){for(let k=0;k<12;k++){const a=k*Math.PI/6,b=(k+1)*Math.PI/6,p=[x+radius*Math.cos(a),y+radius*Math.sin(a),z],q=[x+radius*Math.cos(b),y+radius*Math.sin(b),z];if(cone)triangle(out,p,q,[x,y,z+height],color);else{const r=[q[0],q[1],z+height],t=[p[0],p[1],z+height];triangle(out,p,q,r,color);triangle(out,p,r,t,color)}}}
  function rebuild(){
    dispose(batches);dispose(objects);dispose(rays);batches=[];objects=[];rays=[];
    const heights=$('cover').checked?s.surface:s.ground;
    low=Infinity;high=-Infinity;for(const row of heights)for(const z of row)if(z!==null){low=Math.min(low,z);high=Math.max(high,z)}
    if(!Number.isFinite(low)){low=0;high=1;$('status').textContent='Brak poprawnych wysokości w scenie';return}
    $('low').textContent=`${low.toFixed(1)} m`;$('high').textContent=`${high.toFixed(1)} m`;
    for(let r=0;r<heights.length-1;r+=128)for(let c=0;c<heights[0].length-1;c+=128){const tile=terrainTile(s,heights,r,c,Math.min(r+128,heights.length-1),Math.min(c+128,heights[0].length-1),low,high,$('material').value);if(tile.indices.length)batches.push(upload(tile))}
    const construction=[];
    if(s.ground_z!==null){cylinder(construction,0,0,s.ground_z,s.hub,Math.max(.7,s.hub*.018),[.94,.96,.97]);const z=s.ground_z+s.hub;
      for(let k=0;k<3;k++){const a=(k*120+20)*Math.PI/180,r=s.diameter/2,w=s.diameter*.018;triangle(construction,[-w,0,z],[w,0,z],[r*Math.sin(a),0,z+r*Math.cos(a)],[.98,.98,.98])}}
    if($('trees').checked&&$('cover').checked)for(const tree of s.trees||[]){cylinder(construction,tree.x,tree.y,tree.ground,tree.height*.4,.3,[.34,.23,.15]);cylinder(construction,tree.x,tree.y,tree.ground+tree.height*.3,tree.height*.7,Math.min(8,Math.max(1,tree.height*.2)),[.12,.35,.19],true)}
    if(construction.length)objects.push(upload({vertices:new Float32Array(construction)}));
    if(s.eye!==null&&s.ground_z!==null){const lines=[];for(const [delta,color] of [[s.diameter/2,[.58,.38,.82]],[0,[.94,.25,.4]],[-s.diameter/2,[.8,.58,.12]]])for(let i=0;i<100;i+=2)for(const t of [i/100,(i+1)/100]){const p=[s.observer[0]*(1-t),s.observer[1]*(1-t),s.eye+(s.ground_z+s.hub+delta-s.eye)*t];lines.push(...world(p),0,0,1,...color,0,0,0)}rays.push(upload({vertices:new Float32Array(lines)},gl.LINES))}
    $('status').textContent=`Gotowe · ${batches.reduce((n,b)=>n+b.count/3,0).toLocaleString('pl-PL')} trójkątów terenu · ${(s.trees||[]).length} symboli drzew · braki pozostają otworami`;
  }
  function bind(batch){gl.bindBuffer(gl.ARRAY_BUFFER,batch.buffer);for(const a of attributes){gl.enableVertexAttribArray(a.location);gl.vertexAttribPointer(a.location,a.size,gl.FLOAT,false,48,a.offset)}if(batch.index){gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,batch.index);gl.drawElements(batch.mode,batch.count,gl.UNSIGNED_SHORT,0)}else gl.drawArrays(batch.mode,0,batch.count)}
  function draw(){pending=false;try{
    if(dirty){rebuild();dirty=false}
    const dpr=Math.min(window.devicePixelRatio||1,2),w=canvas.clientWidth,h=canvas.clientHeight;
    if(canvas.width!==Math.round(w*dpr))canvas.width=Math.round(w*dpr);if(canvas.height!==Math.round(h*dpr))canvas.height=Math.round(h*dpr);gl.viewport(0,0,canvas.width,canvas.height);
    const bearing=+$('bearing').value,tilt=+$('tilt').value,vertical=+$('vertical').value,angle=bearing*Math.PI/180,elevation=tilt*Math.PI/180;
    $('bval').textContent=`${Math.round(bearing)}°`;$('tval').textContent=`${tilt}°`;$('vval').textContent=vertical;$('fval').textContent=`${$('fov').value}°`;
    const distance=2.8/zoom*Math.max(1,h/w);let target=[0,0,(high-low)/s.radius*vertical*.4],eye=[Math.sin(angle)*Math.cos(elevation)*distance,Math.cos(angle)*Math.cos(elevation)*distance,target[2]+Math.sin(elevation)*distance],near=.005,far=100;
    if($('camera').value==='eye'&&observerPoint){const pose=eyePose(s,low,observerPoint,+$('eye-height').value,bearing,tilt,$('cover').checked);
      if(pose.error){$('eye-status').textContent=pose.error;return}eye=pose.eye;target=pose.target;near=.1/s.radius;far=4+(high-low+s.hub+s.diameter)/s.radius;
      const origin=s.origin||[0,0];$('eye-status').textContent=`X=${(origin[0]+observerPoint[0]).toFixed(2)}, Y=${(origin[1]+observerPoint[1]).toFixed(2)} · grunt NMT ${pose.ground.toFixed(2)} m + oko ${$('eye-height').value} m = ${pose.eyeZ.toFixed(2)} m · ${s.height_system||''}`;}
    gl.uniformMatrix4fv(uniforms.uMatrix,false,multiply(projection(+$('fov').value,w/h,distance,$('projection').value==='ortho',near,far),lookAt(eye,target)));gl.uniform1f(uniforms.uVertical,vertical);
    const sun=+$('sun').value*Math.PI/180;gl.uniform3fv(uniforms.uSun,new Float32Array([Math.sin(sun)*.707,Math.cos(sun)*.707,.707]));gl.uniform1i(uniforms.uTexture,0);gl.uniform1f(uniforms.uUseTexture,textureReady&&$('material').value==='texture'?1:0);
    gl.clearColor(.83,.9,.91,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);gl.enable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(1,1);for(const b of batches)bind(b);gl.disable(gl.POLYGON_OFFSET_FILL);for(const b of objects)bind(b);
    if($('lines').checked){gl.disable(gl.DEPTH_TEST);for(const b of rays)bind(b);gl.enable(gl.DEPTH_TEST)}drawLocator();
  }catch(error){$('status').textContent='Problem renderowania: '+error.message+'. Użyj lekkiego podglądu.'}}
  function schedule(){if(!pending){pending=true;requestAnimationFrame(draw)}}
  for(const id of ['bearing','tilt','vertical','sun','projection','fov','material','cover','trees','lines'])$(id).addEventListener('input',()=>{if(['material','cover','trees'].includes(id))dirty=true;schedule()});
  $('reset').onclick=()=>{$('camera').value='orbit';cameraMode();$('bearing').value=s.azimuth;$('tilt').value=28;$('vertical').value=1;$('fov').value=45;$('projection').value='perspective';zoom=1;schedule()};
  $('save').onclick=()=>{draw();const a=document.createElement('a');a.download=`scena_3d_${s.resource}.png`;a.href=canvas.toDataURL('image/png');a.click()};
  canvas.onpointerdown=e=>{canvas.focus?.();drag={x:e.clientX,y:e.clientY,b:+$('bearing').value,t:+$('tilt').value};canvas.setPointerCapture(e.pointerId)};
  canvas.onpointermove=e=>{if(drag){const eye=$('camera').value==='eye';$('bearing').value=(drag.b+(e.clientX-drag.x)*.35+360)%360;$('tilt').value=Math.max(eye?-89:8,Math.min(eye?89:80,drag.t+(e.clientY-drag.y)*.2*(eye?-1:1)));schedule()}};
  canvas.onpointerup=canvas.onpointercancel=()=>{drag=null};canvas.addEventListener('wheel',e=>{e.preventDefault();if($('camera').value==='eye')$('fov').value=Math.max(15,Math.min(90,+$('fov').value*Math.exp(e.deltaY*.001)));else zoom=Math.max(.3,Math.min(7,zoom*Math.exp(-e.deltaY*.001)));schedule()},{passive:false});
  canvas.addEventListener('keydown',event=>{if($('camera').value!=='eye'||!observerPoint)return;const key=event.key.toLowerCase(),motion={arrowup:[1,0],w:[1,0],arrowdown:[-1,0],s:[-1,0],arrowleft:[0,-1],a:[0,-1],arrowright:[0,1],d:[0,1]}[key];if(!motion)return;event.preventDefault();const a=+$('bearing').value*Math.PI/180,step=event.shiftKey?10:2;const point=[observerPoint[0]+step*(motion[0]*Math.sin(a)+motion[1]*Math.cos(a)),observerPoint[1]+step*(motion[0]*Math.cos(a)-motion[1]*Math.sin(a))];if(setObserver(point,false))schedule()});
  canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();$('status').textContent='Utracono kontekst graficzny. Odśwież stronę albo wybierz mniejszą siatkę.'});window.addEventListener('resize',schedule);
  if(s.start_eye){$('camera').value='eye';cameraMode()}schedule();
}
if(typeof module!=='undefined'&&module.exports)module.exports={heightColor,multiply,lookAt,projection,terrainTile,vertexShader,fragmentShader,surfaceAt,eyePose};
if(typeof document!=='undefined'){try{startScene(scene,textureData)}catch(error){document.getElementById('status').textContent='Nie udało się otworzyć WebGL: '+error.message+'. Użyj lekkiego podglądu.'}}
