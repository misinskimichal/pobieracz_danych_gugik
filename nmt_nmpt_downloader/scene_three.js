/* Three.js 0.184, bundled locally. Source coordinates: east X, north Y, up Z, metres. */
'use strict';
function startThreeScene(s,previewUrl,blocks,exportIssues){
  const T=AtlasTHREE,$=id=>document.getElementById(id),canvas=$('view');
  const renderer=new T.WebGLRenderer({canvas,antialias:true,preserveDrawingBuffer:true,alpha:false,logarithmicDepthBuffer:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));renderer.outputColorSpace=T.SRGBColorSpace;
  const world=new T.Scene();world.background=new T.Color('#b9dce9');world.fog=new T.Fog('#d7e6e8',s.radius*1.2,s.radius*3.2);
  world.add(new T.HemisphereLight(0xe5f2ff,0x66724a,2));
  const sun=new T.DirectionalLight(0xffffff,2.1);sun.position.set(-s.radius,s.radius,s.radius*2);world.add(sun);
  const camera=new T.PerspectiveCamera(45,1,.1,Math.max(5000,s.radius*8));camera.up.set(0,0,1);
  let point=null,active=(s.detail_views||[]).findIndex(v=>v.patch&&!v.error),zoom=1,dirty=true,pending=false,drag=null,low=0,high=1;
  if(s.detail_views?.[s.initial_view]?.patch&&!s.detail_views[s.initial_view].error)active=s.initial_view;
  let terrain=new T.Group(),objects=new T.Group(),forestGroup=new T.Group(),rays=new T.Group();
  world.add(terrain,objects,forestGroup,rays);
  const textures=new Map(),completed=new Set(),errors=[],materials=[],previewClones=[],leafTextures=[];
  let preview=null,previewImage=null,generation=0,treeCount=0,houseCount=0;
  const origin=s.origin||[0,0],allBounds=(s.texture_bounds||[s.x[0],s.y.at(-1),s.x.at(-1),s.y[0]]).map((v,i)=>v+origin[i%2]);
  const loader=new T.TextureLoader();
  function tune(texture){texture.colorSpace=T.SRGBColorSpace;texture.anisotropy=Math.min(8,renderer.capabilities.getMaxAnisotropy());texture.wrapS=texture.wrapT=T.ClampToEdgeWrapping;return texture;}
  function expected(){return blocks.filter(b=>b.view_index==null||b.view_index===active);}
  function photoState(){
    const total=expected().length,loaded=expected().filter(b=>textures.has(b.id)).length;
    $('texture-status').textContent=(preview||loaded)?`Zdjęcie na powierzchni 3D: ${$('photo').checked?'WŁĄCZONE':'wyłączone'} · szczegółowe kafle ${loaded}/${total}`:(previewUrl?'Wczytywanie zdjęcia na powierzchnię 3D…':'Brak ortofotomapy w pliku. Wybierz jej źródło w QGIS i przygotuj model ponownie.');
    if(errors.length||exportIssues.length)$('texture-status').textContent+=` · brakujące kafle: ${errors.length+exportIssues.length}`;
  }
  function previewFor(bounds){
    if(!preview)return null;
    const tex=preview.clone();tex.repeat.set((bounds[2]-bounds[0])/(allBounds[2]-allBounds[0]),(bounds[3]-bounds[1])/(allBounds[3]-allBounds[1]));
    tex.offset.set((bounds[0]-allBounds[0])/(allBounds[2]-allBounds[0]),(bounds[1]-allBounds[1])/(allBounds[3]-allBounds[1]));
    tex.needsUpdate=true;previewClones.push(tex);return tex;
  }
  function surfaceMaterial(id,bounds){
    const Material=$('photo-shade').checked?T.MeshLambertMaterial:T.MeshBasicMaterial;
    const material=new Material({side:T.DoubleSide,vertexColors:true});
    materials.push({material,id,bounds,fallback:null});return material;
  }
  function updateMaterials(){
    for(const entry of materials){
      const map=textures.get(entry.id)?.texture||(entry.fallback||(entry.fallback=previewFor(entry.bounds)));
      const on=$('photo').checked&&!!map;
      entry.material.map=on?map:null;entry.material.vertexColors=!on;entry.material.needsUpdate=true;
    }
  }
  function loadImages(){
    const token=++generation;
    for(const [id,data] of textures)if(data.view_index!=null&&data.view_index!==active){data.texture.dispose();textures.delete(id);completed.delete(id);}
    const queue=expected().filter(b=>!textures.has(b.id));
    function next(){
      if(token!==generation||!queue.length)return;
      const b=queue.shift();
      loader.load(b.image,texture=>{
        if(token!==generation){texture.dispose();return;}
        textures.set(b.id,{texture:tune(texture),view_index:b.view_index});completed.add(b.id);updateMaterials();photoState();schedule();next();
      },undefined,()=>{if(token!==generation)return;completed.add(b.id);errors.push({id:b.id,error:'Nie można odczytać kafla'});photoState();next();});
    }
    for(let i=0;i<4;i++)next();photoState();
  }
  if(previewUrl)loader.load(previewUrl,texture=>{
    preview=tune(texture);previewImage=texture.image;$('photo').checked=true;$('photo').disabled=false;$('show-photo').disabled=false;
    $('download-texture').href=previewUrl;$('download-texture').download=`ortofoto_${s.resource}.png`;$('download-texture').style.display='';
    updateMaterials();photoState();schedule();
  },undefined,()=>{$('texture-status').textContent='Nie udało się odczytać podglądu ortofotomapy';});
  const atlas=foliageAtlas();
  const facade=document.createElement('canvas');facade.width=facade.height=256;
  const paint=facade.getContext('2d');paint.fillStyle='#e2d9c7';paint.fillRect(0,0,256,256);
  paint.fillStyle='#b0a58f';paint.fillRect(54,52,148,154);paint.fillStyle='#7596a4';paint.fillRect(60,58,136,142);
  paint.fillStyle='#cadcdd';paint.fillRect(66,64,124,50);paint.strokeStyle='#efece0';paint.lineWidth=6;
  paint.strokeRect(60,58,136,142);paint.beginPath();paint.moveTo(128,58);paint.lineTo(128,200);paint.moveTo(60,128);paint.lineTo(196,128);paint.stroke();
  const facadeTexture=tune(new T.CanvasTexture(facade));facadeTexture.wrapS=facadeTexture.wrapT=T.RepeatWrapping;
  for(let i=0;i<3;i++){const cut=document.createElement('canvas');cut.width=Math.round(atlas.width/3);cut.height=atlas.height;cut.getContext('2d').drawImage(atlas,i*atlas.width/3,0,atlas.width/3,atlas.height,0,0,cut.width,cut.height);leafTextures.push(tune(new T.CanvasTexture(cut)));}
  function clear(group){for(const mesh of [...group.children]){group.remove(mesh);mesh.geometry?.dispose();for(const material of Array.isArray(mesh.material)?mesh.material:[mesh.material])material?.dispose();}}
  function gridMesh(model,field,b,exclude){
    const positions=[],uv=[],colors=[],indices=[],width=b.col1-b.col0+1;
    for(let r=b.row0;r<=b.row1;r++)for(let c=b.col0;c<=b.col1;c++){
      const z=field[r][c],x=model.x[c],y=model.y[r];positions.push(x,y,z??0);
      uv.push((x+origin[0]-b.bounds[0])/(b.bounds[2]-b.bounds[0]),(y+origin[1]-b.bounds[1])/(b.bounds[3]-b.bounds[1]));
      colors.push(...($('material').value==='cover'&&model.forest?.[r]?.[c]?[.15,.38,.21]:heightColor(((z??low)-low)/(high-low||1))));
    }
    for(let r=b.row0;r<b.row1;r++)for(let c=b.col0;c<b.col1;c++){
      if(exclude&&r>=exclude[0]&&r<exclude[2]&&c>=exclude[1]&&c<exclude[3])continue;
      const n=(r-b.row0)*width+c-b.col0;
      if([field[r][c],field[r+1][c],field[r][c+1]].every(z=>z!==null))indices.push(n,n+width,n+1);
      if([field[r+1][c],field[r+1][c+1],field[r][c+1]].every(z=>z!==null))indices.push(n+width,n+width+1,n+1);
    }
    const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(positions,3));g.setAttribute('uv',new T.Float32BufferAttribute(uv,2));g.setAttribute('color',new T.Float32BufferAttribute(colors,3));g.setIndex(indices);g.computeVertexNormals();
    terrain.add(new T.Mesh(g,surfaceMaterial(b.id,b.bounds)));
  }
  function addGround(model,patchExclude){
    const focus=point||s.camera_observer||[0,0],field=displaySurface(model,$('cover').checked,$('forest-objects').checked&&$('trees').checked,focus,s.detail_radius||120,$('buildings').checked);
    let plan=model.texture_grid;
    if(!plan?.length){plan=[];for(let r=0;r<model.y.length-1;r+=128)for(let c=0;c<model.x.length-1;c+=128){const r1=Math.min(r+128,model.y.length-1),c1=Math.min(c+128,model.x.length-1);plan.push({row0:r,row1:r1,col0:c,col1:c1,bounds:[model.x[c]+origin[0],model.y[r1]+origin[1],model.x[c1]+origin[0],model.y[r]+origin[1]]});}}
    for(const b of plan)gridMesh(model,field,b,patchExclude);
  }
  function faceMesh(faces,material,bounds=allBounds){
    const p=[],uv=[];
    for(const face of faces)for(let i=1;i<face.length-1;i++)for(const v of [face[0],face[i],face[i+1]]){p.push(...v);uv.push((v[0]+origin[0]-bounds[0])/(bounds[2]-bounds[0]),(v[1]+origin[1]-bounds[1])/(bounds[3]-bounds[1]));}
    const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(p,3));g.setAttribute('uv',new T.Float32BufferAttribute(uv,2));g.setAttribute('color',new T.Float32BufferAttribute(p.map(()=>1),3));g.computeVertexNormals();return new T.Mesh(g,material);
  }
  function addBuildings(){
    houseCount=0;if(!$('buildings').checked)return;
    for(const building of s.buildings||[]){
      const z=building.roof+.08,edges=building.wall_edges||building.rings.flatMap(ring=>ring.slice(0,-1).map((a,i)=>[[...a,z],[...ring[i+1],z]]));
      const walls=edges.map(([a,b])=>[[a[0],a[1],building.ground],[b[0],b[1],building.ground],[b[0],b[1],b[2]],[a[0],a[1],a[2]]]);
      const wallMesh=faceMesh(walls,new T.MeshLambertMaterial({map:facadeTexture,color:0xf4f0e7,side:T.DoubleSide})),wallUv=[];
      for(const face of walls)for(let i=1;i<face.length-1;i++)for(const v of [face[0],face[i],face[i+1]])wallUv.push(Math.hypot(v[0]-face[0][0],v[1]-face[0][1])/3.2,(v[2]-building.ground)/3.2);
      wallMesh.geometry.setAttribute('uv',new T.Float32BufferAttribute(wallUv,2));objects.add(wallMesh);
      const faces=building.roof_faces||building.roof_triangles.map(face=>face.map(p=>[...p,z]));
      const patch=active>=0?s.detail_views[active].patch:null,near=patch&&faces.every(f=>f.every(p=>p[0]>=patch.x[0]&&p[0]<=patch.x.at(-1)&&p[1]>=patch.y.at(-1)&&p[1]<=patch.y[0]));
      const plan=near?patch.texture_grid:s.texture_grid,parts=new Map();
      for(const face of faces){const pieces=plan?.length?roofPieces(face,plan,origin):[];if(!pieces.length){objects.add(faceMesh([face],surfaceMaterial(null,allBounds)));continue;}
        for(const piece of pieces){if(!parts.has(piece.id))parts.set(piece.id,[]);parts.get(piece.id).push(piece.face);}}
      for(const [id,polys] of parts){const b=blocks.find(b=>b.id===id)||plan.find(b=>b.id===id);objects.add(faceMesh(polys,surfaceMaterial(id,b.bounds),b.bounds));}
      houseCount++;
    }
  }
  function addTrees(){
    const focus=point||s.camera_observer||[0,0],limit=(s.detail_radius||120)*1.4;
    const trees=$('trees').checked?(s.trees||[]).filter(t=>Math.hypot(t.x-focus[0],t.y-focus[1])<=limit):[];treeCount=trees.length;
    for(let variant=0;variant<3;variant++){
      const selected=trees.filter((t,i)=>i%3===variant);if(!selected.length)continue;
      const geometry=new T.PlaneGeometry(1,1);geometry.rotateX(Math.PI/2);geometry.translate(0,0,.5);
      const mesh=new T.InstancedMesh(geometry,new T.MeshLambertMaterial({map:leafTextures[variant],alphaTest:.48,side:T.DoubleSide}),selected.length*3);
      const matrix=new T.Matrix4(),q=new T.Quaternion(),axis=new T.Vector3(0,0,1);let n=0;
      for(const tree of selected)for(let plane=0;plane<3;plane++){
        q.setFromAxisAngle(axis,plane*Math.PI/3+((tree.x*31+tree.y*97)%100)/200);
        matrix.compose(new T.Vector3(tree.x,tree.y,tree.ground),q,new T.Vector3(Math.max(2,tree.height*.57),1,tree.height));mesh.setMatrixAt(n++,matrix);
      }mesh.instanceMatrix.needsUpdate=true;mesh.computeBoundingSphere();forestGroup.add(mesh);
    }
  }
  function addTurbine(){
    if(s.ground_z===null)return;
    const material=new T.MeshLambertMaterial({color:0xecf0ef,side:T.DoubleSide});
    const tower=new T.Mesh(new T.CylinderGeometry(Math.max(.7,s.hub*.009),Math.max(1,s.hub*.017),s.hub,20),material);tower.rotation.x=Math.PI/2;tower.position.set(0,0,s.ground_z+s.hub/2);objects.add(tower);
    const nacelle=new T.Mesh(new T.BoxGeometry(4,7,4),material.clone());nacelle.position.set(0,0,s.ground_z+s.hub);objects.add(nacelle);
    const radius=s.diameter/2,faces=[];
    for(let i=0;i<3;i++){const a=(i*120+20)*Math.PI/180;faces.push([[.025,-.015],[.13,-.035],[.48,-.025],[1,-.003],[1,.003],[.48,.008],[.13,.025],[.025,.015]].map(([d,w])=>[radius*(d*Math.sin(a)+w*Math.cos(a)),-4,s.ground_z+s.hub+radius*(d*Math.cos(a)-w*Math.sin(a))]));}
    objects.add(faceMesh(faces,material.clone()));
  }
  function rebuild(){
    clear(terrain);clear(objects);clear(forestGroup);clear(rays);materials.length=0;for(const tex of previewClones)tex.dispose();previewClones.length=0;
    low=Infinity;high=-Infinity;for(const row of s.surface)for(const z of row)if(z!==null){low=Math.min(low,z);high=Math.max(high,z);}if(!Number.isFinite(low))throw Error('Brak wysokości w modelu');
    const patch=active>=0?s.detail_views[active].patch:null;addGround(s,patch?.coarse);if(patch)addGround({...s,...patch});
    addBuildings();addTrees();addTurbine();updateMaterials();
    if(s.eye!==null&&s.ground_z!==null)for(const [delta,color] of [[s.diameter/2,0x9666d1],[0,0xf05673],[-s.diameter/2,0xd3a333]]){const g=new T.BufferGeometry().setFromPoints([new T.Vector3(...s.observer,s.eye),new T.Vector3(0,0,s.ground_z+s.hub+delta)]);rays.add(new T.Line(g,new T.LineDashedMaterial({color,dashSize:10,gapSize:6,depthTest:false})));rays.children.at(-1).computeLineDistances();}
    $('status').textContent=`Model 3D · ${treeCount} koron w otoczeniu · ${houseCount} budynków · Three.js ${T.REVISION}`;
    $('context-status').textContent=(s.context_notes||[]).join(' ')+(!s.trees?.length?' Brak warstwy drzew/lasów: roślinność pozostaje powierzchnią NMPT.':'')+(!s.buildings?.length?' Brak obrysów budynków: dachy pozostają powierzchnią NMPT.':'');
    $('low').textContent=low.toFixed(1)+' m';$('high').textContent=high.toFixed(1)+' m';dirty=false;
  }
  function eyeModel(p){const patch=active>=0?s.detail_views[active].patch:null;return patch&&p[0]>=patch.x[0]&&p[0]<=patch.x.at(-1)&&p[1]>=patch.y.at(-1)&&p[1]<=patch.y[0]?{...s,...patch}:s;}
  function observer(p,aim=true){
    const model=eyeModel(p),pose=eyePose(model,0,p,+$('eye-height').value,0,0,$('cover').checked);
    if(pose.error){$('eye-status').textContent=pose.error;return false;}
    point=p.slice();dirty=true;
    if(aim){$('bearing').value=(Math.atan2(-p[0],-p[1])*180/Math.PI+360)%360;$('tilt').value=Math.max(-89,Math.min(89,Math.atan2((s.ground_z||pose.eyeZ)+s.hub-pose.eyeZ,Math.hypot(...p))*180/Math.PI));}
    return true;
  }
  function defaultObserver(){if(active>=0){const v=s.detail_views[active];$('eye-height').value=v.eye;return observer(v.point);}if(s.camera_observer&&observer(s.camera_observer))return true;for(const scale of [.65,.4,.85])for(const d of [0,25,-25,90,180]){const a=(s.azimuth+d)*Math.PI/180;if(observer([Math.sin(a)*s.radius*scale,Math.cos(a)*s.radius*scale]))return true;}return false;}
  function cameraMode(){const eye=$('camera').value==='eye';$('tilt').min=eye?-89:8;$('tilt').max=eye?89:85;$('bearing-label').textContent=eye?'Kierunek':'Strona';if(eye){$('vertical').value=1;$('projection').value='perspective';$('lines').checked=false;if(!(point?observer(point):defaultObserver())){$('camera').value='orbit';$('tilt').min=8;$('tilt').value=28;}}else $('tilt').value=28;schedule();}
  function drawLocator(){const c=$('locator'),ctx=c.getContext('2d'),b=s.texture_bounds;ctx.clearRect(0,0,c.width,c.height);ctx.fillStyle='#cedbce';ctx.fillRect(0,0,c.width,c.height);if(previewImage)ctx.drawImage(previewImage,0,0,c.width,c.height);const px=(x,y)=>[(x-b[0])/(b[2]-b[0])*c.width,(b[3]-y)/(b[3]-b[1])*c.height];for(const [p,color] of [[[0,0],'#f04464'],[point,'#218ce4']])if(p){const [x,y]=px(...p);ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,5,0,Math.PI*2);ctx.fill();if(p===point){const a=+$('bearing').value*Math.PI/180;ctx.strokeStyle=color;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+20*Math.sin(a),y-20*Math.cos(a));ctx.stroke();}}}
  function draw(){pending=false;try{
    if(dirty)rebuild();const w=canvas.clientWidth,h=canvas.clientHeight;renderer.setSize(w,h,false);
    camera.fov=+$('fov').value;camera.aspect=w/h;camera.updateProjectionMatrix();
    const a=+$('bearing').value*Math.PI/180,p=+$('tilt').value*Math.PI/180;
    if($('camera').value==='eye'&&point){const pose=eyePose(eyeModel(point),0,point,+$('eye-height').value,+$('bearing').value,+$('tilt').value,$('cover').checked);if(pose.error){$('eye-status').textContent=pose.error;return;}camera.position.set(point[0],point[1],pose.eyeZ);camera.lookAt(point[0]+Math.sin(a)*Math.cos(p),point[1]+Math.cos(a)*Math.cos(p),pose.eyeZ+Math.sin(p));$('eye-status').textContent=`X=${(origin[0]+point[0]).toFixed(2)}, Y=${(origin[1]+point[1]).toFixed(2)} · aparat ${pose.eyeZ.toFixed(2)} m · ${s.height_system||''}`;}
    else{const d=s.radius*2.5/zoom,target=low+(high-low)*.5*+$('vertical').value;camera.position.set(Math.sin(a)*Math.cos(p)*d,Math.cos(a)*Math.cos(p)*d,target+Math.sin(p)*d);camera.lookAt(0,0,target);}
    for(const group of [terrain,objects,forestGroup,rays]){group.scale.z=+$('vertical').value;group.position.z=low*(1-group.scale.z);}rays.visible=$('lines').checked;
    const light=+$('sun').value*Math.PI/180;sun.position.set(Math.sin(light)*s.radius,Math.cos(light)*s.radius,s.radius*1.5);
    let renderCamera=camera;
    if($('projection').value==='ortho'&&$('camera').value!=='eye'){
      const half=s.radius*1.3/zoom,ortho=new T.OrthographicCamera(-half*w/h,half*w/h,half,-half,.1,camera.far);ortho.up.set(0,0,1);ortho.position.copy(camera.position);ortho.lookAt(0,0,low+(high-low)*.5*+$('vertical').value);renderCamera=ortho;
    }
    renderer.render(world,renderCamera);drawLocator();$('bval').textContent=Math.round(+$('bearing').value)+'°';$('tval').textContent=$('tilt').value+'°';$('vval').textContent=$('vertical').value;$('fval').textContent=$('fov').value+'°';
  }catch(error){$('status').textContent='Błąd modelu 3D: '+error.message;}}
  function schedule(){if(!pending){pending=true;requestAnimationFrame(draw);}}
  $('title').textContent=`${s.resource} · model 3D otoczenia turbiny ${s.turbine}`;
  $('info').textContent=`${s.demo?'PRZYKŁAD SYNTETYCZNY · ':''}wersja ${s.version} · Three.js ${T.REVISION} · teren ${s.step_m} m · analiza ${s.analysis_step_m} m`;
  $('cover').checked=s.resource==='NMPT';$('cover').disabled=s.resource!=='NMPT';$('bearing').value=s.azimuth;$('eye-height').value=s.eye_height||1.7;
  const hasForest=s.trees?.length&&(s.forest||[]).some(row=>row.some(v=>v===1));$('forest-objects').checked=!!hasForest;$('forest-objects').disabled=!hasForest;
  $('trees').disabled=!s.trees?.length;$('buildings').disabled=!s.buildings?.length;
  $('profile').href=`profil_${s.resource}.svg`;$('fallback').href=`scena_3d_lekka_${s.resource}.html`;
  for(let i=0;i<(s.detail_views||[]).length;i++){const v=s.detail_views[i],o=document.createElement('option');o.value=i;o.textContent=v.name+(v.error?' · niedostępne':'');o.disabled=!!v.error;$('viewpoint').appendChild(o);}$('viewpoint').value=active;
  $('viewpoint').onchange=()=>{active=+$('viewpoint').value;if(active>=0){$('eye-height').value=s.detail_views[active].eye;observer(s.detail_views[active].point);$('camera').value='eye';}dirty=true;loadImages();cameraMode();};
  $('camera').oninput=cameraMode;$('eye-height').oninput=()=>{if(point)observer(point);schedule();};
  $('locator').onpointerdown=e=>{const r=$('locator').getBoundingClientRect(),b=s.texture_bounds,p=[b[0]+(e.clientX-r.left)/r.width*(b[2]-b[0]),b[3]-(e.clientY-r.top)/r.height*(b[3]-b[1])];$('tilt').min=-89;$('tilt').max=89;if(observer(p)){$('camera').value='eye';cameraMode();}};
  for(const id of ['bearing','tilt','vertical','sun','projection','fov','material','cover','trees','buildings','lines','forest-objects','photo-shade'])$(id).addEventListener('input',()=>{if(['material','cover','trees','buildings','forest-objects','photo-shade'].includes(id))dirty=true;schedule();});
  $('photo').oninput=()=>{updateMaterials();photoState();schedule();};$('show-photo').onclick=()=>{$('photo').checked=true;updateMaterials();photoState();schedule();};
  $('photo-top').onclick=()=>{$('camera').value='orbit';$('tilt').value=85;zoom=1;schedule();};
  $('look-turbine').onclick=()=>{if(point)observer(point);$('camera').value='eye';cameraMode();};
  $('object-view').disabled=!s.trees?.length&&!s.buildings?.length;$('object-view').onclick=()=>{$('cover').checked=false;$('trees').checked=true;$('buildings').checked=true;dirty=true;schedule();};
  $('reset').onclick=()=>{$('camera').value='orbit';$('bearing').value=s.azimuth;$('tilt').value=28;$('vertical').value=1;$('fov').value=45;zoom=1;schedule();};
  $('save').onclick=()=>{draw();const a=document.createElement('a');a.href=canvas.toDataURL('image/png');a.download=`model_3d_${s.resource}.png`;a.click();};
  canvas.onpointerdown=e=>{if(e.button!==0)return;canvas.focus();drag={x:e.clientX,y:e.clientY,b:+$('bearing').value,t:+$('tilt').value};canvas.setPointerCapture(e.pointerId);};
  canvas.onpointermove=e=>{if(drag){const eye=$('camera').value==='eye';$('bearing').value=(drag.b+(e.clientX-drag.x)*.3+360)%360;$('tilt').value=Math.max(eye?-89:8,Math.min(eye?89:85,drag.t+(e.clientY-drag.y)*.2*(eye?-1:1)));schedule();}};
  canvas.onpointerup=canvas.onpointercancel=()=>{drag=null;};canvas.onwheel=e=>{e.preventDefault();if($('camera').value==='eye')$('fov').value=Math.max(15,Math.min(90,+$('fov').value*Math.exp(e.deltaY*.001)));else zoom=Math.max(.3,Math.min(7,zoom*Math.exp(-e.deltaY*.001)));schedule();};
  canvas.onkeydown=e=>{if($('camera').value!=='eye'||!point)return;const motion={w:[1,0],arrowup:[1,0],s:[-1,0],arrowdown:[-1,0],a:[0,-1],arrowleft:[0,-1],d:[0,1],arrowright:[0,1]}[e.key.toLowerCase()];if(!motion)return;e.preventDefault();const a=+$('bearing').value*Math.PI/180,d=e.shiftKey?10:2;observer([point[0]+d*(motion[0]*Math.sin(a)+motion[1]*Math.cos(a)),point[1]+d*(motion[0]*Math.cos(a)-motion[1]*Math.sin(a))],false);schedule();};
  canvas.sceneDiagnostics=()=>({renderer:'Three.js '+T.REVISION,version:s.version,resource:s.resource,preview_loaded:!!preview,photo_enabled:$('photo').checked,
    tiles_expected:expected().length,tiles_loaded:expected().filter(b=>textures.has(b.id)).length,tiles_completed:expected().filter(b=>completed.has(b.id)).length,
    export_tiles_expected:blocks.length,export_errors:exportIssues,tile_errors:errors,max_texture_size:renderer.capabilities.maxTextureSize,
    forest_presentation:$('forest-objects').checked,continuous_surface:$('cover').checked,tree_symbols:s.trees?.length||0,building_symbols:s.buildings?.length||0,
    rendered_trees:treeCount,rendered_buildings:houseCount,mapped_meshes:materials.filter(m=>!!m.material.map).length,texture_status:$('texture-status').textContent,
    render_status:$('status').textContent,camera:$('camera').value,active_view:active,gl_error:renderer.getContext().getError()});
  $('diagnostics').onclick=()=>{const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify(canvas.sceneDiagnostics(),null,2)],{type:'application/json'}));a.href=url;a.download='diagnostyka_widoku_3d.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();$('status').textContent='Utracono kontekst graficzny. Odśwież stronę lub wybierz mniejszy model.';});
  window.addEventListener('resize',schedule);loadImages();if(s.start_eye){$('camera').value='eye';cameraMode();}schedule();
}
if(typeof document!=='undefined'){
  try{startThreeScene(scene,textureData,textureTiles,textureTileIssues);}
  catch(error){
    const old=document.getElementById('view'),fresh=old.cloneNode(false);old.replaceWith(fresh);
    document.getElementById('info').textContent='Tryb zgodności WebGL 1: '+error.message;
    try{startScene(scene,textureData,textureTiles,textureTileIssues);}catch(fallback){document.getElementById('status').textContent='Nie można uruchomić grafiki 3D: '+fallback.message;}
  }
}
