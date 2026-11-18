import {RefreshCw} from 'lucide-react';
import {PostTools,PostPreview} from './post-tools';
// Редактор и предпросмотр публикации перед постановкой в очередь Telegram.
import {draftPhoto,useReloadValue} from './reload-position';
import React,{useRef,useEffect,useState} from 'react';

const zone='Asia/Krasnoyarsk';
const formatTime=stamp=>new Intl.DateTimeFormat('ru-RU',{dateStyle:'long',timeStyle:'short',timeZone:zone}).format(stamp*1000);
const maxSize=8*1024*1024;

async function loadPhoto(file){
  if(!['image/jpeg','image/png'].includes(file.type)||file.size>maxSize)throw Error('Выберите фото JPEG или PNG до 8 МБ.');
  const url=await new Promise((resolve,reject)=>{
    const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Не удалось прочитать фото.'));
    reader.readAsDataURL(file);
  });
  const image=new Image();image.src=url;
  try{await image.decode();}catch{throw Error('Не удалось открыть изображение.');}
  const w=image.naturalWidth,h=image.naturalHeight;
  if(w+h>10000 || Math.max(w/h,h/w)>20)throw Error('Для Telegram уменьшите фото: сумма сторон до 10 000 пикселей, соотношение до 20:1.');
  return {file,url};
}

function formattedPost(text){
  const pattern=/(\*\*|__)([\s\S]+?)\1/g;
  const pieces=[];let pos=0;
  for(const m of text.matchAll(pattern)){
    pieces.push(text.slice(pos,m.index),m[1]==='**'?<strong key={m.index}>{m[2]}</strong>:<em key={m.index}>{m[2]}</em>);
    pos=m.index+m[0].length;
  }
  return [...pieces,text.slice(pos)];
}

export function TelegramNews({api,uploadFile,group=false,groupName,refreshGroup,groupRefresh}){
  const scope=group?'group':'news';
  const editor=useRef(null);
  const [text,setText]=useReloadValue(scope+'Text',''),[photo,setPhoto]=useState(null),[mode,setMode]=useReloadValue(scope+'Mode','now');
  const [date,setDate]=useReloadValue(scope+'Date',''),[time,setTime]=useReloadValue(scope+'Time',''),[snapshot,setSnapshot]=useReloadValue(scope+'Preview',null);
  const [busy,setBusy]=useState(false),[reading,setReading]=useState(false),[progress,setProgress]=useState(0);
  const [error,setError]=useState(''),[result,setResult]=useState('');
  const [key,setKey]=useReloadValue(scope+'Key',()=>crypto.randomUUID()),[hasPhoto,setHasPhoto]=useReloadValue(scope+'HasPhoto',false);
  const [photoSpoiler,setPhotoSpoiler]=useReloadValue(scope+'PhotoSpoiler',false);
  const [captionAbove,setCaptionAbove]=useReloadValue(scope+'CaptionAbove',false);
  const [hideLink,setHideLink]=useReloadValue(scope+'HideLink',false);
  const [linkSize,setLinkSize]=useReloadValue(scope+'LinkSize','auto'),[linkAbove,setLinkAbove]=useReloadValue(scope+'LinkAbove',false);
  const [reveal,setReveal]=useState(false);
  const sending=useRef(false);
  const draft=snapshot?{...snapshot,photo}:null;
  useEffect(()=>{
    if(!hasPhoto||photo)return;
    let active=true;
    setReading(true);
    draftPhoto(key).then(file=>{if(!file)throw Error();return loadPhoto(file);}).then(restored=>{if(active)setPhoto(restored);})
      .catch(()=>{if(active){setSnapshot(null);setHasPhoto(false);setError('Выберите фото повторно.');}})
      .finally(()=>{if(active)setReading(false);});
    return ()=>{active=false;};
  },[]);
  function removePhoto(){
    draftPhoto(key,null).catch(()=>{});setPhoto(null);setHasPhoto(false);setKey(crypto.randomUUID());
  }

  async function choose(e){
    const file=e.target.files[0];e.target.value='';if(!file)return;
    setReading(true);setError('');setResult('');
    try{const next=await loadPhoto(file);const nextKey=crypto.randomUUID();await draftPhoto(nextKey,file);if(hasPhoto)draftPhoto(key,null).catch(()=>{});setKey(nextKey);setHasPhoto(true);setPhoto(next);}
    catch(failure){setError(failure.message);}
    finally{setReading(false);}
  }
  async function preview(e){
    e.preventDefault();setError('');setResult('');
    const at=mode==='later'?Date.parse(date+'T'+time+':00+07:00')/1000:0;
    if(mode==='later'&&(!Number.isFinite(at)||at<=Date.now()/1000)){setError('Выберите будущие дату и время по Красноярску.');return;}
    if(!photo&&!text.trim())return;
    setBusy(true);
    try{
      const source=!text.includes('[')?text.replace(/(\*\*|__)([\s\S]+?)\1/g,(_,mark,part)=>mark==='**'?'[b]'+part+'[/b]':'[i]'+part+'[/i]'):text;
      const result=await api('/api/admin/support/news/preview',{method:'POST',body:{key,text:source,filename:photo?.file.name||''}});
      setReveal(false);setSnapshot({source,text:result.text,entities:result.entities,at});
    }catch(failure){setError(failure.message);}finally{setBusy(false);}
  }
  async function confirm(){
    if(sending.current)return;
    if(draft.at && draft.at<=Date.now()/1000){setError('Время отправки прошло. Измените расписание.');return;}
    sending.current=true;setBusy(true);setError('');setProgress(0);
    try{
      const file=draft.photo?.file;
      if(file)await uploadFile(api,'/api/admin/support/news',{},key,file,setProgress);
      const r=await api('/api/admin/support/news',{method:'POST',body:{key,destination:group?'group':'clients',text:draft.source??draft.text,rich:draft.source!==undefined,photo_spoiler:photoSpoiler,caption_above:captionAbove,hide_link_preview:hideLink,link_size:linkSize,link_above:linkAbove,at:draft.at,filename:file?.name||'',size:file?.size||0}});
      setResult((draft.at?'Запланировано на '+formatTime(draft.at)+' (Красноярск).':'Новость поставлена в очередь.')+(group?' Группа: '+groupName+'.':' Получателей: '+r.count+'.'));
      removePhoto();setPhotoSpoiler(false);setCaptionAbove(false);setHideLink(false);setLinkSize('auto');setLinkAbove(false);setSnapshot(null);setText('');setMode('now');setDate('');setTime('');
    }catch(failure){setError(failure.message);}
    finally{sending.current=false;setBusy(false);}
  }
  const previewText=draft?.text && (draft.entities?<PostPreview text={draft.text} entities={draft.entities}/>:<p>{group?formattedPost(draft.text):draft.text}</p>);
  return <section className="news-composer"><h2>{group?'Опубликовать пост в группу':'Новости в Telegram'}</h2>{group&&<><p className="post-group-name"><span>{groupName?'Группа: '+groupName:groupRefresh.busy?'Получаем название…':'Группа Telegram не настроена'}</span><button type="button" className="icon-button" onClick={refreshGroup} disabled={groupRefresh.busy} aria-label="Обновить название группы" title="Обновить название группы"><RefreshCw size={16} aria-hidden="true"/></button></p>{groupRefresh.error&&<p role="alert" className="field-error">{groupRefresh.error}</p>}</>}
    {draft?<div className="news-preview" aria-label="Предпросмотр новости">
      <h3>Предпросмотр</h3><article>{draft.photo&&captionAbove&&previewText}{draft.photo&&(photoSpoiler&&!reveal?<button type="button" className="photo-cover" onClick={()=>setReveal(true)}>Показать скрытое фото</button>:<img src={draft.photo.url} alt="Фото новости"/>)}{(!draft.photo||!captionAbove)&&previewText}
      {!group&&<div className="news-bot-buttons" aria-label="Кнопки под сообщением"><span>Кабинет</span><span>Техподдержка</span></div>}</article>
      {!draft.photo&&/https?:\/\//i.test(draft.source||draft.text)&&<small>{hideLink?'Карточка ссылки отключена.':'Карточка ссылки '+(linkAbove?'над текстом':'под текстом')+' · '+({auto:'автоматический размер',small:'компактная',large:'крупная'}[linkSize])+'. Изображение подбирает Telegram.'}</small>}
      <p>{group?'Публикация в группе «'+groupName+'».':'Получатели: зарегистрированные клиенты Telegram.'}<br/>{draft.at?'Отправка '+formatTime(draft.at)+' · Красноярск (UTC+7)':'Отправка сразу после подтверждения.'}</p>
      <div className="support-actions"><button className="button secondary" disabled={busy} onClick={()=>{setSnapshot(null);setError('');}}>Редактировать</button>
      <button className="button primary" disabled={busy||reading||(hasPhoto&&!photo)} onClick={confirm}>{busy?(photo?'Отправляем… '+progress+'%':'Сохраняем…'):draft.at?'Подтвердить расписание':'Подтвердить отправку'}</button></div>
    </div>:<form onSubmit={preview}>
      <PostTools editor={editor} text={text} onChange={setText}/>
      <label>{group?'Текст поста':'Текст новости'}<textarea ref={editor} value={text} onChange={e=>setText(e.target.value)} rows={4} maxLength={20000} required={!photo}/></label>
      {photo&&<div className="news-photo"><img src={photo.url} alt="Выбранное фото"/><span>{photo.file.name}</span><button type="button" className="text-link" onClick={removePhoto}>Убрать фото</button></div>}
      <label>Фото к новости<input type="file" accept="image/jpeg,image/png" onChange={choose} disabled={reading}/><small>JPEG или PNG до 8 МБ. Подпись к фото — до 1024 символов.</small></label>
      <div className="post-options">{photo?<><label><input type="checkbox" checked={captionAbove} onChange={e=>setCaptionAbove(e.target.checked)}/>Подпись над фото</label><label><input type="checkbox" checked={photoSpoiler} onChange={e=>setPhotoSpoiler(e.target.checked)}/>Скрыть фото под спойлером</label></>:<label><input type="checkbox" checked={hideLink} onChange={e=>setHideLink(e.target.checked)}/>Отключить карточку ссылки в Telegram</label>}</div>
      {!photo&&!hideLink&&/https?:\/\//i.test(text)&&<div className="post-options"><label>Карточка ссылки<select value={linkSize} onChange={e=>setLinkSize(e.target.value)}><option value="auto">Автоматически</option><option value="small">Компактная</option><option value="large">Крупная</option></select></label><label><input type="checkbox" checked={linkAbove} onChange={e=>setLinkAbove(e.target.checked)}/>Карточка над текстом</label></div>}
      <fieldset><legend>Когда отправить</legend>{[['now','Сейчас'],['later','По расписанию']].map(([id,label])=><label key={id}><input type="radio" name={scope+'-time'} checked={mode===id} onChange={()=>setMode(id)}/>{label}</label>)}</fieldset>
      {mode==='later'&&<div className="news-schedule"><label>Дата<input type="date" value={date} onChange={e=>setDate(e.target.value)} required/></label>
      <label>Время<input type="time" value={time} onChange={e=>setTime(e.target.value)} required/></label><small>Красноярск (UTC+7)</small></div>}
      <button className="button primary" disabled={(group&&!groupName)||reading||(!text.trim()&&!photo)||busy}>{reading?'Читаем фото…':'Предпросмотр'}</button>
    </form>}
    {error&&<p role="alert" className="field-error">{error}</p>}{result&&<p role="status">{result}</p>}
  </section>;
}
