import React, {useLayoutEffect, useEffect, useRef, useState} from 'react';
import {ArrowDown, ArrowUpRight, ArrowRight, Link2, Play, Pause, Gamepad2, MessageCircle, CreditCard, Monitor, Globe2} from 'lucide-react';

// Presentation only: motion never owns application state or navigation.
export function usePageMotion(root) {
  useEffect(() => {
    const element = root.current;
    if (!element) return;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    let observer;
    let frame = 0;
    const art = element.querySelector('.route-art');
    const footer = element.querySelector('.footer-reveal');
    const revealed = new WeakSet();
    const reveal = target => {
      if (revealed.has(target) || preference.matches) return;
      revealed.add(target);
      target.animate([
        {opacity: .15, transform: 'translate3d(0, 32px, 0)'},
        {opacity: 1, transform: 'translate3d(0, 0, 0)'}
      ], {duration: 800, easing: 'cubic-bezier(.16,1,.3,1)'});
    };
    const observe = () => {
      observer?.disconnect();
      if (preference.matches) {
        if (art) art.style.transform = '';
        element.getAnimations({subtree: true}).forEach(animation => animation.cancel());
        return;
      }
      observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {if (entry.isIntersecting) {reveal(entry.target); observer.unobserve(entry.target);}});
      }, {threshold: .12});
      element.querySelectorAll('[data-reveal]').forEach(target => observer.observe(target));
    };
    const scroll = () => {
      if (preference.matches || frame) return;
      frame = requestAnimationFrame(() => {
        const y = Math.min(window.scrollY, 850);
        if (art) art.style.transform = `translate3d(0, ${y * .13}px, 0) rotate(${-y * .009}deg)`;
        if (footer) {
          const rect = footer.getBoundingClientRect();
          const progress = Math.max(0,Math.min(1,(innerHeight-rect.top)/Math.min(innerHeight,rect.height)));
          footer.style.setProperty('--footer-progress',String(progress));
        }
        frame = 0;
      });
    };
    observe();
    window.addEventListener('scroll', scroll, {passive: true});
    preference.addEventListener('change', observe);
    return () => {
      observer?.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener('resize',scroll);
      window.removeEventListener('scroll', scroll);
      preference.removeEventListener('change', observe);
    };
  }, [root]);
}

export function LineMark() {
  return <svg className="line-mark" width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden="true"><path d="M5 23 15 7M13 23 23 7" stroke="currentColor" strokeWidth="4.5" strokeLinecap="round"/></svg>;
}

export {RouteSculpture} from './network-sculpture';

export function ConnectionPath() {
  return <div className="connection-path" aria-label="Ваше устройство — персональный доступ — интернет"><span>Ваше устройство</span><span className="path-track"/><span><Link2 size={15}/>Линия</span><span className="path-track"/><span>Интернет<ArrowUpRight size={16}/></span></div>;
}

import {useScenarioMotion} from './scenario-motion';
import art01 from './assets/scenarios/01.webp';
import art02_1 from './assets/scenarios/02_1.webp';
import art02_2 from './assets/scenarios/02_2.webp';
import art03 from './assets/scenarios/03.webp';
import art04_1 from './assets/scenarios/04_1.webp';
import art04_2 from './assets/scenarios/04_2.webp';
import art04_3 from './assets/scenarios/04_3.webp';
import art05_1 from './assets/scenarios/05_1.webp';
import art05_2 from './assets/scenarios/05_2.webp';
import art05_3 from './assets/scenarios/05_3.webp';

const routes = [
  {art:[art01], label:'Игры', icon:Gamepad2, end:'Отряд', title:'Игра с друзьями', text:'В Warframe не приходит приглашение в отряд? В Destiny 2 затянулся поиск матча? Сравните, как игра подключается к другим игрокам с обычным маршрутом и через Линию.'},
  {art:[art02_1,art02_2], label:'Общение', icon:MessageCircle, end:'Канал', title:'Discord и Telegram', text:'Отправьте ссылку на матч в Telegram и зайдите в голосовой канал Discord, чтобы обсудить тактику с командой.'},
  {art:[art03], label:'Видео', icon:Play, end:'Видео', title:'YouTube', text:'На отдельном маршруте YouTube можно смотреть ролики без рекламы. Показ объявлений зависит от региона и самого YouTube.'},
  {art:[art04_1,art04_2,art04_3], label:'Нейросети', icon:Globe2, end:'Ассистент', title:'ChatGPT, Claude Code и Gemini', text:'Обсудите идею с ChatGPT, разберите код в Claude Code или подготовьте черновик в Gemini.'},
  {art:[art05_1,art05_2,art05_3], label:'Подписки', icon:CreditCard, end:'Магазин', title:'Игры и рабочие инструменты', text:'Перейдите в личный кабинет нужного сервиса, чтобы оформить подписку на нейросеть, PlayStation Plus, Xbox Game Pass или Adobe. Доступность планов и способы оплаты определяет площадка с учётом региона аккаунта.'}
];

function ScenarioBubble({selected,swipe}) {
  const bubble=useRef(null);
  const mounted=useRef(false);
  useLayoutEffect(()=>{
    const node=bubble.current,group=node.parentElement;
    const buttons=[...group.querySelectorAll('button[aria-pressed]')];
    const reduced=matchMedia('(prefers-reduced-motion: reduce)');
    const bounds=button=>({x:button.offsetLeft,y:button.offsetTop,w:button.offsetWidth,h:button.offsetHeight});
    const frame=r=>({transform:'translate('+r.x+'px,'+r.y+'px)',width:r.w+'px',height:r.h+'px'});
    function painted(){
      const r=node.getBoundingClientRect(),g=group.getBoundingClientRect();
      return {x:r.left-g.left,y:r.top-g.top,w:r.width,h:r.height};
    }
    function between(a,b,t){
      const stretch=Math.sin(Math.PI*t)*Math.min(32,Math.hypot(b.x-a.x,b.y-a.y)*.21);
      return {x:a.x+(b.x-a.x)*t-stretch/2,y:a.y+(b.y-a.y)*t+stretch/16,
        w:a.w+(b.w-a.w)*t+stretch,h:a.h+(b.h-a.h)*t-stretch/8};
    }
    let target=bounds(buttons[selected]),dragOrigin=null;
    function settle(animate,returning=false){
      const from=painted();
      node.getAnimations().forEach(a=>a.cancel());
      Object.assign(node.style,frame(target));
      if(!animate||reduced.matches)return;
      const frames=[frame(from)];
      if(!returning)frames.push({...frame(between(from,target,.5)),offset:.42});
      frames.push(frame(target));
      node.animate(frames,{duration:returning?320:360,easing:'cubic-bezier(.25,.72,.23,1)'});
    }
    settle(mounted.current);
    mounted.current=true;
    swipe.current={
      move(index,progress){
        if(!dragOrigin){
          dragOrigin=painted();
          node.getAnimations().forEach(a=>a.cancel());
        }
        Object.assign(node.style,frame(between(dragOrigin,bounds(buttons[index]),progress)));
      },
      cancel(){
        if(!dragOrigin)return;
        dragOrigin=null;
        settle(true,true);
      }
    };
    const observer=new ResizeObserver(()=>{
      const next=bounds(buttons[selected]);
      if(Object.keys(target).some(key=>target[key]!==next[key])){
        target=next;dragOrigin=null;settle(false);
      }
    });
    observer.observe(group);
    buttons.forEach(button=>observer.observe(button));
    return ()=>{observer.disconnect();swipe.current=null;};
  },[selected,swipe]);
  return <span ref={bubble} className="scenario-bubble" aria-hidden="true"/>;
}

export function ServiceStories() {
  const [{selected,previous,direction,exitOffset=0},setSlide]=useState({selected:0,previous:null,direction:1});
  const [touchTrack,setTouchTrack]=useState(false);
  const gesture=useRef(null);
  const stage=useRef(null);
  const bubbleSwipe=useRef(null);
  const desired=useRef(0);
  const request=useRef(0);
  async function select(next,step,dragOffset=0) {
    if(next===desired.current)return;
    desired.current=next;
    const version=++request.current;
    await Promise.allSettled(routes[next].art.map(src=>{
      const img=new Image(); img.src=src; return img.decode();
    }));
    if(request.current!==version)return;
    resetDrag(false);
    const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
    setSlide(current=>current.selected===next ? current : {
      selected:next,previous:reduce||touchTrack?null:current.selected,direction:step,exitOffset:dragOffset
    });
  }
  function resetDrag(restoreBubble=true) {
    if(restoreBubble)bubbleSwipe.current?.cancel();
    setDragging(false);
    gesture.current=null;
    stage.current?.removeAttribute('data-dragging');
    stage.current?.style.removeProperty('--drag-progress');
  }
  function startSwipe(event) {
    if(!event.isPrimary){resetDrag();return;}
    if(event.pointerType==='mouse')return;
    const host=event.currentTarget;
    // Re-grabbing a returning image starts from its current painted position.
    const current=host.querySelector('[data-current]');
    const painted=getComputedStyle(current).translate;
    const offset=(parseFloat(painted)||0)*(painted.includes('%')?host.clientWidth/100:1);
    ++request.current;
    desired.current=selected;
    gesture.current={id:event.pointerId,x:event.clientX,y:event.clientY,offset,axis:null};
    setTouchTrack(true);
    host.style.setProperty('--drag-progress',String(offset/(host.clientWidth*.6)));
    setDragging(true);
    host.dataset.dragging='';
    host.setPointerCapture(event.pointerId);
  }
  function moveSwipe(event) {
    const start=gesture.current;
    if(start?.id!==event.pointerId)return;
    const dx=event.clientX-start.x,dy=event.clientY-start.y;
    if(!start.axis && Math.max(Math.abs(dx),Math.abs(dy))>=4)
      start.axis=Math.abs(dx)>Math.abs(dy)?'x':'y';
    if(start.axis!=='x')return;
    const travel=start.offset+dx;
    const step=travel<0?1:-1;
    const progress=Math.min(1,Math.abs(travel)/(event.currentTarget.clientWidth*.6));
    event.currentTarget.style.setProperty('--drag-progress',String(-step*progress));
    bubbleSwipe.current?.move((selected+step+routes.length)%routes.length,progress);
  }
  function endSwipe(event) {
    const start=gesture.current;
    if(start?.id!==event.pointerId)return;
    moveSwipe(event);
    const dx=start.offset+event.clientX-start.x;
    const threshold=Math.min(88,event.currentTarget.clientWidth*.22);
    setDragging(false);
    if(start.axis!=='x'||Math.abs(dx)<threshold){resetDrag();return;}
    gesture.current=null;
    const step=dx<0?1:-1;
    select((selected+step+routes.length)%routes.length,step,dx);
  }
  const panel = useRef(null);
  const [visible,setVisible]=useState(false);
  const [paused,setPaused]=useState(()=>matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [dragging,setDragging]=useState(false);
  const [entered,setEntered] = useState(false);
  useEffect(()=>{
    const observer=new IntersectionObserver(([entry])=>{
      setVisible(entry.isIntersecting);
      if(entry.isIntersecting)setEntered(true);
    },{threshold:.08});
    observer.observe(panel.current);
    return ()=>observer.disconnect();
  },[]);
  useEffect(()=>{
    if(!visible||paused||dragging)return;
    let timer;
    function schedule(){
      clearTimeout(timer);
      if(!document.hidden)timer=setTimeout(()=>{
        if(!gesture.current&&desired.current===selected)select((selected+1)%routes.length,1);
      },3000);
    }
    schedule();
    document.addEventListener('visibilitychange',schedule);
    return ()=>{clearTimeout(timer);document.removeEventListener('visibilitychange',schedule);};
  },[selected,visible,paused,dragging]);
  useScenarioMotion(panel,entered);
  const route = routes[selected];
  const Icon = route.icon;
  return <section className="service-stories" aria-labelledby="service-heading">
    <div className="story-intro" data-reveal><h2 id="service-heading">Куда ведёт ваша линия?</h2><p>Выберите, для чего хотите настроить подключение.</p><a href="#devices" className="text-link">Настроить на устройстве<ArrowDown size={17}/></a></div>
      <div className="scenario-picker" role="group" aria-label="Сценарий подключения"><ScenarioBubble selected={selected} swipe={bubbleSwipe}/>{routes.map(({label,icon:Symbol},i)=><button key={label} type="button" aria-pressed={selected===i} onClick={()=>select(i,i>selected?1:-1)}><Symbol aria-hidden="true" size={17}/>{label}</button>)}<button type="button" className="scenario-playback" aria-label={paused?'Включить автолистание':'Приостановить автолистание'} title={paused?'Включить автолистание':'Приостановить автолистание'} onClick={()=>setPaused(value=>!value)}>{paused?<Play size={16}/>:<Pause size={16} strokeWidth={3} aria-hidden="true"/>}</button></div>
    <div ref={panel} className={`story-content scenario-panel${entered ? " has-entered" : ""}`}>
      <div className="scenario-network" aria-hidden="true"/>
      <div ref={stage} className={touchTrack?"scenario-stage touch-track":"scenario-stage"} aria-hidden="true" style={{'--direction':direction,'--exit-offset':exitOffset+'px'}}
        onPointerDown={startSwipe} onPointerMove={moveSwipe} onPointerUp={endSwipe} onPointerCancel={resetDrag}
        onLostPointerCapture={event=>{if(gesture.current?.id===event.pointerId)resetDrag();}}>
        {(touchTrack?routes.map((_,i)=>i):[previous,selected].filter(i=>i!==null)).map(i=>
          <div key={i} data-current={i===selected?"":undefined} style={touchTrack?{"--slot":(i-selected+routes.length+2)%routes.length-2}:undefined} className={`scenario-art parts-${routes[i].art.length} ${i===previous?'slide-out':previous!==null?'slide-in':''}`}
            onAnimationEnd={event=>{
              if(event.target===event.currentTarget&&i===previous)
                setSlide(current=>current.previous===i&&current.selected===selected?{...current,previous:null}:current);
            }}>
            {routes[i].art.map(src=><img key={src} src={src} alt="" draggable="false"/>)}
          </div>)}
      </div>

      <div className="scenario-detail" aria-live={paused?'polite':'off'}>
        <div key={route.label} className="scenario-map" aria-hidden="true"><span><Monitor/>Устройство</span><i/><span><LineMark/>Линия</span><i/><span><Icon/>{route.end}</span></div>
        <h3>{route.title}</h3><p>{route.text}</p>
      </div>
    </div>
  </section>;
}
