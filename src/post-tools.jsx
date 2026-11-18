import {Bold, Italic, Underline, Strikethrough, EyeOff, Quote, ListCollapse, Code, SquareCode, Link2, CalendarClock, Smile} from 'lucide-react';
import React,{useRef,useState} from 'react';

const marks=[
  ['b','Жирный',Bold],['i','Курсив',Italic],['u','Подчёркнутый',Underline],['s','Зачёркнутый',Strikethrough],['spoiler','Спойлер',EyeOff],
  ['quote','Цитата',Quote],['fold','Сворачиваемая цитата',ListCollapse],['code','Код',Code],['pre','Блок кода',SquareCode],
  ['link','Ссылка',Link2],['time','Дата в тексте',CalendarClock],['symbols','Эмодзи и метки',Smile],
];
export function PostTools({editor,text,onChange}){
  const [panel,setPanel]=useState(''),[value,setValue]=useState(''),[error,setError]=useState('');
  const range=useRef([0,0]);
  function insert(tag,arg='',literal){
    const [start,end]=range.current;
    const chosen=text.slice(start,end)||(tag==='time'?value.replace('T',' '):'текст');
    const before=literal===undefined?'['+tag+(arg?'='+arg:'')+']':'';
    const content=literal??chosen;
    onChange(text.slice(0,start)+before+content+(literal===undefined?'[/'+tag+']':'')+text.slice(end));
    setPanel('');setError('');
    requestAnimationFrame(()=>{editor.current?.focus();editor.current?.setSelectionRange(start+before.length,start+before.length+content.length);});
  }
  function choose(tag){
    const field=editor.current;range.current=[field.selectionStart,field.selectionEnd];
    if(['link','pre','time','symbols'].includes(tag)){setPanel(tag);setValue('');setError('');return;}
    insert(tag);
  }
  function apply(){
    const v=value.trim();
    if(panel==='link'&&!/^https?:\/\/[^\s\]]+$/i.test(v)){setError('Введите адрес с https:// или http://');return;}
    if(panel==='time'){
      const stamp=Date.parse(v+':00+07:00')/1000;
      if(!Number.isFinite(stamp)){setError('Выберите дату и время');return;}
      insert(panel,String(stamp));return;
    }
    insert(panel,v);
  }
  return <div className="post-tools"><div role="group" aria-label="Оформление текста" className="post-marks">
    {marks.map(([tag,label,Icon])=><button type="button" key={tag} className="post-format-icon" title={label} aria-label={label} onMouseDown={e=>e.preventDefault()} onClick={()=>choose(tag)}><Icon size={18} aria-hidden="true"/></button>)}
  </div>{panel&&<div className="post-tool-input">{panel==='symbols'?<div className="post-marks">{['📌','📣','✨','✅','❤️','🔥','🎉','💬','#тема','@username'].map(char=><button key={char} type="button" onClick={()=>insert('', '',char)}>{char}</button>)}</div>:<>
    <label>{panel==='link'?'Адрес ссылки':panel==='pre'?'Язык кода (необязательно)':'Дата и время · Красноярск'}
    <input type={panel==='time'?'datetime-local':panel==='link'?'url':'text'} value={value} autoFocus onChange={e=>setValue(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();apply();}}}/></label>
    <button type="button" className="button secondary" onClick={apply}>Вставить</button></>}
    <button type="button" className="text-link" onClick={()=>setPanel('')}>Отмена</button>{error&&<small role="alert">{error}</small>}</div>}</div>;
}

function Secret({children}){
  const [revealed,setRevealed]=useState(false);
  return <span className={'post-secret'+(revealed?' revealed':'')} onClick={()=>setRevealed(!revealed)} role="button" tabIndex={0} aria-label="Показать или скрыть спойлер" onKeyDown={e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();setRevealed(!revealed);}}}>{children}</span>;
}

export function PostPreview({text,entities}){
  const root={offset:0,length:text.length,children:[]},stack=[root];
  for(const e of entities){
    while(stack.length>1 && e.offset>=stack.at(-1).offset+stack.at(-1).length)stack.pop();
    const node={...e,children:[]};stack.at(-1).children.push(node);stack.push(node);
  }
  function render(node){
    let p=node.offset;const children=[];
    for(const child of node.children){
      children.push(text.slice(p,child.offset),<React.Fragment key={child.offset+'-'+child.type}>{render(child)}</React.Fragment>);
      p=child.offset+child.length;
    }
    children.push(text.slice(p,node.offset+node.length));
    switch(node.type){
      case 'bold':return <strong>{children}</strong>;
      case 'italic':return <em>{children}</em>;
      case 'underline':return <u>{children}</u>;
      case 'strikethrough':return <s>{children}</s>;
      case 'spoiler':return <Secret>{children}</Secret>;
      case 'blockquote':return <blockquote>{children}</blockquote>;
      case 'expandable_blockquote':return <details><summary>Цитата</summary><blockquote>{children}</blockquote></details>;
      case 'code':return <code>{children}</code>;
      case 'pre':return <pre><code>{children}</code></pre>;
      case 'text_link':return <a href={node.url} target="_blank" rel="noreferrer">{children}</a>;
      case 'date_time':return <time>{new Date(node.unix_time*1000).toLocaleString('ru-RU')}</time>;
      default:return children;
    }
  }
  return <div className="post-preview-text">{render(root)}</div>;
}
