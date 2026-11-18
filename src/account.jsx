import {clientsFor, inferredPlatform} from './vpn-clients.mjs';
import {usePagePosition} from './reload-position';
import {SupportChat} from './support';
import {PartnerPanel} from './partners';
import {SpeedCheck} from './speed-check';
import React, {useState, useEffect, useRef, useCallback} from 'react';
import {ArrowRight, ArrowUpRight, Link2, Copy, RefreshCw, CalendarDays, Clock3, ShieldCheck, CircleAlert, Bell, UserRound, Download, Upload, Activity, ExternalLink, QrCode, ChevronRight} from 'lucide-react';
import {accountState, remainingTime, parseAccessToken} from './account-state.mjs';
import './account.css';
import {AccountPassword} from './account-password';

const exactDate = value => value ? new Intl.DateTimeFormat('ru-RU', {day:'numeric',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Krasnoyarsk'}).format(new Date(value * 1000)) : 'Без ограничения срока';

export function AccountEntry({settings, Shell, Button}) {
  const [link, setLink] = useState('');
  const [error, setError] = useState('');
  function submit(event) {
    event.preventDefault();
    try { location.href = '/connect/' + parseAccessToken(link, settings.base_url); }
    catch { setError('Вставьте персональную ссылку, которую выдал владелец сервиса.'); }
  }
  return <Shell settings={settings} selected="account"><section className="account-entry" id="connection">
    <div className="account-entry-copy"><span className="account-entry-icon"><UserRound size={30}/></span><h1>Личный кабинет</h1><p>Ваш доступ, трафик и подписка.<br/>Всё в одном месте.</p></div>
    <form className="account-entry-form" onSubmit={submit}><h2>Войдите по своей ссылке</h2><p>Подойдёт ссылка на подключение или подписку, которую вам отправил владелец.</p><label htmlFor="account-link">Персональная ссылка</label><input id="account-link" value={link} onChange={event=>{setLink(event.target.value);setError('');}} required autoComplete="off" autoCapitalize="off" spellCheck={false} placeholder="https://…/connect/…" aria-invalid={Boolean(error)} aria-describedby={error?'account-entry-error':'account-entry-note'}/>{error&&<p className="field-error" id="account-entry-error" role="alert">{error}</p>}<Button type="submit">Открыть кабинет<ArrowRight size={18}/></Button><p id="account-entry-note" className="account-entry-note"><ShieldCheck size={16}/>Ваша персональная ссылка — ключ к кабинету. Не передавайте её другим.</p><a className="text-link" href="/#questions">У меня пока нет ссылки<ArrowUpRight size={15}/></a></form>
  </section></Shell>;
}

export function UserAccount({token,settings,api,Shell,Button,Status,PlatformGuide,formatBytes,date,relative,show,session,onLogout,signingOut,onSessionExpired,onSessionUpdate}) {
  const [access,setAccess]=useState(session||null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [updated,setUpdated]=useState(null);
  const [now,setNow]=useState(()=>Date.now()/1000);
  const counted=useRef(false);
  const alive=useRef(false);
  const pending=useRef(false);
  const load=useCallback(async(manual=false)=>{
    if(pending.current)return;
    pending.current=true;
    if(manual)setBusy(true);
    try {
      const result=await api(session?'/api/account/me':'/api/access/'+token);
      if(alive.current){setAccess(result);setError('');setUpdated(Date.now()/1000);setNow(Date.now()/1000);if(session)onSessionUpdate?.(result);}
    } catch(failure) {
      if(alive.current){if(session&&failure.status===401){onSessionExpired?.();return;}setError(failure.message);if(failure.status===404||failure.status===410)setAccess(null);}
    } finally {
      pending.current=false;
      if(alive.current)setBusy(false);
    }
  },[token,api,Boolean(session),onSessionExpired,onSessionUpdate]);
  useEffect(()=>{
    alive.current=true;
    load();
    if(token&&!counted.current){counted.current=true;api('/api/access/'+token+'/view',{method:'POST'}).catch(()=>{});}
    const resume=()=>{if(!document.hidden){setNow(Date.now()/1000);load();}};
    const timer=setInterval(()=>{if(!document.hidden){setNow(Date.now()/1000);load();}},15000);
    document.addEventListener('visibilitychange',resume);
    window.addEventListener('focus',resume);
    return()=>{alive.current=false;clearInterval(timer);document.removeEventListener('visibilitychange',resume);window.removeEventListener('focus',resume);};
  },[token,api,load]);
  useEffect(()=>{const title=document.title;document.title='Личный кабинет — '+(access?.settings?.name||settings.name);return()=>{document.title=title;};},[access?.settings?.name,settings.name]);
  const copy=async(value,message)=>{
    try{await navigator.clipboard.writeText(value);show(message||'Ссылка скопирована');}
    catch{show('Не удалось скопировать. Выделите ссылку вручную',true);}
  };
  usePagePosition(Boolean(access),'account:'+(access?.id||''));
  const currentSettings=access?.settings||settings;
  const state=access?accountState(access,now):null;
  const support=currentSettings.support_url;
  const renewalHref=support||'#renewal';
  const supportProps=support?{target:'_blank',rel:'noreferrer'}:{};
  return <Shell settings={currentSettings} account signedIn={Boolean(session)} onLogout={onLogout} signingOut={signingOut}><div className="account-page">
    <header className="account-heading"><div><h1>Личный кабинет</h1><p>Регион подключения · 🇵🇱 Польша</p></div><button className="button secondary account-refresh" disabled={busy} onClick={()=>load(true)}><RefreshCw size={16} className={busy?'is-refreshing':''}/>{busy?'Обновляем…':'Обновить'}</button></header>
    {!access?(error?<section className="account-load-error" role="alert"><Link2 size={34}/><h2>Не удалось открыть кабинет</h2><p>{error}. Проверьте ссылку или обратитесь к владельцу.</p><div><Button onClick={()=>load(true)} disabled={busy}>Повторить</Button><a href="/account" className="button secondary">Другая ссылка</a></div></section>:<div className="account-skeleton" role="status"><span className="sr-only">Загружаем личный кабинет</span><div/><div/><div/></div>):<>
      {error&&<div className="error-banner" role="alert">Не удалось обновить данные. Показана последняя загруженная информация.<button onClick={()=>load(true)}>Повторить</button></div>}
      <section className="account-overview" id="connection" aria-label="Обзор доступа"><div className="account-profile"><span className="account-avatar" aria-hidden="true"><UserRound size={24}/></span><div><h2>{access.name}</h2><span>{access.account_username?'Логин: '+access.account_username:'Персональный доступ'}</span></div><Status status={state.status} online={access.online}/></div>
      <div className="account-metrics"><article className={`account-term ${state.status==='expired'?'term-expired':''}`}><div className="account-metric-label"><CalendarDays size={18}/><span>{access.expires_at?'Доступ действует до':'Срок доступа'}</span></div><strong>{access.expires_at?date(access.expires_at):'Без срока'}</strong><div className="account-term-bottom"><span>{state.remaining===null?'Ограничение по дате не установлено':state.remaining<=0?'Срок закончился':'Осталось: '+remainingTime(state.remaining)}</span><a href={renewalHref} {...supportProps}>Продлить<ArrowUpRight size={16}/></a></div>{access.expires_at&&<p className="account-exact-time">До {new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Krasnoyarsk'}).format(new Date(access.expires_at*1000))} по Красноярску · UTC+7</p>}</article>
      <article className="account-traffic"><div className="account-metric-label"><Activity size={18}/><span>{state.quota?'Осталось трафика':'Трафик без лимита'}</span></div><strong>{state.quota?formatBytes(state.left):formatBytes(state.used)}<small>{state.quota?'из '+formatBytes(state.quota):'использовано'}</small></strong>{state.quota>0&&<progress className={state.fraction>=.95?'quota-critical':state.fraction>=.8?'quota-warning':''} value={Math.min(state.used,state.quota)} max={state.quota} aria-label="Использованный трафик"/>}<div className="account-traffic-bottom"><span>Использовано {formatBytes(state.used)}</span><span>{state.quota?new Intl.NumberFormat('ru-RU',{maximumFractionDigits:1}).format(state.fraction*100)+'%':'На всех устройствах'}</span></div></article></div>
      <dl className="account-facts"><div><dt>Доступ создан</dt><dd>{access.created_at?date(access.created_at,true):'Дата не указана'}</dd></div><div><dt>Последняя активность</dt><dd>{relative(access.last_seen_at)}</dd></div><div><dt>Открытых соединений</dt><dd>{access.connections??0}</dd></div></dl></section>
      <section className="account-notifications" aria-labelledby="notifications-heading"><div className="account-section-heading"><h2 id="notifications-heading"><Bell size={20}/>Уведомления</h2><span>{state.alerts.length?state.alerts.length:'Всё в порядке'}</span></div><div className="account-notification-list" role="status" aria-live="polite" aria-atomic="true">{state.alerts.length?state.alerts.map(alert=><article className={`account-notice notice-${alert.tone}`} key={alert.id}><span className="notice-icon">{alert.id==='expiry'?<Clock3 size={21}/>:<CircleAlert size={21}/>}</span><div><h3>{alert.title}</h3><p>{alert.body}</p>{alert.id==='expiry'&&access.expires_at&&<p className="notice-date">Дата окончания: {exactDate(access.expires_at)} · Красноярск</p>}{alert.id==='traffic'&&state.quota>0&&<p className="notice-date">Осталось {formatBytes(state.left)} из {formatBytes(state.quota)}</p>}</div><a className="notice-action" href={renewalHref} {...supportProps}>{support?'Связаться':'Что делать'}<ChevronRight size={16}/></a></article>):<div className="account-notice notice-ok"><ShieldCheck size={22}/><div><h3>{state.status==='active'?'Доступ активен':'Нет новых предупреждений'}</h3><p>Здесь появятся предупреждения за 7 дней до окончания доступа и при расходе 80% трафика.</p></div></div>}</div></section>
      <section className="account-subscription" id="subscription" aria-labelledby="subscription-heading"><div className="account-section-heading"><h2 id="subscription-heading">Ваша подписка</h2><span>Одна ссылка для всех устройств</span></div><div className="account-subscription-body"><div><p>Скопируйте ссылку или добавьте подписку прямо в приложение. При продлении ссылка остаётся прежней.</p><label htmlFor="subscription-url" className="sr-only">URL подписки</label><div className="copy-field"><input id="subscription-url" readOnly value={access.subscription_url} onFocus={event=>event.target.select()}/><button className="icon-button" aria-label="Скопировать подписку" onClick={()=>copy(access.subscription_url,'Ссылка подписки скопирована')}><Copy size={19}/></button></div><div className="subscription-actions">{state.status==='active'?clientsFor(inferredPlatform()).map((client,index)=><a key={client.name} className={'button '+(index===0?'primary':'secondary')} href={client.importLink(access.subscription_url)}>{index===0&&<ExternalLink size={17}/>}Добавить в {client.name}{index===1&&<ArrowUpRight size={16}/>}</a>):<p className="account-import-note">Добавление подключения доступно после возобновления доступа. Ссылку можно сохранить уже сейчас.</p>}</div><button className="text-link account-copy-page" onClick={()=>copy(session?location.origin+'/account':access.page_url||location.origin+'/connect/'+token,'Ссылка на кабинет скопирована')}><Copy size={15}/>Скопировать ссылку на кабинет</button><p className="account-link-note"><ShieldCheck size={15}/>Ссылка даёт доступ к вашей подписке и кабинету. Храните её как пароль.</p></div>{state.status==='active'?<figure className="qr-figure"><img src={session?'/api/account/qr.svg':'/api/access/'+token+'/qr.svg'} alt="QR-код подписки" width="160" height="160"/><figcaption>Сканируйте в приложении для подключения</figcaption></figure>:<div className="account-qr-paused"><QrCode size={42}/><span>QR-код появится после возобновления доступа</span></div>}</div></section>
      <section className="account-usage" aria-labelledby="usage-heading"><div className="account-section-heading"><h2 id="usage-heading">Использование</h2><span>Общий расход всех устройств</span></div><dl className="account-usage-values"><div><dt><Download size={17}/>Получено</dt><dd>{formatBytes(access.downloaded||0)}</dd></div><div><dt><Upload size={17}/>Отправлено</dt><dd>{formatBytes(access.uploaded||0)}</dd></div><div><dt><Activity size={17}/>Всего</dt><dd>{formatBytes(state.used)}</dd></div></dl></section>
      {session?<SupportChat api={api} csrf={access.csrf||session.csrf}/>:<a className="button secondary" href="/account">Войти и написать в техподдержку</a>}
      <PartnerPanel partner={access.partner} terms={currentSettings.offer_terms} copy={copy}/><SpeedCheck/>
      {session&&<AccountPassword api={api} csrf={access.csrf||session.csrf} Button={Button} onSessionExpired={onSessionExpired} onChanged={result=>{setAccess(result);onSessionUpdate?.(result);}}/>}
      <div className="account-device-guide"><PlatformGuide subscriptionUrl={access.subscription_url} singBoxUrl={access.sing_box_url} singBoxNaiveUrl={access.sing_box_naive_url} active={state.status==='active'}/></div>
      <section className="account-renewal" id="renewal"><div><h2>Нужно продлить доступ?</h2><p>Срок и лимит меняет владелец сервиса. Напишите ему и укажите имя «{access.name}». После продления ваша ссылка и настройки в приложении сохранятся.</p>{!support&&<p className="renewal-no-contact">Свяжитесь с тем, кто отправил вам персональную ссылку. Контакт для связи на сайте пока не указан.</p>}</div>{support&&<a className="button primary" href={support} target="_blank" rel="noreferrer">Связаться с владельцем<ArrowUpRight size={17}/></a>}</section>
      <p className="account-updated">{updated?'Данные обновлены в '+new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Krasnoyarsk'}).format(new Date(updated*1000)):'Загружаем данные'} · Автообновление каждые 15 секунд · Красноярск, UTC+7</p>
    </>}
  </div></Shell>;
}
