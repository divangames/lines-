import React, {useEffect, useState} from 'react';
import {Copy} from 'lucide-react';
import './partners.css';

const defaults = {device_price:49, traffic_price:99, quarter_discount:null, year_discount:null, reward_days:7, router_help:'Разовая помощь'};
const fields = [
  ['device_price','Дополнительное устройство, ₽ в месяц',100000],
  ['traffic_price','Ещё 100 ГБ, ₽',100000],
  ['quarter_discount','Скидка за 3 месяца, %',100],
  ['year_discount','Скидка за 12 месяцев, %',100],
  ['reward_days','Бонус за первую оплату друга, дней',365],
  ['router_help','Настройка роутера']
];
function daysLabel(n) {
  const form = new Intl.PluralRules('ru').select(n);
  return n+' '+({one:'день', few:'дня', many:'дней'}[form]||'дней');
}
export function offerRows(terms=defaults) {
  const discount=value=>value ? value+'%' : 'По согласованию';
  return [
    ['Дополнительное устройство',terms.device_price+' ₽ в месяц'],
    ['Ещё 100 ГБ трафика',terms.traffic_price+' ₽'],
    ...(terms.quarter_discount===terms.year_discount ? [['Подписка на 3 или 12 месяцев',discount(terms.year_discount)]] :
      [['Подписка на 3 месяца',discount(terms.quarter_discount)],['Подписка на 12 месяцев',discount(terms.year_discount)]]),
    ['Друг оплатил подписку','+'+daysLabel(terms.reward_days)],['Настройка роутера',terms.router_help]
  ];
}
export function OffersForm({settings,api,onSaved,show}) {
  const [draft,setDraft]=useState(settings.offer_terms||defaults);
  const [busy,setBusy]=useState(false);
  async function submit(e) {
    e.preventDefault();setBusy(true);
    try {onSaved(await api('/api/admin/offers',{method:'PUT',body:draft}));show('Условия сохранены');}
    catch(error){show(error.message,true);} finally{setBusy(false);}
  }
  return <form className="settings-section" onSubmit={submit}><h2>Дополнительные условия</h2>
    <p>Цены и условия видны в разделе «Пакеты». Оставьте скидку пустой для согласования с клиентом.</p>
    <div className="offer-fields">{fields.map(([key,label,max])=><div className="field" key={key}><label htmlFor={'offer-'+key}>{label}</label>
      <input id={'offer-'+key} type={max?'number':'text'} min={key==='reward_days'||key.includes('discount')?1:0} max={max} maxLength={max?undefined:80}
        required={!key.includes('discount')} placeholder={key.includes('discount')?'По согласованию':undefined}
        value={draft[key]??''} onChange={e=>setDraft({...draft,[key]:max?(e.target.value===''?null:Number(e.target.value)):e.target.value})}/>
    </div>)}</div><button className="button primary" disabled={busy}>{busy?'Сохраняем…':'Сохранить условия'}</button></form>;
}
export function PartnerPanel({partner,terms=defaults,copy}) {
  if(!partner)return null;
  const url=location.origin+'/invite/'+partner.code;
  return <section className="partner-panel" id="partners"><h2>Партнёрская программа</h2>
    <p>Отправьте другу приглашение. После подтверждения его первой оплаты вы получите {daysLabel(terms.reward_days)} подписки.</p>
    <label htmlFor="partner-url">Ваша ссылка для приглашений</label>
    <div className="copy-field"><input id="partner-url" value={url} readOnly onFocus={e=>e.target.select()}/>
      <button type="button" className="icon-button" aria-label="Скопировать приглашение" onClick={()=>copy(url,'Приглашение скопировано')}><Copy size={18}/></button></div>
    <dl className="partner-counts">{[['Приглашено',partner.invited],['Оплатили',partner.paid],['Бонусных дней',partner.days]].map(([label,n])=><div key={label}><dt>{label}</dt><dd>{n}</dd></div>)}</dl></section>;
}
const plans = [['Личный',199,100],['Комфорт',349,300],['Семья',549,600]];

export function Invitation({code,settings,api}) {
  const [done,setDone]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  async function submit(e){
    e.preventDefault();
    const body=Object.fromEntries(new FormData(e.currentTarget));
    setBusy(true);setError('');
    try{await api('/api/invitations/'+code+'/join',{method:'POST',body});setDone(true);}
    catch(failure){setError(failure.message);}finally{setBusy(false);}
  }
  return <section className="partner-invite partner-panel"><h1>{done?'Заявка отправлена':'Вас пригласили в «Линию»'}</h1>
    {done?<div role="status"><p>Для оплаты сообщите владельцу выбранный логин. После подтверждения первой оплаты войдите в кабинет со своим паролем.</p>
      {settings.support_url&&<a className="button secondary" href={settings.support_url}>Связаться с владельцем</a>} <a className="button primary" href="/account">Перейти к входу</a></div>:
      <form onSubmit={submit}><p>Приглашение уже учтено. Выберите пакет на 30 дней и создайте логин для личного кабинета.</p>
        <label htmlFor="invite-plan">Пакет</label><select id="invite-plan" name="plan">{plans.map(([name,price,gb])=><option key={name} value={name}>{name} · {gb} ГБ · {price} ₽</option>)}</select>
        <label htmlFor="invite-login">Логин</label><input id="invite-login" name="account_username" pattern="[A-Za-z0-9][A-Za-z0-9._\-]{2,63}" placeholder="От 3 символов латиницей" required autoComplete="username"/>
        <label htmlFor="invite-password">Пароль</label><input id="invite-password" name="account_password" type="password" required minLength={12} maxLength={256} placeholder="Не менее 12 символов" autoComplete="new-password"/>
        {error&&<p role="alert">{error}</p>}<button className="button primary" disabled={busy}>{busy?'Отправляем…':'Отправить заявку'}</button></form>}</section>;
}

export function PendingInvitations({requests,api,refresh,show}){
  const [busy,setBusy]=useState(null);
  async function confirm(id){
    setBusy(id);
    try{await api('/api/admin/invitations/'+id+'/payment',{method:'POST'});await refresh();show('Доступ открыт, бонус начислен');}
    catch(error){show(error.message,true);}finally{setBusy(null);}
  }
  if(!requests?.length)return null;
  return <section className="admin-section"><h2>Ожидают первой оплаты</h2>{requests.map(r=><div className="partner-request" key={r.id}>
    <div><strong>{r.username}</strong><p>{r.plan} · {plans.find(([name])=>name===r.plan)?.[1]} ₽ · Пригласил: {r.partner_name}</p></div>
    <button className="button secondary" disabled={busy!==null} onClick={()=>confirm(r.id)}>{busy===r.id?'Сохраняем…':'Подтвердить первую оплату'}</button></div>)}</section>;
}
export function ReferralPayment({client,api,onChanged}) {
  const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  useEffect(()=>{let active=true;api('/api/admin/clients/'+client.id+'/referral').then(r=>{if(active)setData(r);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[client.id,api]);
  async function confirm(){setBusy(true);setError('');try{setData(await api('/api/admin/clients/'+client.id+'/referral/payment',{method:'POST'}));onChanged();}catch(e){setError(e.message);}finally{setBusy(false);}}
  if(!data&&!error)return null;
  return <section className="admin-account-panel"><h3>Приглашение</h3>{data&&<><p>Пригласил: {data.partner_name}. Бонус: {daysLabel(data.days)}.</p>
    {data.paid_at?<strong>Первая оплата подтверждена · бонус начислен</strong>:<button className="button secondary" disabled={busy} onClick={confirm}>{busy?'Сохраняем…':'Подтвердить первую оплату'}</button>}</>}
    {error&&<p role="alert">{error}</p>}</section>;
}
