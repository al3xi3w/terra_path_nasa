// Guarda la app en el teléfono la primera vez. Las teselas del mapa que el usuario ya vio
// también se guardan (solo las vistas, nunca una descarga masiva: política de uso de OpenStreetMap).
// Cambia VERSION cada vez que se regeneren los datos (scripts/build_app.py lo hace solo).
const VERSION = 'terrapath-8263ab6633';
const TILES = 'terrapath-tiles';
const MAX_TILES = 400;
const FILES = ['./', 'index.html', 'styles.css', 'app.js', 'i18n.js', 'data/app_data.js', 'manifest.webmanifest', 'icon.svg',
  'icons/icon-192.png', 'icons/icon-512.png', 'icons/icon-maskable-512.png', 'icons/apple-touch-icon.png',
  'vendor/leaflet/leaflet.js', 'vendor/leaflet/leaflet.css'];
self.addEventListener('install', e => e.waitUntil(caches.open(VERSION).then(c => c.addAll(FILES)).then(() => self.skipWaiting())));
self.addEventListener('activate', e => e.waitUntil(
  caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION && k !== TILES).map(k => caches.delete(k)))).then(() => self.clients.claim())));
async function tile(request) {
  const cache = await caches.open(TILES);
  const hit = await cache.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  if (response.ok) {
    await cache.put(request, response.clone());
    const keys = await cache.keys();
    if (keys.length > MAX_TILES) await cache.delete(keys[0]);
  }
  return response;
}
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  if (new URL(e.request.url).hostname === 'tile.openstreetmap.org') return e.respondWith(tile(e.request));
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request)));
});
