import React, {useEffect, useRef} from 'react';

const radius = 18;
const half = 114;
const rails = [-43,43];
const paths = [
  [-100,-70,12], [-83,-22,-14], [-54,-78,7], [-37,5,18],
  [-12,-41,-12], [6,54,14], [32,7,7], [52,85,-12], [82,48,13], [98,104,6]
];
const tau = Math.PI*2;
const unit = n => Math.max(0,Math.min(1,n));
const point = (x,y,z) => [x,y,z];

// Capsule rings include both hemispheres. Light is evaluated in camera space.
function capsule(x) {
  const rings = [];
  for (let i=0;i<=6;i++) {
    const a=-Math.PI/2+i*Math.PI/12;
    rings.push([x,-half+radius*Math.sin(a),radius*Math.cos(a),Math.sin(a),Math.cos(a)]);
  }
  for (let i=0;i<=6;i++) {
    const a=i*Math.PI/12;
    rings.push([x,half+radius*Math.sin(a),radius*Math.cos(a),Math.sin(a),Math.cos(a)]);
  }
  const mesh=[];
  for(let i=1;i<rings.length;i++) for(let j=0;j<40;j++) {
    const a=tau*j/40,b=tau*(j+1)/40;
    const vertex=(r,t)=>point(x+r[2]*Math.cos(t),r[1],r[2]*Math.sin(t));
    const prev=rings[i-1],next=rings[i],v=(a+b)/2;
    mesh.push({vertices:[vertex(prev,a),vertex(next,a),vertex(next,b),vertex(prev,b)],
      normal:[Math.cos(v)*(prev[4]+next[4])/2,(prev[3]+next[3])/2,Math.sin(v)*(prev[4]+next[4])/2]});
  }
  return mesh;
}
const mesh=rails.flatMap(capsule);
const cameraDistance=650;
// Bound both rounded rails under any rotation, including perspective enlargement.
const sceneRadius=Math.hypot(half,Math.max(...rails.map(Math.abs)))+radius+1;
const projectedDiameter=2*sceneRadius/Math.sqrt(1-(sceneRadius/cameraDistance)**2);
function bridge([start,end,bow],t) {
  const arc=Math.sin(Math.PI*t);
  return point(-43+86*t,start+(end-start)*t+bow*arc,8+arc*bow);
}
function lane(x,index,t) {
  const a=1.06+index*.43+.085*Math.sin(t*tau*1.5+index);
  return point(x+(radius+.5)*Math.cos(a),half*(1-2*t),(radius+.5)*Math.sin(a));
}

export function RouteSculpture() {
  const canvas=useRef(null),button=useRef(null),send=useRef(null);
  useEffect(()=>{
    const el=canvas.current,control=button.current,ctx=el.getContext('2d');
    if(!ctx)return;
    const motion=matchMedia('(prefers-reduced-motion: reduce)');
    let width=0,height=0,frame=0,visible=true,last=0,time=0;
    let yaw=0,pitch=0,targetX=0,targetY=0,burst=0,selected=0;
    let velocityX=0,velocityY=0,drag=null,suppressClick=false;
    const desktop=matchMedia('(min-width: 851px)');
    function render(now) {
      frame=0;
      if(!width||!height||!visible||document.hidden)return;
      const dt=Math.min(.05,(now-last)/1000);last=now;
      if(!motion.matches)time+=dt;
      if (!drag && !motion.matches) {
        // Small integration steps keep the spring stable even after a slow frame.
        const steps=Math.max(1,Math.ceil(dt*120)),step=dt/steps;
        for(let i=0;i<steps;i++){
          velocityX+=((targetX-yaw)*155-velocityX*15)*step;
          velocityY+=((targetY-pitch)*155-velocityY*15)*step;
          yaw+=velocityX*step;pitch+=velocityY*step;
        }
      } else if(!drag) {
        yaw=targetX;pitch=targetY;velocityX=velocityY=0;
      }
      const ay=.16+yaw+(motion.matches?0:.045*Math.sin(time*.65));
      const ax=-.12+pitch;
      const cy=Math.cos(ay),sy=Math.sin(ay),cx=Math.cos(ax),sx=Math.sin(ax);
      function rotate([x,y,z]) {
        const u=x*cy+z*sy,v=z*cy-x*sy,w=y*cx-v*sx;
        return [u*.866-w*.5,u*.5+w*.866,y*sx+v*cx];
      }
      const inset=Math.max(8,Math.min(width,height)*.035);
      const available=Math.max(1,Math.min(width,height)-2*inset);
      const scale=Math.min(available/projectedDiameter,desktop.matches ? Infinity : height/300);
      function project(p) {
        const [x,y,z]=rotate(p),k=scale*cameraDistance/(cameraDistance-z);
        return [width/2+x*k,height/2+y*k,z];
      }
      ctx.clearRect(0,0,width,height);
      function stroke(points,color,thickness) {
        ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));
        ctx.strokeStyle=color;ctx.lineWidth=thickness*scale;ctx.lineCap='round';ctx.stroke();
      }
      function trace(fn,start,end,color,thickness,n=20) {
        stroke(Array.from({length:n+1},(_,i)=>project(fn(start+(end-start)*i/n))),color,thickness);
      }
      const pulse=(time-burst);
      paths.forEach((p,i)=>{
        const fn=t=>bridge(p,t);
        trace(fn,0,1,i===selected?'#568ffa':'#93b6e7',i===selected?1.35:.85);
        const head=(time*.36+i*.319)%1;
        trace(fn,Math.max(0,head-.14),head,'#1673fa',2.2,5);
        if(!motion.matches&&pulse<1.3) {
          const t=unit((pulse-i*.035)*1.6);
          trace(fn,Math.max(0,t-.21),t,'#04a0df',3,7);
        }
      });
      const faces=[];
      for(const face of mesh){
        const [nx,ny,nz]=rotate(face.normal);
        if(nz<-.04)continue;
        const light=unit(-nx*.57-ny*.4+nz*.69);
        const gloss=Math.pow(unit(-nx*.32-ny*.26+nz*.91),14);
        const pts=face.vertices.map(project);
        faces.push({pts,z:pts.reduce((sum,p)=>sum+p[2],0)/4,color:`rgb(${8+34*light+102*gloss} ${41+63*light+83*gloss} ${128+96*light+31*gloss})`});
      }
      faces.sort((a,b)=>a.z-b.z);
      for(const {pts,color} of faces){
        ctx.beginPath();pts.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));
        ctx.closePath();ctx.fillStyle=ctx.strokeStyle=color;ctx.lineWidth=.55*scale;ctx.fill();ctx.stroke();
      }
      rails.forEach((x,r)=>{for(let i=0;i<4;i++){
        const fn=t=>lane(x,i,t);
        trace(fn,0,1,'rgba(197,225,255,.44)',.65);
        const t=(time*(.27+i*.025)+i*.21+r*.37)%1;
        trace(fn,Math.max(0,t-.09),t,'#e8faff',1.6,6);
      }});
      el.style.opacity='1';
      if(!motion.matches)schedule();
    }
    function schedule(){if(!frame&&visible&&!document.hidden)frame=requestAnimationFrame(render);}
    function resize(){const box=el.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);width=el.clientWidth;height=el.clientHeight;if(!box.width||!width||!height)return;
      el.width=Math.round(width*dpr);el.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);schedule();}
    function down(e) {
      if(!e.isPrimary || e.button!==0 || drag)return;
      suppressClick=false;
      drag={id:e.pointerId,x:e.clientX,y:e.clientY,yaw,pitch,last:e.timeStamp,moved:false};
      targetX=targetY=velocityX=velocityY=0;
      control.setPointerCapture(e.pointerId);
    }
    function move(e) {
      if(!drag) {
        if(e.pointerType!=='mouse'||motion.matches)return;
        const rect=control.getBoundingClientRect();
        targetX=((e.clientX-rect.left)/rect.width-.5)*.7;
        targetY=((e.clientY-rect.top)/rect.height-.5)*.45;
        return;
      }
      if(e.pointerId!==drag.id)return;
      const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
      if(!drag.moved && Math.hypot(dx,dy)<4)return;
      drag.moved=true;
      const nextX=drag.yaw+1.38*Math.tanh(dx/100);
      const nextY=drag.pitch-.84*Math.tanh(dy/90);
      const elapsed=Math.max(.008,(e.timeStamp-drag.last)/1000);
      velocityX=Math.max(-4,Math.min(4,(nextX-yaw)/elapsed));
      velocityY=Math.max(-4,Math.min(4,(nextY-pitch)/elapsed));
      yaw=nextX;pitch=nextY;drag.last=e.timeStamp;schedule();
    }
    function finish(e) {
      if(!drag||e.pointerId!==drag.id)return;
      suppressClick=drag.moved;
      if(e.timeStamp-drag.last>80||e.type==='pointercancel')velocityX=velocityY=0;
      drag=null;targetX=targetY=0;
      if(control.hasPointerCapture(e.pointerId))control.releasePointerCapture(e.pointerId);
      schedule();
    }
    function leave(){if(!drag)targetX=targetY=0;}
    send.current=(event)=>{
      if(suppressClick&&event.detail){suppressClick=false;return;}
      burst=time;selected=(selected+1)%paths.length;schedule();
    };
    const listeners={pointerdown:down,pointermove:move,pointerup:finish,pointercancel:finish,lostpointercapture:finish,pointerleave:leave};
    const resizer=new ResizeObserver(resize);resizer.observe(control);
    const observer=new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;schedule();});observer.observe(control);
    for(const [type,fn] of Object.entries(listeners))control.addEventListener(type,fn);
    motion.addEventListener('change',schedule);document.addEventListener('visibilitychange',schedule);resize();
    return ()=>{cancelAnimationFrame(frame);resizer.disconnect();observer.disconnect();for(const [type,fn] of Object.entries(listeners))control.removeEventListener(type,fn);motion.removeEventListener('change',schedule);document.removeEventListener('visibilitychange',schedule);send.current=null;};
  },[]);
  return <div className="route-art"><button ref={button} className="network-sculpture" type="button" aria-label="Отправить импульс по сетевым линиям" onClick={event=>send.current?.(event)}>
    <img src="/linea-mark.svg" alt="" aria-hidden="true"/><canvas ref={canvas} aria-hidden="true"/>
  </button></div>;
}
