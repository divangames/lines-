// Снимок открытого экрана принадлежит текущей записи истории браузера.
import {useLayoutEffect,useRef,useState} from 'react';

const reload=performance.getEntriesByType('navigation')[0]?.type==='reload';
const storageKey='linea.reload.screen';
let previous={};
try{
  if(reload)previous=JSON.parse(sessionStorage.getItem(storageKey)||'{}');
  sessionStorage.removeItem(storageKey);
}catch{previous={};}
const readers=new Map();
const protectedPage=/^\/(admin|account|connect)(\/|$)/.test(location.pathname);
if(protectedPage){
  window.addEventListener('pagehide',()=>{
    const data={};
    for(const [key,read] of readers)data[key]=read();
    try{sessionStorage.setItem(storageKey,JSON.stringify(data));}catch{}
  });
}

export function forgetScreen(){
  for(const key of Object.keys(previous))delete previous[key];
  try{sessionStorage.removeItem(storageKey);}catch{}
}

export function useReloadValue(key,initial){
  const [value,setValue]=useState(()=>Object.hasOwn(previous,key)?previous[key]:typeof initial==='function'?initial():initial);
  const ref=useRef(value);ref.current=value;
  useLayoutEffect(()=>{
    readers.set(key,()=>ref.current);
    return ()=>{readers.delete(key);delete previous[key];};
  },[key]);
  return [value,setValue];
}

export function usePagePosition(ready,scope){
  useLayoutEffect(()=>{
    if(!ready)return;
    const key='position:'+scope;
    const sections=()=>[...document.querySelectorAll('.account-page>section,.account-page>[id],.support-admin>section,.settings-layout>form')];
    const capture=()=>{
      const nodes=sections();
      const index=nodes.findLastIndex(node=>node.getBoundingClientRect().top<=80);
      return {y:scrollY,index,offset:index<0?0:nodes[index].getBoundingClientRect().top,
        drawer:document.querySelector('dialog[open]')?.scrollTop||0};
    };
    readers.set(key,capture);
    const saved=previous[key];
    delete previous[key];
    const target=/^#[\w-]+$/.test(location.hash)?document.getElementById(location.hash.slice(1)):null;
    function restore(){
      const node=saved&&sections()[saved.index];
      if(saved) window.scrollTo({top:node?scrollY+node.getBoundingClientRect().top-saved.offset:saved.y,behavior:'instant'});
      else if(target)target.scrollIntoView({behavior:'instant'});
      const dialog=document.querySelector('dialog[open]');
      if(dialog&&saved?.drawer)dialog.scrollTop=saved.drawer;
    }
    let observer,timer,frame;
    function stop(){observer?.disconnect();clearTimeout(timer);cancelAnimationFrame(frame);}
    if(saved||target){
      frame=requestAnimationFrame(restore);
      observer=new ResizeObserver(restore);observer.observe(document.body);
      timer=setTimeout(stop,1800);
      for(const event of ['wheel','touchstart','pointerdown','keydown'])window.addEventListener(event,stop,{passive:true});
    }
    return ()=>{stop();readers.delete(key);for(const event of ['wheel','touchstart','pointerdown','keydown'])window.removeEventListener(event,stop);};
  },[ready,scope]);
}

// Локальный черновик фото остаётся в этой вкладке при перезагрузке редактора.
export async function draftPhoto(key,value){
  const db=await new Promise((resolve,reject)=>{
    const open=indexedDB.open('linea-news-drafts',1);
    open.onupgradeneeded=()=>open.result.createObjectStore('photos');
    open.onsuccess=()=>resolve(open.result);open.onerror=()=>reject(open.error);
  });
  try{
    return await new Promise((resolve,reject)=>{
      const tx=db.transaction('photos',value===undefined?'readonly':'readwrite');
      const store=tx.objectStore('photos');
      const request=value===undefined?store.get(key):value===null?store.delete(key):store.put({file:value,stamp:Date.now()},key);
      if(value){const cursor=store.openCursor();cursor.onsuccess=()=>{const item=cursor.result;if(item){if(item.value.stamp<Date.now()-86400000)item.delete();item.continue();}};}
      tx.oncomplete=()=>resolve(value===undefined?request.result?.file:null);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);
    });
  }finally{db.close();}
}
