import {useEffect} from 'react';
import {gsap} from 'gsap';
import Lenis from 'lenis';
import 'lenis/dist/lenis.css';

export function useScenarioMotion(panel, entered) {
  useEffect(()=>{
    const media=gsap.matchMedia();
    media.add('(pointer:fine) and (prefers-reduced-motion:no-preference)',()=>{
      const scroll=new Lenis({autoRaf:true,lerp:.14,syncTouch:false});
      return ()=>scroll.destroy();
    });
    return ()=>media.revert();
  },[]);

  useEffect(()=>{
    if(!entered)return;
    const media=gsap.matchMedia();
    media.add('(prefers-reduced-motion:no-preference)',()=>{
      const art=panel.current.querySelector('.scenario-stage');
      let active=true,tween;
      gsap.set(art,{opacity:0,y:22,scale:.94});
      Promise.allSettled([...art.querySelectorAll('img')].map(img=>img.decode())).then(()=>{
        if(active)tween=gsap.to(art,{opacity:1,y:0,scale:1,duration:.56,ease:'power3.out',clearProps:'opacity,transform'});
      });
      return ()=>{active=false;tween?.kill();};
    });
    return ()=>media.revert();
  },[panel,entered]);

  useEffect(()=>{
    if(!entered)return;
    const media=gsap.matchMedia();
    media.add('(min-width:851px) and (pointer:fine) and (prefers-reduced-motion:no-preference)',()=>{
      let disposed=false,effect;
      const host=panel.current.querySelector('.scenario-network');
      Promise.all([import('three'),import('vanta/src/vanta.net.js')]).then(([THREE,{default:net}])=>{
        if(!disposed)effect=net({el:host,THREE,color:0x416bb8,backgroundColor:0xdbe7fc,
          points:5,spacing:19,maxDistance:24,showDots:false,mouseControls:false,touchControls:false,
          gyroControls:false,scale:2,minWidth:1,minHeight:1});
      }).catch(()=>{/* The panel keeps its CSS background when WebGL is unavailable. */});
      return ()=>{disposed=true;effect?.destroy();};
    });
    return ()=>media.revert();
  },[panel,entered]);
}
