// Регистрация на сайте и вход из меню Telegram.
import React, {useState} from 'react';

let launchPromise;

// Telegram передаёт подписанные данные запуска во фрагменте URL.
export function miniLaunch(api) {
  if (location.pathname.replace(/\/$/, '') !== '/account/mini') return api('/api/account/me');
  if (!launchPromise) {
    const data = new URLSearchParams(location.hash.slice(1)).get('tgWebAppData');
    const script = document.createElement('script');
    script.src = 'https://telegram.org/js/telegram-web-app.js';
    script.onload = () => { window.Telegram?.WebApp.ready(); window.Telegram?.WebApp.expand(); };
    document.head.appendChild(script);
    launchPromise = data ? api('/api/account/telegram', {method:'POST', body:{data}}) : api('/api/account/me');
  }
  return launchPromise;
}

// Ссылку на подтверждение открывает сам пользователь после создания заявки.
export function RegistrationForm({api, Button, onLogin}) {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setBusy(true);
    setError('');
    try {
      const result = await api('/api/account/register', {method:'POST', body:Object.fromEntries(fields)});
      setUrl(result.url);
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }
  return <form className="account-entry-form account-login-form" onSubmit={submit}>
    <h2>{url ? 'Подтвердите телефон' : 'Попробовать VPN'}</h2>
    {url ? <>
      <p>Откройте личный чат, нажмите «Старт» и поделитесь своим номером. Бот пришлёт пароль. Ссылка действует 15 минут.</p>
      <a className="button primary" href={url} onClick={event=>{
        if(window.Telegram?.WebApp?.initData){event.preventDefault();window.Telegram.WebApp.openTelegramLink(url);window.Telegram.WebApp.close();}
      }}>Перейти в Telegram</a>
      <button type="button" className="text-link" onClick={()=>setUrl('')}>Изменить данные</button>
    </> : <>
      <p>🇵🇱 Польша · 48 часов · 5 ГБ. Для регистрации нужен Telegram с этим номером.</p>
      <label htmlFor="trial-name">Имя для VPN-профиля</label>
      <input id="trial-name" name="name" autoComplete="given-name" maxLength={80} required/>
      <label htmlFor="trial-phone">Телефон с кодом страны</label>
      <input id="trial-phone" name="phone" type="tel" autoComplete="tel" placeholder="+7 999 123 45 67" maxLength={32} required/>
      {error && <p className="field-error" role="alert">{error}</p>}
      <Button type="submit" disabled={busy}>{busy?'Готовим ссылку…':'Продолжить в Telegram'}</Button>
    </>}
    <button type="button" className="text-link" onClick={onLogin}>Уже есть доступ? Войти</button>
  </form>;
}
