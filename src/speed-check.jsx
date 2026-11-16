import React, {useEffect, useId, useRef, useState} from 'react';
import {Activity, ArrowDown, ArrowUp, Play, RotateCw, Square} from 'lucide-react';
import './speed-check.css';

const origin = 'https://speed.cloudflare.com';
const sampleBytes = 2 * 1024 * 1024;
const formatRate = new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 1});
const median = values => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
const mbps = (bytes, milliseconds) => bytes * 8 / (1000 * Math.max(milliseconds, 1));
const ticks = [0, 10, 50, 100, 500, 1000];
const phases = {
  idle: 'Готов к проверке', latency: 'Измеряем задержку', download: 'Измеряем загрузку',
  upload: 'Измеряем отдачу', done: 'Проверка завершена', stopped: 'Проверка остановлена',
  timeout: 'Время проверки истекло', error: 'Проверка прервалась',
};

function dialPosition(value) {
  const upper = ticks.findIndex(tick => tick >= value);
  if (upper < 0) return 1;
  if (upper === 0) return 0;
  const fraction = (value - ticks[upper - 1]) / (ticks[upper] - ticks[upper - 1]);
  return (upper - 1 + fraction) / (ticks.length - 1);
}

// A 216-degree sweep leaves room for the digital readout beneath the hub.
function polar(fraction, radius) {
  const angle = Math.PI * (0.9 + 1.2 * fraction);
  return {x: 155 + radius * Math.cos(angle), y: 130 + radius * Math.sin(angle)};
}

function Dial({value, label}) {
  const position = dialPosition(value ?? 0);
  const start = polar(0, 84);
  const end = polar(1, 84);
  const curve = `M ${start.x} ${start.y} A 84 84 0 1 1 ${end.x} ${end.y}`;
  return <div className="speed-dial" aria-hidden="true">
    <svg viewBox="0 0 310 225" focusable="false">
      <path className="speed-track" d={curve}/>
      {position > 0 && <path className="speed-fill" d={curve} pathLength="100" strokeDasharray={`${position * 100} 100`}/>}
      {Array.from({length: 26}, (_, i) => {
        const major = i % 5 === 0;
        const a = polar(i / 25, 93);
        const b = polar(i / 25, major ? 101 : 97);
        return <line key={i} className={major ? 'speed-tick major' : 'speed-tick'} x1={a.x} y1={a.y} x2={b.x} y2={b.y}/>;
      })}
      {ticks.map((tick, i) => {
        const p = polar(i / (ticks.length - 1), 117);
        return <text key={tick} className="speed-tick-label" x={p.x} y={p.y + 4}>{tick === 1000 ? '1000+' : tick}</text>;
      })}
      <g className="speed-needle" transform={`rotate(${162 + 216 * position} 155 130)`}>
        <path d="M 151 127.5 L 234 129.4 Q 236 130 234 130.6 L 151 132.5 Z"/>
      </g>
      <circle cx="155" cy="130" r="7" className="speed-hub"/>
      <circle cx="155" cy="130" r="2.5" className="speed-hub-dot"/>
      <text x="155" y="178" className="speed-digits">{value == null ? '—' : formatRate.format(value)}</text>
      <text x="155" y="201" className="speed-unit">{label} · Мбит/с</text>
    </svg>
  </div>;
}

function testUrl(upload, bytes) {
  const url = new URL(upload ? '/__up' : '/__down', origin);
  url.searchParams.set('sample', crypto.randomUUID());
  if (!upload) url.searchParams.set('bytes', String(bytes));
  return url;
}

export function SpeedCheck() {
  const heading = useId();
  const active = useRef(null);
  const [phase, setPhase] = useState('idle');
  const [live, setLive] = useState(null);
  const [results, setResults] = useState({});
  useEffect(() => () => {
    active.current?.abort();
    active.current = null;
  }, []);

  async function run() {
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    const timeout = setTimeout(() => controller.abort('timeout'), 90000);
    const options = {signal: controller.signal, credentials: 'omit', referrerPolicy: 'no-referrer'};
    const block = new Uint8Array(sampleBytes / 2);
    let lastUpdate = 0;
    function showRate(bytes, start, force = false) {
      const now = performance.now();
      const rate = mbps(bytes, now - start);
      if (active.current === controller && !controller.signal.aborted && (force || now - lastUpdate >= 90)) {
        setLive(rate);
        lastUpdate = now;
      }
      return rate;
    }
    async function latency() {
      const start = performance.now();
      const response = await fetch(testUrl(false, 0), options);
      if (!response.ok || (await response.arrayBuffer()).byteLength !== 0) throw new Error();
      return performance.now() - start;
    }
    async function download() {
      const start = performance.now();
      const response = await fetch(testUrl(false, sampleBytes), options);
      if (!response.ok) throw new Error();
      const reader = response.body.getReader();
      let bytes = 0;
      try {
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) break;
          bytes += chunk.value.byteLength;
          showRate(bytes, start);
        }
      } finally {
        reader.releaseLock();
      }
      if (bytes !== sampleBytes) throw new Error();
      return showRate(bytes, start, true);
    }
    async function upload() {
      const start = performance.now();
      let confirmed = 0;
      // A successful HTTP response confirms the block reached the remote endpoint.
      // Counting both blocks over the same interval gives the aggregate upload rate.
      await Promise.all([0, 1].map(async () => {
        const response = await fetch(testUrl(true), {...options, method: 'POST', body: block});
        if (!response.ok) throw new Error();
        await response.arrayBuffer();
        confirmed += block.byteLength;
        showRate(confirmed, start, true);
      }));
      return mbps(confirmed, performance.now() - start);
    }

    setResults({});
    setLive(null);
    setPhase('latency');
    try {
      await latency();
      const delays = [];
      for (let i = 0; i < 3; i++) delays.push(await latency());
      setResults({latency: Math.round(median(delays))});
      for (const [key, measure] of [['download', download], ['upload', upload]]) {
        setPhase(key);
        setLive(null);
        const samples = [];
        for (let i = 0; i < 3; i++) samples.push(await measure());
        setResults(current => ({...current, [key]: median(samples)}));
      }
      setPhase('done');
    } catch {
      if (active.current === controller) {
        setPhase(controller.signal.reason === 'timeout' ? 'timeout' : controller.signal.aborted ? 'stopped' : 'error');
      }
    } finally {
      clearTimeout(timeout);
      controller.abort();
      if (active.current === controller) active.current = null;
    }
  }

  const busy = ['latency', 'download', 'upload'].includes(phase);
  const dialValue = busy ? live : results.download;
  const StartIcon = phase === 'idle' ? Play : RotateCw;
  return <section className="speed-check" aria-labelledby={heading}>
    <header className="speed-heading"><h2 id={heading}>Скорость интернета</h2>
      <p>От этого устройства до Cloudflare по текущему маршруту.</p>
    </header>
    <div className="speed-panel">
      <Dial value={dialValue} label={phase === 'upload' ? 'Отдача' : 'Загрузка'}/>
      <div className="speed-details">
        <dl className="speed-results">
          {[[ArrowDown, 'download', 'Загрузка'], [ArrowUp, 'upload', 'Отдача'], [Activity, 'latency', 'Задержка HTTPS']].map(([Icon, key, name]) => {
            const value = key === phase && key !== 'latency' ? live : results[key];
            return <div className={phase === key ? 'is-measuring' : ''} key={key}>
              <dt><Icon size={17} aria-hidden="true"/>{name}</dt>
              <dd>{value == null ? '—' : formatRate.format(value)} <span>{key === 'latency' ? 'мс' : 'Мбит/с'}</span></dd>
            </div>;
          })}
        </dl>
        <div className="speed-controls">
          {busy ? <button type="button" className="speed-stop" onClick={() => active.current?.abort('user')}><Square size={14} aria-hidden="true"/>Остановить</button>
            : <button type="button" className="speed-start" onClick={run}><StartIcon size={16} aria-hidden="true"/>{phase === 'idle' ? 'Проверить скорость' : 'Проверить снова'}</button>}
          <span className="speed-status" role="status">{phase === 'idle' ? 'Около 12 МиБ' : phases[phase]}</span>
        </div>
      </div>
    </div>
  </section>;
}
