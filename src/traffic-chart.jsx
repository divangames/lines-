import React,{useId,useLayoutEffect,useRef,useState} from 'react';
import {useReloadValue} from './reload-position';

const width=900,height=168,pad=12;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const exact=new Intl.NumberFormat('ru-RU');
const shortDay=new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short'});
const fullDay=new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',year:'numeric'});

export function TrafficChart({history,formatBytes}){
  const [period,setPeriod]=useReloadValue('trafficPeriod',14);
  const [hover,setHover]=useState(null);
  const plot=useRef(null),tip=useRef(null),chart=useRef(null);
  const tipId=useId();
  const data=history.slice(-period),values=data.map(d=>d.uploaded+d.downloaded);
  const maximum=Math.max(1024,...values),total=values.reduce((sum,n)=>sum+n,0);
  const step=(width-pad*2)/Math.max(1,data.length-1);
  const x=i=>pad+i*step,y=i=>height-pad-values[i]/maximum*(height-pad*2);
  const item=hover&&data[hover.index];

  function point(event){
    if(!data.length)return;
    const rect=plot.current.getBoundingClientRect();
    const local=(event.clientX-rect.left)/rect.width*width;
    setHover({index:clamp(Math.round((local-pad)/step),0,data.length-1),left:event.clientX-rect.left,top:event.clientY-rect.top});
  }
  function choose(index){
    if(!data.length)return;
    const rect=plot.current.getBoundingClientRect();
    setHover({index,left:x(index)/width*rect.width,top:y(index)/height*rect.height});
  }
  function keyDown(event){
    if(event.key==='Escape'){setHover(null);return;}
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();
    choose(event.key==='Home'?0:event.key==='End'?data.length-1:clamp((hover?.index??0)+(event.key==='ArrowLeft'?-1:1),0,data.length-1));
  }
  useLayoutEffect(()=>{
    if(!item||!tip.current)return;
    const bounds=chart.current.getBoundingClientRect(),area=plot.current.getBoundingClientRect(),box=tip.current;
    const px=area.left+hover.left,py=area.top+hover.top;
    const left=clamp(px-box.offsetWidth/2,Math.max(6,bounds.left),Math.min(innerWidth-6,bounds.right)-box.offsetWidth);
    const top=py-box.offsetHeight-12>=6?py-box.offsetHeight-12:py+14;
    box.style.left=(left-bounds.left)+'px';
    box.style.top=(top-bounds.top)+'px';
  },[hover,item]);
  function changePeriod(next){setHover(null);setPeriod(next);}
  return <section className="traffic-section"><div className="section-header"><div><h2>Трафик</h2><p>{formatBytes(total)} за {period} дней</p></div>
    <div className="segmented">{[7,14].map(n=><button key={n} className={period===n?'selected':''} aria-pressed={period===n} onClick={()=>changePeriod(n)}>{n} дней</button>)}</div></div>
    <div className="chart" ref={chart}><div className="chart-scale"><span>{formatBytes(maximum)}</span><span>0 Б</span></div>
      <svg ref={plot} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" tabIndex={0}
        aria-label={`Трафик за ${period} дней. Выберите день стрелками влево и вправо.`} aria-describedby={item?tipId:undefined}
        onPointerMove={point} onPointerDown={point} onPointerLeave={()=>setHover(null)} onPointerCancel={()=>setHover(null)}
        onFocus={()=>choose(data.length-1)} onBlur={()=>setHover(null)} onKeyDown={keyDown}>
        <line x1="0" x2={width} y1={height/2} y2={height/2} className="chart-grid"/>
        <line x1="0" x2={width} y1={height-pad} y2={height-pad} className="chart-grid"/>
        {item&&<line x1={x(hover.index)} x2={x(hover.index)} y1={0} y2={height-pad} className="traffic-guide" vectorEffect="non-scaling-stroke"/>}
        <polyline points={values.map((_,i)=>x(i)+','+y(i)).join(' ')} className="chart-line" vectorEffect="non-scaling-stroke"/>
      </svg>
      {item&&<div className="traffic-tip" ref={tip} role="tooltip" id={tipId}>
        <strong>{fullDay.format(new Date(item.day+'T12:00:00'))}</strong>
        <dl>{[['Получено',item.downloaded],['Отправлено',item.uploaded],['Всего',values[hover.index]]].map(([label,n])=><div key={label}><dt>{label}</dt><dd>{exact.format(n)} Б</dd></div>)}</dl>
      </div>}
    </div>
    <div className="chart-dates">{data.filter((_,i)=>[0,Math.floor(data.length/2),data.length-1].includes(i)).map(d=><span key={d.day}>{shortDay.format(new Date(d.day+'T12:00:00'))}</span>)}</div>
    {total===0&&<p className="chart-empty">Здесь появится расход, когда кто-нибудь подключится</p>}
  </section>;
}
