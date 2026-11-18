import {useReloadValue} from './reload-position';
import {TelegramNews} from './telegram-news';
// Переписка поддержки в личном кабинете и в панели администратора.
import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Paperclip, Send, Download} from 'lucide-react';
import './support.css';

const sizeLimit=8*1024*1024;
const partSize=32768;
const when=stamp=>new Date(stamp*1000).toLocaleString('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});

// Малые блоки проходят через существующее ограничение размера запроса на VPS.
async function uploadFile(api,path,options,key,file,setProgress){
  let done=0, next=0, failed=false;
  const count=Math.ceil(file.size/partSize);
  async function sendPart(){
    while(next<count && !failed){
      const i=next++;
      const bytes=new Uint8Array(await file.slice(i*partSize,(i+1)*partSize).arrayBuffer());
      try {
        await api(path+'/upload/'+key+'/'+i,{...options,method:'PUT',body:{data:btoa(String.fromCharCode(...bytes))}});
        setProgress(Math.round(++done/count*100));
      } catch(error){failed=true;throw error;}
    }
  }
  const result=await Promise.allSettled(Array.from({length:4},sendPart));
  const failure=result.find(r=>r.status==='rejected');
  if(failure)throw failure.reason;
}

export function SupportChat({api,path='/api/account/support',csrf,admin=false}){
  const [messages,setMessages]=useState([]),[older,setOlder]=useState(false),[text,setText]=useState('');
  const [file,setFile]=useState(null),[busy,setBusy]=useState(false),[progress,setProgress]=useState(0),[error,setError]=useState('');
  const key=useRef(crypto.randomUUID()),fileInput=useRef(null),list=useRef(null),follow=useRef(true);
  const refresh=useCallback(async(before=0)=>{
    const data=await api(path+(before?'?before='+before:''));
    setMessages(previous=>{
      const merge=new Map(previous.map(m=>[m.id,m]));
      for(const m of data.messages)merge.set(m.id,m);
      return [...merge.values()].sort((a,b)=>a.id-b.id);
    });
    if(before || !list.current?.dataset.paged)setOlder(data.older);
  },[api,path]);
  useEffect(()=>{
    const tick=()=>refresh().catch(e=>setError(e.message));
    tick();
    const timer=setInterval(()=>{if(!document.hidden)tick();},4500);
    return ()=>clearInterval(timer);
  },[refresh]);
  useEffect(()=>{if(follow.current && list.current)list.current.scrollTop=list.current.scrollHeight;},[messages]);
  async function send(event){
    event.preventDefault();
    if(!text.trim()&&!file)return;
    setError('');setBusy(true);setProgress(0);
    const options=csrf?{headers:{'X-CSRF-Token':csrf}}:{};
    try{
      if(file)await uploadFile(api,path,options,key.current,file,setProgress);
      await api(path,{...options,method:'POST',body:{key:key.current,text,filename:file?.name||'',size:file?.size||0}});
      key.current=crypto.randomUUID();setText('');setFile(null);fileInput.current.value='';follow.current=true;
      await refresh();
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  const labels={client:admin?'Клиент':'Вы',admin:admin?'Вы':'Техподдержка',service:'Линия',bot:'Помощник Линии'};
  return <section className="support-chat" id="support">
    <h2>{admin?'Переписка':'Техподдержка'}</h2>
    {older&&<button type="button" className="text-link" onClick={()=>{list.current.dataset.paged='1';follow.current=false;refresh(messages[0].id).catch(e=>setError(e.message));}}>Предыдущие сообщения</button>}
    <div className="support-history" ref={list} onScroll={e=>{const n=e.currentTarget;follow.current=n.scrollHeight-n.scrollTop-n.clientHeight<48;}}>
      {!messages.length&&<p>{admin?'В этом диалоге пока нет сообщений.':'Опишите проблему. Здесь сохранится переписка с поддержкой.'}</p>}
      {messages.map(m=><article key={m.id} className={m.role===(admin?'admin':'client')?'own':''}>
        <header><strong>{labels[m.role]}</strong><time>{when(m.stamp)}</time></header>
        {m.body&&<p>{m.body}</p>}
        {m.filename&&<a href={path+'/file/'+m.id} download><Download size={16}/>{m.filename}</a>}
        {admin&&m.role!=='client'&&m.delivery&&<small>{{sent:'Отправлено в Telegram',failed:'Telegram отклонил доставку',pending:'В очереди Telegram',skipped:'Уведомление устарело'}[m.delivery]}</small>}
      </article>)}
    </div>
    <form onSubmit={send}><label>Сообщение<textarea value={text} disabled={busy} onChange={e=>setText(e.target.value)} maxLength={file?1024:4000} rows={3}/></label>
      <div className="support-actions"><label className="button secondary"><Paperclip size={17}/> {file?file.name:'Прикрепить файл'}
        <input type="file" ref={fileInput} disabled={busy} onChange={e=>{const f=e.target.files[0];key.current=crypto.randomUUID();if(f?.size>sizeLimit){setError('Выберите файл до 8 МБ');e.target.value='';setFile(null);}else{setFile(f||null);setError('');}}}/></label>
        {file&&!busy&&<button type="button" className="text-link" onClick={()=>{setFile(null);fileInput.current.value='';}}>Убрать</button>}
        <button className="button primary" disabled={busy||(!file&&!text.trim())||(file&&text.length>1024)}><Send size={16}/>{busy?(file?progress+'%':'Отправляем…'):'Отправить'}</button>
      </div><small>Файл до 8 МБ{file?' · Подпись до 1024 символов':''}</small></form>
    {error&&<p role="alert" className="field-error">{error}</p>}
  </section>;
}

export function SupportAdmin({api,clients,show}){
  const [inbox,setInbox]=useState({threads:[],linked:false}),[thread,setThread]=useReloadValue('supportThread',()=>new URLSearchParams(location.search).get('chat')||'');
  const [destination,setDestination]=useReloadValue('supportPublisher','clients');
  const [bind,setBind]=useState(''),[receipt,setReceipt]=useState(''),[busy,setBusy]=useState(false);
  useEffect(()=>{
    const tick=()=>api('/api/admin/support').then(setInbox).catch(e=>show(e.message,true));
    tick();const timer=setInterval(()=>{if(!document.hidden)tick();},5000);return ()=>clearInterval(timer);
  },[api]);
  const [groupRefresh,setGroupRefresh]=useState({busy:false,name:'',error:''});
  const groupPending=useRef(false);
  const refreshGroup=useCallback(async()=>{
    if(groupPending.current)return;
    groupPending.current=true;
    setGroupRefresh(last=>({...last,busy:true,error:''}));
    try{
      const data=await api('/api/admin/support/group/refresh',{method:'POST'});
      setGroupRefresh({busy:false,name:data.groupName,error:''});
    }catch(e){setGroupRefresh(last=>({...last,busy:false,error:e.message}));}
    finally{groupPending.current=false;}
  },[api]);
  useEffect(()=>{if(destination==='group')refreshGroup();},[destination,refreshGroup]);
  async function act(action){
    setBusy(true);
    try{await action();}catch(e){show(e.message,true);}finally{setBusy(false);}
  }
  const clientOptions=clients.filter(c=>!inbox.threads.some(t=>t.id==='c-'+c.id));
  return <div className="support-admin">
    <section className="support-inbox admin-section"><div className="section-header"><h2>Чаты</h2></div><label>Выберите диалог<select value={thread} onChange={e=>{setThread(e.target.value);setReceipt('');const url=new URL(location.href);url.searchParams.set('chat',e.target.value);history.replaceState(history.state,'',url);}}>
      <option value="">Выберите клиента</option>
      <optgroup label="Переписка">{inbox.threads.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</optgroup>
      <optgroup label="Клиенты">{clientOptions.map(c=><option key={c.id} value={'c-'+c.id}>{c.name}</option>)}</optgroup>
    </select></label>
    {thread&&<SupportChat key={thread} path={'/api/admin/support/'+encodeURIComponent(thread)} api={api} admin/>}
    {thread&&<details><summary>Подтверждение оплаты</summary><form onSubmit={e=>{e.preventDefault();act(async()=>{
      await api('/api/admin/support/'+encodeURIComponent(thread)+'/payment',{method:'POST',body:{reference:receipt}});
      setReceipt('');show('Подтверждение сохранено в диалоге');
    });}}><label>Номер подтверждённой операции<input value={receipt} maxLength={100} required onChange={e=>setReceipt(e.target.value)}/></label>
    <button className="button secondary" disabled={busy}>Подтвердить получение оплаты</button></form></details>}
    </section>
    <section className="support-notification settings-section"><h2>Уведомления администратору</h2><p>{inbox.linked?'Telegram подключён.':'Привяжите свой личный Telegram для уведомлений о сообщениях клиентов.'}</p>
    <button className="button secondary" disabled={busy} onClick={()=>act(async()=>setBind((await api('/api/admin/support/bind',{method:'POST'})).url))}>{inbox.linked?'Привязать другой Telegram':'Подключить Telegram'}</button>
    {bind&&<p><a href={bind} target="_blank" rel="noreferrer">Открыть бота для привязки</a> · Ссылка действует 10 минут</p>}</section>
    <section className="support-publisher admin-section"><div className="section-header"><h2>Публикации в Telegram</h2></div>
      <div className="publisher-switch" aria-label="Получатели публикации">
        <button type="button" aria-pressed={destination==='clients'} onClick={()=>setDestination('clients')}>Новости клиентам</button>
        <button type="button" aria-pressed={destination==='group'} onClick={()=>setDestination('group')}>Пост в группу</button>
      </div>
      <div hidden={destination!=='clients'}><TelegramNews api={api} uploadFile={uploadFile}/></div>
      <div hidden={destination!=='group'}><TelegramNews api={api} uploadFile={uploadFile} group groupName={groupRefresh.name||inbox.groupName} refreshGroup={refreshGroup} groupRefresh={groupRefresh}/></div>
    </section>
  </div>;
}
