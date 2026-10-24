/* Original procedural materials; no external images or network dependencies. */
'use strict';
function seededRandom(seed){let n=seed>>>0;return ()=>{n=(Math.imul(n,1664525)+1013904223)>>>0;return n/4294967296}}
function foliageAtlas(){
  const canvas=document.createElement('canvas');canvas.width=1536;canvas.height=1024;const ctx=canvas.getContext('2d');
  for(let variant=0;variant<3;variant++){
    const random=seededRandom(9281+variant*317),offset=variant*512;
    const trunk=ctx.createLinearGradient(offset+235,0,offset+265,0);trunk.addColorStop(0,'#403b2d');trunk.addColorStop(.55,'#81725a');trunk.addColorStop(1,'#514735');
    ctx.fillStyle=trunk;ctx.beginPath();ctx.moveTo(offset+235,1008);ctx.lineTo(offset+263,1008);ctx.lineTo(offset+258,390);ctx.lineTo(offset+249,348);ctx.lineTo(offset+242,510);ctx.closePath();ctx.fill();
    ctx.strokeStyle='#554d38';ctx.lineWidth=5;
    for(let i=0;i<26;i++){const x=offset+50+random()*412,y=180+random()*500;ctx.beginPath();ctx.moveTo(offset+250,640);ctx.quadraticCurveTo(offset+250+(x-offset-250)*.35,y+90,x,y);ctx.stroke()}
    // Small overlapping leaf clusters, irregular silhouette and gaps, rather than a solid sphere.
    for(let cluster=0;cluster<185;cluster++){
      const angle=random()*Math.PI*2,rad=Math.sqrt(random()),cx=256+Math.cos(angle)*205*rad,
        cy=390+Math.sin(angle)*290*rad,span=18+random()*32;
      const light=.65+.25*(1-cy/800)+random()*.2;
      for(let leaf=0;leaf<75;leaf++){
        const a=random()*Math.PI*2,r=Math.sqrt(random())*span,x=offset+cx+Math.cos(a)*r,y=cy+Math.sin(a)*r*.8;
        const green=Math.round((78+random()*62)*light),red=Math.round(green*(.42+random()*.18));
        ctx.fillStyle=`rgba(${red},${green},${Math.round(green*.28)},${.75+random()*.25})`;
        ctx.beginPath();ctx.ellipse(x,y,2+random()*4,1.5+random()*3,random()*Math.PI,0,Math.PI*2);ctx.fill();
      }
    }
  }
  const trimmed=document.createElement('canvas');trimmed.width=1536;trimmed.height=1024;const target=trimmed.getContext('2d');
  for(let variant=0;variant<3;variant++){
    const pixels=ctx.getImageData(variant*512,0,512,1024)?.data;
    if(!pixels)return canvas;
    let minX=512,minY=1024,maxX=0,maxY=0;
    for(let y=0;y<1024;y++)for(let x=0;x<512;x++)if(pixels[(y*512+x)*4+3]>4){minX=Math.min(minX,x);minY=Math.min(minY,y);maxX=Math.max(maxX,x);maxY=Math.max(maxY,y)}
    if(maxX>minX&&maxY>minY)target.drawImage(canvas,variant*512+minX,minY,maxX-minX+1,maxY-minY+1,variant*512+2,2,508,1020);
  }
  return trimmed;
}
function forestFloorTexture(){
  const canvas=document.createElement('canvas');canvas.width=canvas.height=256;const ctx=canvas.getContext('2d'),random=seededRandom(4243);
  ctx.fillStyle='#675b40';ctx.fillRect(0,0,256,256);
  for(let i=0;i<7000;i++){const r=48+Math.floor(random()*72);ctx.fillStyle=`rgb(${r},${Math.round(r*.83)},${Math.round(r*.5)})`;ctx.beginPath();ctx.ellipse(random()*256,random()*256,1+random()*3,.5+random()*1.4,random()*Math.PI,0,Math.PI*2);ctx.fill()}
  return canvas;
}
function roofPieces(face,blocks,origin){
  const output=[];
  const clip=(polygon,axis,edge,greater)=>{if(!polygon.length)return [];const result=[];let a=polygon[polygon.length-1],da=(a[axis]-edge)*(greater?1:-1);for(const b of polygon){const db=(b[axis]-edge)*(greater?1:-1);if((da>=0)!==(db>=0)){const f=da/(da-db);result.push(a.map((v,k)=>v+(b[k]-v)*f))}if(db>=0)result.push(b);a=b;da=db}return result};
  const minX=Math.min(...face.map(p=>p[0]))+origin[0],maxX=Math.max(...face.map(p=>p[0]))+origin[0],minY=Math.min(...face.map(p=>p[1]))+origin[1],maxY=Math.max(...face.map(p=>p[1]))+origin[1];
  for(const block of blocks){const b=block.bounds;if(b[0]>maxX||b[2]<minX||b[1]>maxY||b[3]<minY)continue;let poly=face;poly=clip(poly,0,b[0]-origin[0],true);poly=clip(poly,0,b[2]-origin[0],false);poly=clip(poly,1,b[1]-origin[1],true);poly=clip(poly,1,b[3]-origin[1],false);for(let i=1;i<poly.length-1;i++){const a=poly[0],p=poly[i],q=poly[i+1],area=(p[0]-a[0])*(q[1]-a[1])-(p[1]-a[1])*(q[0]-a[0]);if(Math.abs(area)>1e-7)output.push({id:block.id,face:[a,p,q]})}}
  return output;
}
function skyRenderer(gl){
  const vertex='attribute vec2 aSkyPosition;varying mediump vec2 skyUv;void main(){skyUv=aSkyPosition*.5+.5;gl_Position=vec4(aSkyPosition,1.,1.);}';
  const fragment='precision mediump float;varying mediump vec2 skyUv;void main(){vec3 low=vec3(.87,.92,.94),high=vec3(.35,.60,.80);float t=smoothstep(.05,1.,skyUv.y);gl_FragColor=vec4(mix(low,high,t),1.);}';
  const program=gl.createProgram();
  for(const [type,source] of [[gl.VERTEX_SHADER,vertex],[gl.FRAGMENT_SHADER,fragment]]){const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))return ()=>{};gl.attachShader(program,shader)}
  gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))return ()=>{};
  const location=gl.getAttribLocation(program,'aSkyPosition'),buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);
  return ()=>{gl.useProgram(program);gl.disable(gl.DEPTH_TEST);const count=Number(gl.getParameter(gl.MAX_VERTEX_ATTRIBS))||8;for(let i=0;i<count;i++)gl.disableVertexAttribArray(i);gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.enableVertexAttribArray(location);gl.vertexAttribPointer(location,2,gl.FLOAT,false,8,0);gl.drawArrays(gl.TRIANGLES,0,6)};
}
if(typeof module!=='undefined'&&module.exports)module.exports={roofPieces,seededRandom};
