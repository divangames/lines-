export function parseAccessToken(value, baseUrl) {
  let token = value.trim();
  if (/^https?:\/\//i.test(token) || token.startsWith('/')) {
    const url = new URL(token, baseUrl);
    if (url.origin !== new URL(baseUrl).origin) throw new Error('foreign-origin');
    token = url.pathname.match(/^\/(?:connect|sub|account)\/([A-Za-z0-9_-]+)\/?$/)?.[1] || '';
  }
  if (!/^[A-Za-z0-9_-]{32,64}$/.test(token)) throw new Error('invalid-access');
  return token;
}

function plural(value, forms) {
  const last = value % 10, lastTwo = value % 100;
  return forms[last === 1 && lastTwo !== 11 ? 0 : last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14) ? 1 : 2];
}

export function remainingTime(seconds) {
  if (seconds <= 0) return 'Срок закончился';
  if (seconds < 3600) {
    const minutes = Math.max(1, Math.ceil(seconds / 60));
    return `${minutes} ${plural(minutes, ['минута', 'минуты', 'минут'])}`;
  }
  if (seconds < 86400) {
    const hours = Math.ceil(seconds / 3600);
    return `${hours} ${plural(hours, ['час', 'часа', 'часов'])}`;
  }
  const days = Math.ceil(seconds / 86400);
  return `${days} ${plural(days, ['день', 'дня', 'дней'])}`;
}

export function accountState(access, now = Date.now() / 1000) {
  const remaining = access.expires_at ? access.expires_at - now : null;
  const used = Math.max(0, access.used_bytes || 0);
  const quota = Math.max(0, access.quota_bytes || 0);
  const fraction = quota ? Math.min(used / quota, 1) : 0;
  let status = access.status;
  // Server status remains authoritative. Local time can advance an active expiry.
  if (status === 'active' && remaining !== null && remaining <= 0) status = 'expired';
  if (status === 'active' && quota && used >= quota) status = 'limited';
  const alerts = [];
  if (status === 'disabled') alerts.push({id:'disabled',tone:'neutral',title:'Доступ приостановлен',body:'Владелец отключил подключение. Свяжитесь с ним, чтобы уточнить условия возобновления.'});
  if (status === 'expired') alerts.push({id:'expiry',tone:'critical',title:'Срок доступа закончился',body:'Подключение остановлено. Для продления обратитесь к владельцу — ваша ссылка останется прежней.'});
  else if (remaining !== null && remaining > 0 && remaining <= 7 * 86400) alerts.push({id:'expiry',tone:remaining <= 86400?'critical':'warning',title:remaining<=86400?'Доступ закончится в ближайшие сутки':'Срок доступа скоро закончится',body:`До окончания: ${remainingTime(remaining)}. Продлите доступ у владельца заранее, чтобы оставаться на связи.`});
  if (status === 'limited' || (quota && used >= quota)) alerts.push({id:'traffic',tone:'critical',title:'Трафик закончился',body:'Общий лимит исчерпан. Попросите владельца увеличить его или продлить условия доступа.'});
  else if (fraction >= .8) alerts.push({id:'traffic',tone:fraction >= .95?'critical':'warning',title:fraction >= .95?'Трафик почти закончился':'Трафик подходит к концу',body:'Лимит общий для всех ваших устройств. Если трафик закончится, подключение будет приостановлено.'});
  return {status,remaining,used,quota,fraction,left:quota?Math.max(0,quota-used):null,alerts};
}
