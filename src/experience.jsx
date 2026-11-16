import React, {useEffect, useRef} from 'react';
import {ArrowDown, ArrowUpRight, ArrowRight, Link2, Play, ShieldCheck, Globe2} from 'lucide-react';

// Presentation only: motion never owns application state or navigation.
export function usePageMotion(root) {
  useEffect(() => {
    const element = root.current;
    if (!element) return;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    let observer;
    let frame = 0;
    const art = element.querySelector('.route-art');
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
      if (!art || preference.matches || frame) return;
      frame = requestAnimationFrame(() => {
        const y = Math.min(window.scrollY, 850);
        art.style.transform = `translate3d(0, ${y * .13}px, 0) rotate(${-y * .009}deg)`;
        frame = 0;
      });
    };
    observe();
    window.addEventListener('scroll', scroll, {passive: true});
    preference.addEventListener('change', observe);
    return () => {
      observer?.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', scroll);
      preference.removeEventListener('change', observe);
    };
  }, [root]);
}

export function LineMark() {
  return <svg className="line-mark" width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden="true"><path d="M5 23 15 7M13 23 23 7" stroke="currentColor" strokeWidth="4.5" strokeLinecap="round"/></svg>;
}

export function RouteSculpture() {
  const ref = useRef(null);
  useEffect(() => {
    const target = ref.current;
    const media = window.matchMedia('(pointer: fine) and (prefers-reduced-motion: no-preference)');
    const move = event => {
      if (!media.matches) return;
      const rect = target.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - .5;
      const y = (event.clientY - rect.top) / rect.height - .5;
      target.style.transform = `perspective(1000px) rotateY(${x * 9}deg) rotateX(${-y * 9}deg)`;
    };
    const leave = () => {target.style.transform = '';};
    target.addEventListener('pointermove', move);
    target.addEventListener('pointerleave', leave);
    return () => {target.removeEventListener('pointermove', move); target.removeEventListener('pointerleave', leave);};
  }, []);
  return <div className="route-art" aria-hidden="true"><div className="route-sculpture" ref={ref}>
    <svg viewBox="0 0 780 620" fill="none" className="sculpture-svg">
      <defs>
        <linearGradient id="tube" x1="160" y1="430" x2="580" y2="180" gradientUnits="userSpaceOnUse"><stop stopColor="#082884"/><stop offset=".23" stopColor="#1458ef"/><stop offset=".45" stopColor="#82b7ff"/><stop offset=".58" stopColor="#287bff"/><stop offset=".78" stopColor="#0345e8"/><stop offset="1" stopColor="#091f75"/></linearGradient>
        <linearGradient id="tube-light" x1="270" y1="200" x2="440" y2="420" gradientUnits="userSpaceOnUse"><stop stopColor="#c3dcff"/><stop offset=".4" stopColor="#5a9bff"/><stop offset="1" stopColor="#1447ca"/></linearGradient>
        <linearGradient id="tube-front" x1="280" y1="430" x2="570" y2="480" gradientUnits="userSpaceOnUse"><stop stopColor="#276cf6"/><stop offset=".45" stopColor="#80b4ff"/><stop offset="1" stopColor="#0b3eb7"/></linearGradient>
      </defs>
      <g className="sculpture-float">
        <path d="M-70 490C78 500 148 439 194 302C244 153 341 91 448 143C570 203 583 323 482 364C367 410 272 311 308 250C350 180 429 225 471 313C517 410 577 505 683 482C771 462 799 387 852 318" stroke="#061c69" strokeWidth="79" strokeLinecap="round"/>
        <path d="M-70 483C78 493 148 432 194 295C244 146 341 84 448 136C570 196 583 316 482 357C367 403 272 304 308 243C350 173 429 218 471 306C517 403 577 498 683 475C771 455 799 380 852 311" stroke="url(#tube)" strokeWidth="72" strokeLinecap="round"/>
        <path d="M194 279C244 130 341 68 448 120C570 180 583 300 482 341C367 387 272 288 308 227" stroke="url(#tube-light)" strokeWidth="26" strokeLinecap="round" opacity=".8"/>
        <path d="M471 306C517 403 577 498 683 475" stroke="url(#tube-front)" strokeWidth="72" strokeLinecap="round"/>
        <path d="M-70 483C78 493 148 432 194 295C244 146 341 84 448 136C570 196 583 316 482 357C367 403 272 304 308 243C350 173 429 218 471 306C517 403 577 498 683 475C771 455 799 380 852 311" stroke="#e2efff" strokeWidth="3" strokeLinecap="round" pathLength="100" strokeDasharray="1 99" className="route-signal"/>
      </g>
    </svg>
  </div></div>;
}

export function ConnectionPath() {
  return <div className="connection-path" aria-label="Ваше устройство — персональный доступ — интернет"><span>Ваше устройство</span><span className="path-track"/><span><Link2 size={15}/>Линия</span><span className="path-track"/><span>Интернет<ArrowUpRight size={16}/></span></div>;
}

export function ServiceStories() {
  return <section className="service-stories" aria-labelledby="service-heading">
    <div className="story-intro" data-reveal><h2 id="service-heading">Своя линия.<br/>Для каждого.</h2><p>Одно подключение. Разные маршруты для того, чем вы пользуетесь каждый день.</p><a href="#devices" className="text-link">Настроить на устройстве<ArrowDown size={17}/></a></div>
    <div className="story-content">
      <article className="youtube-story" data-reveal><div className="youtube-symbol" aria-hidden="true"><Play fill="currentColor" strokeWidth="0" size={34}/></div><div><h3>YouTube.<br/>Своя линия.</h3><p>Для видео настроен отдельный маршрут. Фильтр рекламы и трекеров работает на уровне сети, но не гарантирует удаление рекламы внутри YouTube.</p></div><ArrowUpRight className="story-arrow" size={28} aria-hidden="true"/></article>
      <article className="direct-story" data-reveal><Globe2 size={28} aria-hidden="true"/><div><h3>Российские сайты — напрямую.</h3><p>Домены .ru и .рф открываются через ваше обычное соединение. Остальной трафик идёт через VPN.</p></div></article>
      <div className="whitelist-note" data-reveal><ShieldCheck size={22} aria-hidden="true"/><p><strong>А если интернет по белым спискам?</strong> Работа подключения зависит от ограничений оператора. Универсального обхода для всех сетей обещать нельзя.</p></div>
    </div>
  </section>;
}
