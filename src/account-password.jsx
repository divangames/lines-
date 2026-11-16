import React, {useState} from 'react';
import {KeyRound, ShieldCheck, Check, ArrowRight} from 'lucide-react';
import {PasswordField} from './account-auth';

export function AccountPassword({api,csrf,onChanged,onSessionExpired,Button}) {
  const [current,setCurrent]=useState('');
  const [password,setPassword]=useState('');
  const [confirmation,setConfirmation]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState(null);
  const [saved,setSaved]=useState(false);
  function update(setter,value){setter(value);setError(null);setSaved(false);}
  function fail(message,field){setError({message,field});if(field)document.getElementById(field)?.focus();}
  async function submit(event){
    event.preventDefault();setError(null);setSaved(false);
    if(password!==confirmation){fail('Новые пароли не совпадают','user-confirm-password');return;}
    if(password===current){fail('Новый пароль должен отличаться от текущего','user-new-password');return;}
    setBusy(true);
    try{
      const result=await api('/api/account/password',{method:'POST',headers:{'X-CSRF-Token':csrf},body:{current_password:current,new_password:password,confirm_password:confirmation}});
      onChanged(result);setCurrent('');setPassword('');setConfirmation('');setSaved(true);
    }catch(failure){
      if(failure.status===401){onSessionExpired?.();return;}
      fail(failure.message,failure.message==='Текущий пароль неверен'?'user-current-password':undefined);
    }finally{setBusy(false);}
  }
  const inputProps=id=>({'aria-invalid':error?.field===id||undefined,'aria-describedby':error?.field===id?'user-password-error':undefined});
  return <section className="account-security" id="security" aria-labelledby="security-heading"><div className="account-section-heading"><h2 id="security-heading"><KeyRound size={20}/>Безопасность</h2></div><div className="account-security-panel"><div className="account-security-copy"><h3>Сменить пароль</h3><p>Измените пароль для входа в личный кабинет. Подписка и настройки VPN сохранятся.</p><p className="password-session-note"><ShieldCheck size={18}/>Вы останетесь в кабинете. Остальные сеансы будут завершены.</p></div><form className="account-password-form" onSubmit={submit}><div className="field"><label htmlFor="user-current-password">Текущий пароль</label><PasswordField id="user-current-password" label="Текущий пароль" autoComplete="current-password" minLength={1} required disabled={busy} value={current} onChange={event=>update(setCurrent,event.target.value)} {...inputProps('user-current-password')}/></div><div className="field"><label htmlFor="user-new-password">Новый пароль</label><PasswordField id="user-new-password" label="Новый пароль" required disabled={busy} value={password} onChange={event=>update(setPassword,event.target.value)} {...inputProps('user-new-password')}/><small>Не менее 12 символов.</small></div><div className="field"><label htmlFor="user-confirm-password">Повторите новый пароль</label><PasswordField id="user-confirm-password" label="Повторите новый пароль" required disabled={busy} value={confirmation} onChange={event=>update(setConfirmation,event.target.value)} {...inputProps('user-confirm-password')}/></div>{error&&<p className="field-error" id="user-password-error" role="alert">{error.message}</p>}{saved&&<p className="password-saved" role="status"><Check size={18}/>Пароль изменён. Остальные сеансы завершены.</p>}<Button type="submit" disabled={busy}>{busy?'Сохраняем…':'Сохранить новый пароль'}{!busy&&<ArrowRight size={17}/>}</Button></form></div></section>;
}
