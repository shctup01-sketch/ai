// Offline support for the installed app.
// The page itself and version.json always come from the network first, so a new
// patch shows up on the next launch; the big, unchanging files (3D models, three.js)
// are kept in a cache so the game starts fast and works without a connection.
const CACHE = 'dino-pixel-assets-v1';
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
const isAsset = u => u.pathname.includes('/models/') || u.hostname === 'cdn.jsdelivr.net' || /\.(png|webp|webmanifest)$/.test(u.pathname);
self.addEventListener('fetch', e => {
  const req = e.request; if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.pathname.endsWith('version.json')) return;   // never cached: it is how updates are noticed
  if (isAsset(url)) {
    e.respondWith(caches.open(CACHE).then(c => c.match(req).then(hit => hit || fetch(req).then(res => {
      if (res.ok || res.type === 'opaque') c.put(req, res.clone()); return res; }))));
    return;
  }
  if (url.origin === location.origin) {
    e.respondWith(fetch(req, { cache: 'no-store' }).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); } return res;
    }).catch(() => caches.match(req, { ignoreSearch: true }).then(hit => hit || caches.match('index.html'))));
  }
});
