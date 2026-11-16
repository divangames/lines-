import React, {useState, useEffect, useCallback} from 'react';
import {UserRound, ShieldCheck, ArrowRight, ArrowUpRight, Eye, EyeOff, LogIn} from 'lucide-react';

export function PasswordField({id,value,onChange,autoComplete='new-password',placeholder='',required=false,minLength=12,readOnly=false,disabled=false,label='Пароль',...inputProps}) {
  const [visible,setVisible]=useState(false);
  return <div className="password-field"><input id={id} aria-label={label} type={visible?'text':'password'} value={value} onChange={onChange} autoComplete={autoComplete} placeholder={placeholder} required={required} minLength={minLength} maxLength={256} readOnly={readOnly} disabled={disabled} spellCheck={false} {...inputProps}/><button type="button" className="icon-button" disabled={disabled} aria-label={visible?'Скрыть пароль':'Показать пароль'} aria-pressed={visible} onClick={()=>setVisible(!visible)}>{visible?<EyeOff size={18}/>:<Eye size={18}/>}</button></div>;
}

export function AccountGate({settings,api,Shell,Button,AccountPage,show}) {
  const [session,setSession]=useState(undefined);
  const [username,setUsername]=useState('');
  const [password,setPassword]=useState('');
  const [remember,setRemember]=useState(true);
  const [busy,setBusy]=useState(false);
  const [signingOut,setSigningOut]=useState(false);
  const [error,setError]=useState('');
  useEffect(()=>{let alive=true;api('/api/account/me').then(data=>{if(alive)setSession(data);}).catch(failure=>{if(alive){setSession(null);if(failure.status!==401)setError('Не удалось проверить вход. Попробуйте войти ещё раз.');}});return()=>{alive=false;};},[api]);
  const expired=useCallback(()=>{setSession(null);setError('Сессия завершена. Войдите ещё раз.');},[]);
  const updateSession=useCallback(data=>setSession(current=>current&&current.csrf!==data.csrf?data:current),[]);
  const logout=useCallback(async()=>{
    setSigningOut(true);
    try{
      try{await api('/api/account/logout',{method:'POST',headers:{'X-CSRF-Token':session.csrf}});}
      catch(failure){if(failure.status!==403)throw failure;const fresh=await api('/api/account/me');await api('/api/account/logout',{method:'POST',headers:{'X-CSRF-Token':fresh.csrf}});}
    }
    catch(failure){if(failure.status!==401){show('Не удалось выйти. Проверьте соединение и повторите',true);return;}}
    finally{setSigningOut(false);}
    setSession(null);setError('');setPassword('');
  },[api,session,show]);
  async function submit(event){
    event.preventDefault();setBusy(true);setError('');
    try{const data=await api('/api/account/login',{method:'POST',body:{username,password,remember}});setPassword('');setSession(data);}
    catch(failure){setError(failure.message);}
    finally{setBusy(false);}
  }
  if(session===undefined)return <Shell settings={settings} account><div className="account-page account-skeleton" role="status"><span className="sr-only">Проверяем вход в кабинет</span><div/><div/><div/></div></Shell>;
  if(session)return <AccountPage settings={settings} session={session} onLogout={logout} signingOut={signingOut} onSessionExpired={expired} onSessionUpdate={updateSession}/>;
  return <Shell settings={settings} selected="account"><section className="account-entry" id="connection"><div className="account-entry-copy"><span className="account-entry-icon"><UserRound size={30}/></span><h1>Личный кабинет</h1><p>Войдите один раз.<br/>Ваш доступ всегда под рукой.</p></div><form className="account-entry-form account-login-form" onSubmit={submit}><h2>Войти в кабинет</h2><p>Логин и пароль выдаёт владелец вместе с доступом к сервису.</p><label htmlFor="account-username">Логин</label><input id="account-username" autoComplete="username" autoCapitalize="off" spellCheck={false} value={username} onChange={event=>{setUsername(event.target.value);setError('');}} maxLength={64} required placeholder="Ваш логин"/><label htmlFor="account-password">Пароль</label><PasswordField id="account-password" label="Пароль" autoComplete="current-password" minLength={1} required value={password} onChange={event=>{setPassword(event.target.value);setError('');}} placeholder="Ваш пароль"/><label className="auth-remember"><input type="checkbox" checked={remember} onChange={event=>setRemember(event.target.checked)}/>Запомнить вход на 30 дней</label>{error&&<p className="field-error" role="alert">{error}</p>}<Button type="submit" disabled={busy}>{busy?'Входим…':'Войти'}{!busy&&<ArrowRight size={18}/>}</Button><p className="account-entry-note"><ShieldCheck size={16}/>Забыли пароль? Владелец сервиса может создать новый в панели управления.</p><a className="text-link" href="/account/link">У меня только персональная ссылка<ArrowUpRight size={15}/></a></form></section></Shell>;
}
