const CACHE_NAME = 'cmms-full-cache-v12';
const CORE_ROUTES = [
  '/static/offline.html',
  '/static/css/app.css',
  '/static/css/legacy.css',
  '/static/vendor/bootstrap/bootstrap.bundle.min.js',
  '/static/vendor/bootstrap-icons/fonts/bootstrap-icons.woff2',
  '/static/vendor/alpine/alpine.min.js',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/fonts/bootstrap-icons.woff2',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
  'https://code.jquery.com/jquery-3.6.0.min.js',
  'https://unpkg.com/dexie@latest/dist/dexie.js',
  '/static/js/offline-db.js',
  '/static/js/offline-sync.js',
  '/static/images/favicon.png',
  '/static/images/logo_white.png',
  '/static/images/Logo Jaya Teknik.png',
  '/static/manifest.json'
];

// 1. Install Event: Pre-cache All Key System Routes & CDN Libraries
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[ServiceWorker] Pre-caching all main system pages, CDN libraries & assets');
      // Satu per satu: addAll bersifat atomik, satu berkas gagal membatalkan seluruh pre-cache
      return Promise.all(CORE_ROUTES.map(url =>
        cache.add(url).catch(err => console.warn('[ServiceWorker] Pre-cache warning:', url, err))
      ));
    })
  );
  self.skipWaiting();
});

// 2. Activate Event: Clean up old cache versions & claim clients immediately
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (cache !== CACHE_NAME) {
            console.log('[ServiceWorker] Removing old cache version:', cache);
            return caches.delete(cache);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// 3. Fetch Event: Dynamic Caching of All Visited Pages + Offline Fallback
self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Skip non-GET requests, socket connections, or backend API sync endpoints from cache storage
  if (req.method !== 'GET' || req.url.includes('/api/') || req.url.includes('/sync/')) {
    return;
  }

  event.respondWith(
    fetch(req)
      .then((networkResponse) => {
        // Cache valid HTTP responses dynamically for offline access
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(req, responseToCache);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        // Network failed -> Serve from Service Worker Cache
        // Aset statis memakai ?v=... dan font ikon memakai ?hash: cocokkan tanpa query string
        return caches.match(req, { ignoreSearch: req.url.includes('/static/') }).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }

          // If it's a page navigation and not in cache, serve the offline.html page or root
          const isHTMLPage = req.mode === 'navigate' || 
                             (req.headers.get('accept') && req.headers.get('accept').includes('text/html'));
          if (isHTMLPage && !req.url.match(/\.(css|js|png|jpg|jpeg|svg|woff2?|ttf|eot)$/i)) {
            return caches.match('/work-orders/') || caches.match('/work_orders/') || caches.match('/static/offline.html') || caches.match('/');
          }

          return null;
        });
      })
  );
});
