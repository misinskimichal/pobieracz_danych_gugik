/* Perspective camera and bounded canvas renderer for an offline, user-owned photograph. */
'use strict';
const PhotoMontageMath = (() => {
  const rad = Math.PI / 180, dot = (a,b) => a.reduce((v,x,i)=>v+x*b[i],0);
  const add = (a,b,s=1) => a.map((x,i)=>x+s*b[i]);
  const clamp = (x,a,b) => Math.max(a,Math.min(b,x));
  function basis(heading,pitch,roll) {
    const h=heading*rad,p=pitch*rad,r=roll*rad;
    const f=[Math.sin(h)*Math.cos(p),Math.cos(h)*Math.cos(p),Math.sin(p)];
    const right=[Math.cos(h),-Math.sin(h),0],up=[-Math.sin(h)*Math.sin(p),-Math.cos(h)*Math.sin(p),Math.cos(p)];
    return {f,r:add(right.map(x=>x*Math.cos(r)),up,Math.sin(r)),u:add(up.map(x=>x*Math.cos(r)),right,-Math.sin(r))};
  }
  function project(point,camera,pose,width,height,curvature=false) {
    const b=basis(pose.heading,pose.pitch,pose.roll),d=[point[0]-camera.x,point[1]-camera.y,point[2]-camera.z];
    if(curvature)d[2]-=(6/7)*(d[0]*d[0]+d[1]*d[1])/12756274;
    const depth=dot(d,b.f),focal=width/(2*Math.tan(pose.fov*rad/2));
    if(depth<=.5)return null;
    return {x:width/2+focal*dot(d,b.r)/depth,y:height/2-focal*dot(d,b.u)/depth,depth};
  }
  function ray(x,y,pose,width,height) {
    const b=basis(pose.heading,pose.pitch,pose.roll),focal=width/(2*Math.tan(pose.fov*rad/2));
    return add(add(b.f,b.r,(x-width/2)/focal),b.u,(height/2-y)/focal);
  }
  function horizonAngle(horizon,bearing) {
    if(!horizon)return null;
    const lo=horizon.bearings[0],hi=horizon.bearings[horizon.bearings.length-1],mid=(lo+hi)/2;
    bearing=mid+Math.atan2(Math.sin(bearing-mid),Math.cos(bearing-mid));
    const k=(bearing-lo)/(hi-lo)*(horizon.bearings.length-1);
    if(k<0||k>horizon.bearings.length-1)return null;
    const i=Math.min(Math.floor(k),horizon.bearings.length-2),f=k-i;
    if(horizon.unknown[i]||horizon.unknown[i+1]||horizon.angles[i]===null||horizon.angles[i+1]===null)return null;
    return horizon.angles[i]*(1-f)+horizon.angles[i+1]*f;
  }
  function geometry(turbine,yaw,phase) {
    const faces=[],center=[turbine.x,turbine.y,turbine.ground],hub=add(center,[0,0,turbine.hub]);
    const radius=turbine.diameter/2,axis=[Math.sin(yaw*rad),Math.cos(yaw*rad),0],side=[Math.cos(yaw*rad),-Math.sin(yaw*rad),0];
    function face(points,color){faces.push({points,color})}
    const bottom=Math.max(1.2,turbine.hub*.017),top=bottom*.55;
    for(let i=0;i<16;i++) {
      const a=i/16*Math.PI*2,b=(i+1)/16*Math.PI*2,c=200+Math.round(32*Math.cos(a-.8));
      face([[center[0]+bottom*Math.cos(a),center[1]+bottom*Math.sin(a),center[2]],
            [center[0]+bottom*Math.cos(b),center[1]+bottom*Math.sin(b),center[2]],
            [hub[0]+top*Math.cos(b),hub[1]+top*Math.sin(b),hub[2]],
            [hub[0]+top*Math.cos(a),hub[1]+top*Math.sin(a),hub[2]]],`rgb(${c},${c+2},${c+3})`);
    }
    // A small oriented nacelle; dimensions are illustrative, never a manufacturer model.
    const w=bottom*.9,z=bottom*.75,l=bottom*2.4;
    const corner=(s,a,u)=>add(add(add(hub,side,s*w),axis,a*l),[0,0,u*z]);
    const corners=[corner(-1,-1,-1),corner(1,-1,-1),corner(1,1,-1),corner(-1,1,-1),corner(-1,-1,1),corner(1,-1,1),corner(1,1,1),corner(-1,1,1)];
    for(const [ids,color] of [[[0,1,2,3],'#a5b0b5'],[[4,7,6,5],'#eef0ed'],[[0,4,5,1],'#c3cccd'],[[1,5,6,2],'#dce2e1'],[[2,6,7,3],'#b2bec2'],[[3,7,4,0],'#d2d9d9']])face(ids.map(i=>corners[i]),color);
    const rotor=add(hub,axis,l*1.05);
    if(radius>0)for(let i=0;i<3;i++) {
      const angle=(phase+i*120)*rad;
      const along=add(side.map(v=>v*Math.sin(angle)),[0,0,Math.cos(angle)]);
      const across=add(side.map(v=>v*Math.cos(angle)),[0,0,-Math.sin(angle)]);
      const outline=[[.025,-.015],[.13,-.035],[.48,-.025],[1,-.003],[1,.003],[.48,.008],[.13,.025],[.025,.015]];
      face(outline.map(([d,s])=>add(add(rotor,along,d*radius),across,s*radius)),'#e7ecea');
    }
    return faces;
  }
  return {rad,dot,add,clamp,basis,project,ray,horizonAngle,geometry};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=PhotoMontageMath;

if(typeof document!=='undefined') (()=>{
  const M=PhotoMontageMath,scene=photoScene,$=id=>document.getElementById(id),canvas=$('photo'),image=new Image();
  const poseKeys=['heading','pitch','roll','fov','yaw','phase','opacity'];
  const initial=Object.assign({yaw:(scene.photo.heading+180)%360,phase:20,opacity:1},scene.photo);
  let strokes=Array.isArray(initial.mask_strokes)?initial.mask_strokes:[],pending=false,drag=null,loaded=false,lastStats={};
  let maskPointCount=strokes.reduce((count,s)=>count+s.points.length,0);
  const camera=scene.camera,rect=()=>canvas.getBoundingClientRect();
  for(const key of poseKeys)$(key).value=initial[key];
  if(scene.occupied){$('occlusion').checked=false;$('occlusion').disabled=true;}
  $('warnings').textContent=(scene.photo.warnings||[]).concat((scene.photo.skipped||[]).map(t=>t.id+': '+t.reason)).join('\n');
  function pose(){
    const p={};for(const k of poseKeys)p[k]=Number($(k).value);
    for(const k of ['heading','yaw','phase'])p[k]=((p[k]%360)+360)%360;
    p.fov=M.clamp(p.fov,10,140);p.pitch=M.clamp(p.pitch,-85,85);p.roll=M.clamp(p.roll,-45,45);p.opacity=M.clamp(p.opacity,0,1);
    return p;
  }
  function worldCamera(point,p) {
    const b=M.basis(p.heading,p.pitch,p.roll),d=[point[0]-camera.x,point[1]-camera.y,point[2]-camera.z];
    if(scene.curvature)d[2]-=(6/7)*(d[0]*d[0]+d[1]*d[1])/12756274;
    return [M.dot(d,b.r),M.dot(d,b.u),M.dot(d,b.f)];
  }
  function clipNear(points) {
    const result=[];
    for(let i=0;i<points.length;i++){
      const a=points[i],b=points[(i+1)%points.length],ia=a[2]>=.5,ib=b[2]>=.5;
      if(ia)result.push(a);
      if(ia!==ib){const f=(.5-a[2])/(b[2]-a[2]);result.push(a.map((v,j)=>v+(b[j]-v)*f));}
    }return result;
  }
  function targetLayer(target,p,width,height) {
    const focal=width/(2*Math.tan(p.fov*M.rad/2));
    const faces=M.geometry(target,p.yaw,p.phase).map(face=>{
      const points=clipNear(face.points.map(point=>worldCamera(point,p)));
      return {color:face.color,depth:points.length?points.reduce((s,v)=>s+v[2],0)/points.length:0,
              points:points.map(v=>({x:width/2+focal*v[0]/v[2],y:height/2-focal*v[1]/v[2]}))};
    }).filter(f=>f.points.length>=3).sort((a,b)=>b.depth-a.depth);
    const all=faces.flatMap(f=>f.points);if(!all.length)return null;
    const x0=M.clamp(Math.floor(Math.min(...all.map(v=>v.x)))-2,0,width),y0=M.clamp(Math.floor(Math.min(...all.map(v=>v.y)))-2,0,height);
    const x1=M.clamp(Math.ceil(Math.max(...all.map(v=>v.x)))+2,0,width),y1=M.clamp(Math.ceil(Math.max(...all.map(v=>v.y)))+2,0,height);
    if(x1<=x0||y1<=y0)return null;
    const layer=document.createElement('canvas');layer.width=x1-x0;layer.height=y1-y0;
    const ctx=layer.getContext('2d',{willReadFrequently:true});ctx.translate(-x0,-y0);
    for(const face of faces){ctx.beginPath();face.points.forEach((v,i)=>i?ctx.lineTo(v.x,v.y):ctx.moveTo(v.x,v.y));ctx.closePath();ctx.fillStyle=face.color;ctx.fill();}
    let hidden=0;
    if($('occlusion').checked&&target.horizon){
      const pixels=ctx.getImageData(0,0,layer.width,layer.height),b=M.basis(p.heading,p.pitch,p.roll);
      for(let y=0;y<layer.height;y++)for(let x=0;x<layer.width;x++){
        const index=(y*layer.width+x)*4;if(!pixels.data[index+3])continue;
        const u=(x+x0+.5-width/2)/focal,v=(height/2-y-y0-.5)/focal;
        const east=b.f[0]+u*b.r[0]+v*b.u[0],north=b.f[1]+u*b.r[1]+v*b.u[1],up=b.f[2]+u*b.r[2]+v*b.u[2];
        const angle=M.horizonAngle(target.horizon,Math.atan2(east,north));
        if(angle!==null&&Math.atan2(up,Math.hypot(east,north))<angle){pixels.data[index+3]=0;hidden++;}
      }ctx.putImageData(pixels,0,0);
    }
    return {layer,x:x0,y:y0,hidden};
  }
  function applyStrokes(context,width,height){
    context.save();context.lineCap=context.lineJoin='round';
    for(const stroke of strokes){
      if(!stroke.points?.length)continue;
      context.globalCompositeOperation=stroke.mode==='hide'?'destination-out':'source-over';
      context.strokeStyle=context.fillStyle='#fff';context.lineWidth=Math.max(.1,stroke.radius*width*2);
      context.beginPath();const points=stroke.points;
      points.forEach(([x,y],i)=>i?context.lineTo(x*width,y*height):context.moveTo(x*width,y*height));
      if(points.length===1){context.arc(points[0][0]*width,points[0][1]*height,context.lineWidth/2,0,2*Math.PI);context.fill();}else context.stroke();
    }context.restore();
  }
  function render(destination,full=false){
    if(!loaded)return;
    const scale=full?1:Math.min(1,2200/image.naturalWidth),width=Math.round(image.naturalWidth*scale),height=Math.round(image.naturalHeight*scale);
    destination.width=width;destination.height=height;const context=destination.getContext('2d');context.drawImage(image,0,0,width,height);
    const p=pose(),overlay=document.createElement('canvas');overlay.width=width;overlay.height=height;const oc=overlay.getContext('2d');
    let inFrame=0,hidden=0;
    if($('turbines').checked)for(const target of [...scene.targets].sort((a,b)=>b.distance-a.distance)){
      const result=targetLayer(target,p,width,height);if(!result)continue;
      inFrame++;hidden+=result.hidden;oc.drawImage(result.layer,result.x,result.y);
      if($('labels').checked){const at=M.project([target.x,target.y,target.ground+target.hub+target.diameter/2+5],camera,p,width,height,scene.curvature);
        if(at){oc.font=`${Math.max(12,width/120)}px system-ui`;oc.strokeStyle='#15303b';oc.lineWidth=3;oc.strokeText(target.id,at.x,at.y);oc.fillStyle='#fff';oc.fillText(target.id,at.x,at.y);}}
      result.layer.width=result.layer.height=0;
    }
    let mask=null;
    if(strokes.length){mask=document.createElement('canvas');mask.width=width;mask.height=height;const mc=mask.getContext('2d');mc.fillStyle='#fff';mc.fillRect(0,0,width,height);applyStrokes(mc,width,height);oc.globalCompositeOperation='destination-in';oc.drawImage(mask,0,0);}
    context.globalAlpha=p.opacity;context.drawImage(overlay,0,0);context.globalAlpha=1;overlay.width=overlay.height=0;
    if(mask){
      if(!full&&$('show-mask').checked&&['hide','restore'].includes($('mode').value)){
        const mc=mask.getContext('2d');mc.globalCompositeOperation='source-out';mc.fillStyle='rgba(255,75,95,.3)';mc.fillRect(0,0,width,height);context.drawImage(mask,0,0);
      }mask.width=mask.height=0;
    }
    if(!full&&$('guides').checked){
      context.save();context.strokeStyle='#84ffe3';context.lineWidth=1.5;context.setLineDash([8,6]);context.beginPath();
      for(let i=0;i<=180;i++){const a=(p.heading-89+i*178/180)*M.rad,q=M.project([camera.x+1000*Math.sin(a),camera.y+1000*Math.cos(a),camera.z],camera,p,width,height,false);if(q)i?context.lineTo(q.x,q.y):context.moveTo(q.x,q.y);}
      context.stroke();context.setLineDash([]);context.beginPath();context.moveTo(width/2-12,height/2);context.lineTo(width/2+12,height/2);context.moveTo(width/2,height/2-12);context.lineTo(width/2,height/2+12);context.stroke();context.restore();
    }
    lastStats={inFrame,hidden,strokes:strokes.length,width,height};
    $('status').textContent=`${scene.photo.resource} · oko ${scene.photo.eye} m nad NMT · ${inFrame}/${scene.targets.length} turbin w kadrze · ${$('turbines').checked?'fotomontaż':'zdjęcie bez turbin'}`;
    $('summary').textContent=`Zdjęcie ${image.naturalWidth} × ${image.naturalHeight} px. Kierunek względem siatki EPSG:2180. ${scene.photo.fov_source||'Kąt widzenia dopasowywany ręcznie.'}\nDopasowanie jest poglądowe; sprawdź kierunek, kąt widzenia, datę modelu i przesłanianie.`;
    canvas.photoDiagnostics=()=>({...lastStats,pose:pose(),loaded,sourceWidth:image.naturalWidth,sourceHeight:image.naturalHeight});
  }
  function redraw(){if(!pending){pending=true;requestAnimationFrame(()=>{pending=false;render(canvas);});}}
  for(const id of [...poseKeys,'turbines','occlusion','guides','labels','show-mask','mode'])$(id).addEventListener('input',redraw);
  $('aim').onclick=()=>{const t=scene.targets[0];$('heading').value=((Math.atan2(t.x-camera.x,t.y-camera.y)/M.rad+360)%360).toFixed(2);redraw();};
  $('reset').onclick=()=>{for(const k of poseKeys)$(k).value=initial[k];redraw();};
  $('undo').onclick=()=>{maskPointCount-=(strokes.pop()?.points.length||0);redraw();};$('clear').onclick=()=>{strokes=[];maskPointCount=0;redraw();};
  function position(event){const box=rect();return [M.clamp((event.clientX-box.left)/box.width,0,1),M.clamp((event.clientY-box.top)/box.height,0,1)];}
  canvas.onpointerdown=event=>{
    if(!loaded||event.button!==0||$('mode').value==='locked')return;canvas.setPointerCapture(event.pointerId);
    if($('mode').value==='camera')drag={x:event.clientX,y:event.clientY,pose:pose()};
    else{if(strokes.length>=2000||maskPointCount>=200000){$('status').textContent='Limit maski: 2000 pociągnięć / 200 000 punktów. Usuń część maski.';return;}
      const stroke={mode:$('mode').value,radius:Math.min(1,Number($('brush').value)/rect().width/2),points:[position(event)]};strokes.push(stroke);maskPointCount++;drag={stroke};redraw();}
  };
  canvas.onpointermove=event=>{
    if(!drag)return;
    if(drag.stroke){if(drag.stroke.points.length<10000&&maskPointCount<200000){drag.stroke.points.push(position(event));maskPointCount++;}}
    else{
      const factor=drag.pose.fov/rect().width;$('heading').value=((drag.pose.heading-(event.clientX-drag.x)*factor)%360+360)%360;
      $('pitch').value=M.clamp(drag.pose.pitch+(event.clientY-drag.y)*factor,-85,85);
    }redraw();
  };
  canvas.onpointerup=canvas.onpointercancel=()=>{drag=null;};
  function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
  $('settings').onclick=()=>{
    const data={photo_id:scene.photo.id,source_sha256:scene.photo.source_sha256,version:scene.version,...pose(),mask_strokes:strokes};
    download(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),'dopasowanie_'+scene.photo.id+'.json');
  };
  $('save').onclick=async()=>{
    $('save').disabled=true;$('progress').textContent='Przygotowanie PNG w rozdzielczości zdjęcia…';
    await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);
    try{const output=document.createElement('canvas');render(output,true);const blob=await new Promise(resolve=>output.toBlob(resolve,'image/png'));
      if(!blob)throw new Error('Nie udało się utworzyć PNG');download(blob,'fotomontaz_'+scene.photo.id+'.png');output.width=output.height=0;$('progress').textContent='PNG przygotowany.';
    }catch(error){$('progress').textContent='Błąd eksportu: '+error.message;}finally{$('save').disabled=false;}
  };
  image.onload=()=>{loaded=true;render(canvas);};image.onerror=()=>{$('status').textContent='Nie można odczytać osadzonego zdjęcia.';};image.src=scene.image;
})();
