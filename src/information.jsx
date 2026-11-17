import {Cookie,FileText,UserRound,BookOpen,Globe2,ShieldCheck,Play,ChevronDown} from 'lucide-react';
import React, {useEffect, useRef} from 'react';

export const documents = {
  '/privacy': {title:'Политика конфиденциальности', sections:[
    ['Кого касается политика','Политика описывает работу портала «Линия» при выдаче персональной ссылки, входе в кабинет и обращении в поддержку.'],
    ['Какие данные использует портал','Для выдачи и обслуживания доступа сохраняются имя или псевдоним, логин, идентификаторы подключения, срок действия, лимиты и заметки владельца. Пароль кабинета хранится в виде хеша.'],
    ['Учёт подключения','Для расчёта остатка трафика и диагностики портал учитывает объём отправленных и полученных данных, время активности, открытия страницы доступа и обновления подписки. Эти сведения доступны владельцу сервиса в панели управления.'],
    ['Ваши обращения','Вы можете запросить сведения о своих данных, их исправление, ограничение обработки или удаление при наличии оснований. Укажите имя доступа и суть запроса. Пароль и персональную ссылку передавать не нужно.'],
    ['Сторонние сервисы','При переходе в магазин, игру, мессенджер или сервис нейросетей обработку данных на той площадке регулирует её собственная политика.']
  ]},
  '/cookies': {title:'Файлы cookie',sections:[
    ['Для чего они нужны','После входа портал сохраняет в браузере служебный идентификатор сеанса. По нему сервер открывает ваш кабинет при переходе между страницами.'],
    ['Срок действия','Обычный сеанс кабинета действует до 12 часов. Если выбрать «Запомнить вход», сеанс может сохраняться до 30 дней. Кнопка выхода завершает текущий сеанс.'],
    ['Настройки браузера','Вы можете удалить cookie сайта в настройках браузера. При следующем посещении кабинета потребуется снова ввести логин и пароль.']
  ]},
  '/terms': {title:'Условия использования',sections:[
    ['Персональный доступ','Владелец сервиса выдаёт ссылку для подключения. Срок действия, состояние доступа и доступный объём трафика указаны в личном кабинете. Храните ссылку и пароль в тайне.'],
    ['Оплата и продление','Пакеты на главной странице предложены для пилота. Продажи, приём платежей и автоматическое продление этих пакетов на сайте пока не открыты. По вопросам действующего доступа обратитесь к владельцу.'],
    ['Сервисы и подписки','Покупки в PlayStation Store, Xbox, Adobe и сервисах нейросетей оформляются отдельно у соответствующей площадки. Она определяет доступность, оплату и возвраты. Стоимость сторонних подписок не входит в пакет «Линии».'],
    ['Работа подключения','Результат зависит от провайдера, устройства, настроек сети и состояния серверов игры или приложения. Для разбора проблемы укажите устройство, название приложения и время сбоя.']
  ]}
};

export function DocumentLinks() {
  return <nav className="document-links" aria-label="Правовая информация">{Object.entries(documents).map(([url,doc])=><a key={url} href={url}>{url==='/privacy'?<ShieldCheck size={17} aria-hidden="true"/>:url==='/cookies'?<Cookie size={17} aria-hidden="true"/>:<FileText size={17} aria-hidden="true"/>}{doc.title}</a>)}</nav>;
}
export function DocumentPage({doc,settings}) {
  return <article className="legal-page"><a href="/">← На главную</a><h1>{doc.title}</h1><p>Редакция от 16 ноября 2026 года</p>{doc.sections.map(([heading,body])=><section key={heading}><h2>{heading}</h2><p>{body}</p></section>)}<h2>Связь с владельцем</h2>{settings.support_url?<a href={settings.support_url} rel="noreferrer">Написать в поддержку</a>:<p>Используйте канал связи, через который вам выдали доступ.</p>}</article>;
}
const plans = [
  {name:'Личный', price:199, devices:2, traffic:100},
  {name:'Комфорт', price:349, devices:5, traffic:300},
  {name:'Семья', price:549, devices:10, traffic:600}
];

function lookAt(face,clientX,clientY) {
  delete face.dataset.glance;
  const bounds=face.parentElement.getBoundingClientRect();
  const dx=clientX-bounds.left-bounds.width/2,dy=clientY-bounds.top-bounds.height/2;
  // Convert the screen direction into the axes of the currently tilted plate.
  const matrix=new DOMMatrixReadOnly(getComputedStyle(face.closest('.plan-stack')).transform);
  const det=matrix.a*matrix.d-matrix.b*matrix.c;
  if(Math.abs(det)<.01)return;
  const x=(matrix.d*dx-matrix.c*dy)/det,y=(matrix.a*dy-matrix.b*dx)/det;
  const range=Math.max(36,Math.hypot(x,y));
  const squint=Math.min(1,Math.max(0,(Math.abs(dx)-5)/Math.max(40,Math.hypot(dx,dy)-5)));
  face.style.setProperty('--left-open',dx>0?1-.48*squint:1);
  face.style.setProperty('--right-open',dx<0?1-.48*squint:1);
  face.style.setProperty('--look-x',5*x/range+'px');
  face.style.setProperty('--look-y',5*y/range+'px');
}

function clearLook(face) {
  for(const key of ['--look-x','--look-y','--left-open','--right-open'])face.style.removeProperty(key);
}

function PlanSculpture({layers}) {
  const eyes=useRef(null);
  const stack = useRef(null);
  const state = useRef({finger:null, tilt:0, turn:0, frame:0});
  useEffect(()=>()=>cancelAnimationFrame(state.current.frame),[]);

  useEffect(()=>{
    const face=eyes.current;
    const motion=matchMedia('(prefers-reduced-motion: reduce)');
    let visible=false,timer;
    function schedule(){
      clearTimeout(timer);
      delete face.dataset.glance;
      if(!visible||document.hidden||motion.matches)return;
      timer=setTimeout(()=>{
        if(face.closest('[data-held]')||face.style.getPropertyValue('--look-x')){
          schedule();
          return;
        }
        face.dataset.glance=Math.random()<.5?'left':'right';
        timer=setTimeout(schedule,1800);
      },3500+Math.random()*5500);
    }
    const observer=new IntersectionObserver(([entry])=>{
      visible=entry.isIntersecting;
      schedule();
    });
    observer.observe(face.closest('.plan-art'));
    document.addEventListener('visibilitychange',schedule);
    motion.addEventListener('change',schedule);
    return ()=>{
      clearTimeout(timer);observer.disconnect();
      document.removeEventListener('visibilitychange',schedule);
      motion.removeEventListener('change',schedule);
    };
  },[]);

  function draw(tilt,turn) {
    const pose=state.current;
    pose.tilt=tilt;
    pose.turn=turn;
    stack.current.style.transform=`translateY(8px) rotateX(${56+tilt}deg) rotateY(${turn}deg) rotateZ(-36deg)`;
  }
  function grab(event) {
    const pose=state.current;
    if(event.pointerType==='mouse'||!event.isPrimary||pose.finger)return;
    cancelAnimationFrame(pose.frame);
    pose.finger={id:event.pointerId,x:event.clientX,y:event.clientY,tilt:pose.tilt,turn:pose.turn};
    stack.current.style.transition='none';
    event.currentTarget.dataset.held='';
    lookAt(eyes.current,event.clientX,event.clientY);
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function rotate(event) {
    const finger=state.current.finger;
    if(finger?.id!==event.pointerId)return;
    const tilt=finger.tilt-24*Math.tanh((event.clientY-finger.y)/52);
    const turn=finger.turn+38*Math.tanh((event.clientX-finger.x)/56);
    draw(Math.max(-24,Math.min(24,tilt)),Math.max(-38,Math.min(38,turn)));
    lookAt(eyes.current,event.clientX,event.clientY);
  }
  function release(event) {
    const pose=state.current;
    if(pose.finger?.id!==event.pointerId)return;
    pose.finger=null;
    delete event.currentTarget.dataset.held;
    clearLook(eyes.current);
    if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
    const {tilt,turn}=pose;
    const start=performance.now();
    function settle(now) {
      const t=(now-start)/1000;
      if(t>=.85 || matchMedia('(prefers-reduced-motion: reduce)').matches) {
        pose.tilt=pose.turn=0;
        stack.current.style.removeProperty('transform');
        stack.current.style.removeProperty('transition');
        return;
      }
      // Underdamped return with zero initial velocity.
      const factor=Math.exp(-8*t)*(Math.cos(12*t)+(8/12)*Math.sin(12*t));
      draw(tilt*factor,turn*factor);
      pose.frame=requestAnimationFrame(settle);
    }
    settle(start);
  }
  return <div className="plan-art" aria-hidden="true" onPointerDown={grab} onPointerMove={rotate}
    onPointerUp={release} onPointerCancel={release} onLostPointerCapture={release}><div className="plan-stack" ref={stack}>
    {Array.from({length:layers},(_,i)=><div key={i} className="plan-tile" style={{'--level':i-(layers-1)/2}}>
      {i===layers-1 && <div className="tile-mark" ref={eyes}><i/><i/></div>}
    </div>)}
  </div></div>;
}

import {offerRows} from './partners';
export function Plans({terms}) {
  const section=useRef(null);
  useEffect(()=>{
    const media=matchMedia('(any-hover:hover) and (prefers-reduced-motion:no-preference)');
    const faces=[...section.current.querySelectorAll('.tile-mark')];
    let frame=0,point=null;
    function paint() {
      frame=0;
      for(const face of faces){
        if(face.closest('[data-held]'))continue;
        const card=face.closest('article').getBoundingClientRect();
        const near=point && Math.hypot(Math.max(card.left-point.x,point.x-card.right,0),
          Math.max(card.top-point.y,point.y-card.bottom,0))<88;
        if(!near){
          clearLook(face);continue;
        }
        lookAt(face,point.x,point.y);
      }
    }
    function schedule(){if(!frame)frame=requestAnimationFrame(paint);}
    function move(event){if(event.pointerType==='mouse'){point={x:event.clientX,y:event.clientY};schedule();}}
    function clear(){point=null;schedule();}
    function listen(){
      window.removeEventListener('pointermove',move);
      if(media.matches)window.addEventListener('pointermove',move,{passive:true});
      clear();
    }
    function scroll(){if(point)schedule();}
    listen();media.addEventListener('change',listen);
    document.documentElement.addEventListener('pointerleave',clear);
    window.addEventListener('blur',clear);window.addEventListener('scroll',scroll,{passive:true});
    return ()=>{
      window.removeEventListener('pointermove',move);window.removeEventListener('scroll',scroll);
      window.removeEventListener('blur',clear);document.documentElement.removeEventListener('pointerleave',clear);
      media.removeEventListener('change',listen);cancelAnimationFrame(frame);
    };
  },[]);
  return <section ref={section} className="plans" id="plans" aria-labelledby="plans-title">
    <header><h2 id="plans-title">Пакеты подключения</h2><p>Предварительные цены для пилота. Продажи ещё не открыты.</p></header>
    <article className="trial-plan" aria-labelledby="trial-title"><div><h3 id="trial-title">FREE</h3><p>Пробный доступ</p></div><PlanSculpture layers={1}/><dl><div><dt>Стоимость</dt><dd>0 ₽</dd></div><div><dt>Срок</dt><dd>48 часов</dd></div><div><dt>Общий трафик</dt><dd>5 ГБ</dd></div></dl></article>
    <div className="plan-grid">{plans.map(({name,price,devices,traffic})=>
      <article className="plan-card" key={name}>
        <h3>{name}</h3><PlanSculpture layers={devices}/>
        <p className="plan-price"><strong>{price} ₽</strong> в месяц</p>
        <dl><div><dt>Устройства</dt><dd>{devices}</dd></div><div><dt>Общий трафик</dt><dd>{traffic} ГБ</dd></div></dl>
      </article>)}</div>
    <div className="plan-information">
      <section className="included-features" aria-labelledby="included-title">
        <h3 id="included-title">Во всех пакетах</h3>
        <ul>{[[UserRound,'Личный кабинет'],[BookOpen,'Инструкции для Happ и v2RayTun'],[Globe2,'Прямое подключение к доменам .ru и .рф'],[ShieldCheck,'Сетевой фильтр рекламы и трекеров']].map(([Icon,label])=>
          <li key={label}><Icon size={19} aria-hidden="true"/><span>{label}</span></li>)}</ul>
        <div className="included-video"><Play size={18} aria-hidden="true"/><p><strong>Отдельный маршрут YouTube</strong>Доступен действующим подключениям. Разделение по пакетам планируется позднее.</p></div>
      </section>
      <details className="plan-options" open>
        <summary><span>Дополнительные условия</span><ChevronDown size={20} aria-hidden="true"/></summary>
        <p>Предложения для пилота</p>
        <dl>{offerRows(terms).map(([label,value])=>
          <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      </details>
    </div>
  </section>;
}
