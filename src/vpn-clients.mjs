export function inferredPlatform(device = navigator) {
  const agent = device.userAgent;
  if (/Android/.test(agent)) return 'android';
  if (/iPhone|iPad|iPod/.test(agent) || (/Macintosh/.test(agent) && device.maxTouchPoints > 1)) return 'ios';
  return /Mac/.test(agent) ? 'macos' : 'windows';
}

const iosClients = [
  {
    name: 'v2RAGE',
    download: 'https://apps.apple.com/app/v2rage/id6761075402',
    importLink: url => 'v2rage://import?url=' + encodeURIComponent(url),
    manual: 'В v2RAGE откройте «Настройки» → «Импортировать подписку», вставьте ссылку и подтвердите добавление.',
  },
  {
    name: 'INCY',
    download: 'https://apps.apple.com/app/incy/id6756943388',
    importLink: url => 'incy://import/' + url,
    manual: 'В INCY нажмите «+», добавьте подписку из буфера обмена и подтвердите импорт.',
  },
];

const otherClients = [
  {name: 'Happ', download: 'https://happ.info/', importLink: url => 'happ://add/' + url},
  {name: 'v2RayTun', download: 'https://v2raytun.com/', importLink: url => 'v2raytun://import/' + url},
];

export function clientsFor(platform) {
  return platform === 'ios' ? iosClients : otherClients;
}
