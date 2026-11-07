/**
 * CMMS Offline Sync Manager & Page Caching
 * Seamlessly caches regular Work Order pages, CDN libraries, and handles offline form submissions
 */

const CMMSSyncManager = {
  isOnline: navigator.onLine,

  init: function() {
    this.updateOnlineStatus();
    window.addEventListener('online', () => this.handleNetworkChange(true));
    window.addEventListener('offline', () => this.handleNetworkChange(false));
    this.bindRegularPageFormInterceptors();
  },

  updateOnlineStatus: function() {
    this.isOnline = navigator.onLine;
    const badge = document.getElementById('offlineStatusBadge');
    if (badge) {
      if (this.isOnline) {
        badge.className = 'badge bg-success text-white shadow-sm me-2';
        badge.innerHTML = '<i class="bi bi-wifi"></i> Online';
      } else {
        badge.className = 'badge bg-warning text-dark shadow-sm me-2';
        badge.innerHTML = '<i class="bi bi-wifi-off"></i> Mode Offline';
      }
    }
  },

  handleNetworkChange: function(online) {
    this.updateOnlineStatus();
    if (online) {
      this.syncOutboxToServer();
    }
  },

  // 1. Download & Cache Regular Work Order HTML Pages, CDN Assets, and JSON Data for Offline Work
  downloadAssignedWorkOrders: async function() {
    if (!navigator.onLine) {
      alert('Koneksi internet diperlukan untuk mengunduh data offline.');
      return;
    }

    try {
      const btn = document.getElementById('btnDownloadOffline');
      if (btn) btn.disabled = true;

      const res = await fetch('/sync/api/download-assigned-wo');
      if (!res.ok) throw new Error('Gagal mengunduh data dari server.');

      const data = await res.json(); // { work_orders: [], procedures: [], checklists: [] }

      if (!window.cmmsDB) {
        throw new Error('Database lokal IndexedDB belum terinisialisasi.');
      }

      // Store JSON data to IndexedDB
      await window.cmmsDB.workOrders.clear();
      await window.cmmsDB.procedures.clear();
      await window.cmmsDB.checklists.clear();

      await window.cmmsDB.workOrders.bulkPut(data.work_orders || []);
      await window.cmmsDB.procedures.bulkPut(data.procedures || []);
      await window.cmmsDB.checklists.bulkPut(data.checklists || []);

      // Pre-cache all CDN libraries & regular HTML edit pages into Service Worker cache
      if ('caches' in window) {
        const cache = await caches.open('cmms-full-cache-v6');
        const cdnAssets = [
          '/',
          '/dashboard',
          '/work-orders/',
          '/work_orders/',
          'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
          'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css',
          'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
          'https://code.jquery.com/jquery-3.6.0.min.js',
          'https://unpkg.com/dexie@latest/dist/dexie.js'
        ];

        for (let asset of cdnAssets) {
          await cache.add(asset).catch(e => console.warn(`[Cache] CDN Asset warning ${asset}:`, e));
        }

        // Cache each individual Work Order edit page HTML
        for (let wo of (data.work_orders || [])) {
          const pageUrl = `/work-orders/${wo.id}/edit`;
          await cache.add(pageUrl).catch(err => console.warn(`[Cache] Could not pre-cache ${pageUrl}:`, err));
        }
      }

      alert(`Berhasil mengunduh ${data.work_orders.length} Work Order beserta seluruh halaman HTML, CSS, & Ikon! Anda dapat memilih tab & mengerjakan WO secara offline di halaman biasa.`);
    } catch (err) {
      console.error('[Sync] Download error:', err);
      alert('Terjadi kesalahan saat mengunduh data offline: ' + err.message);
    } finally {
      const btn = document.getElementById('btnDownloadOffline');
      if (btn) btn.disabled = false;
    }
  },

  // 2. Intercept Regular Form Submissions on /work-orders/<id>/edit when Offline
  bindRegularPageFormInterceptors: function() {
    document.addEventListener('submit', async (e) => {
      if (navigator.onLine) return; // If online, allow standard Flask form submission

      const form = e.target;
      if (!form || !form.action) return;

      // Intercept Procedure Completion Form
      if (form.action.includes('/procedure/') && form.action.includes('/complete')) {
        e.preventDefault();
        await this.handleOfflineProcedureSubmit(form);
      }
      // Intercept Checklist Parameter Form
      else if (form.action.includes('/checklist_param/') || form.action.includes('/checklist/bulk_save')) {
        e.preventDefault();
        await this.handleOfflineChecklistSubmit(form);
      }
    });
  },

  handleOfflineProcedureSubmit: async function(form) {
    try {
      const actionUrl = form.action;
      const match = actionUrl.match(/\/work-orders\/(\d+)\/procedure\/(\d+)\/complete/);
      if (!match) return;

      const woId = parseInt(match[1]);
      const procId = parseInt(match[2]);

      const fileInput = form.querySelector('input[type="file"]');
      const actionInput = form.querySelector('input[name="action"]');
      const isUncomplete = actionInput && actionInput.value === 'uncomplete';

      if (isUncomplete) {
        await window.cmmsDB.procedures.update(procId, {
          is_completed: false,
          status: 'Pending',
          synced: false
        });
        alert('Tugas ditandai belum selesai (Offline Mode)');
        window.location.reload();
        return;
      }

      // Check if photo files attached
      if (fileInput && fileInput.files && fileInput.files.length > 0) {
        for (let file of fileInput.files) {
          await window.cmmsDB.mediaOutbox.add({
            proc_id: procId,
            work_order_id: woId,
            file_blob: file,
            file_name: file.name,
            timestamp: new Date().toISOString(),
            synced: false
          });
        }
      }

      await window.cmmsDB.procedures.update(procId, {
        is_completed: true,
        status: 'Done',
        synced: false
      });

      alert('Prosedur berhasil diselesaikan offline! Data tersimpan di perangkat.');
      window.location.reload();
    } catch (err) {
      console.error('[OfflineSubmit] Error:', err);
      alert('Gagal menyimpan pekerjaan offline: ' + err.message);
    }
  },

  handleOfflineChecklistSubmit: async function(form) {
    try {
      const formData = new FormData(form);
      const val = formData.get('value');
      const actionUrl = form.action;

      const match = actionUrl.match(/\/checklist_param\/(\d+)\/save/);
      if (match) {
        const chkId = parseInt(match[1]);
        await window.cmmsDB.checklists.update(chkId, {
          value: val,
          synced: false
        });
        alert('Nilai checklist berhasil disimpan offline!');
      }
    } catch (err) {
      console.error('[OfflineChecklist] Error:', err);
    }
  },

  // 3. Sync Offline Outbox Back to Server when Online
  syncOutboxToServer: async function() {
    if (!window.cmmsDB || !navigator.onLine) return;

    try {
      const pendingProcs = await window.cmmsDB.procedures.where('synced').equals(false).toArray();
      const pendingChecklists = await window.cmmsDB.checklists.where('synced').equals(false).toArray();
      const pendingMedia = await window.cmmsDB.mediaOutbox.where('synced').equals(false).toArray();

      if (pendingProcs.length === 0 && pendingChecklists.length === 0 && pendingMedia.length === 0) {
        return;
      }

      console.log('[Sync] Discovered pending offline transactions. Starting sync...');

      const formData = new FormData();
      formData.append('procedures', JSON.stringify(pendingProcs));
      formData.append('checklists', JSON.stringify(pendingChecklists));

      pendingMedia.forEach((media, idx) => {
        formData.append(`file_${media.proc_id}_${idx}`, media.file_blob, media.file_name || `photo_${idx}.jpg`);
      });

      const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
      const headers = {};
      if (csrfToken) headers['X-CSRFToken'] = csrfToken;

      const res = await fetch('/sync/api/upload-offline-batch', {
        method: 'POST',
        headers: headers,
        body: formData
      });

      if (res.ok) {
        await window.cmmsDB.procedures.where('synced').equals(false).modify({ synced: true });
        await window.cmmsDB.checklists.where('synced').equals(false).modify({ synced: true });
        await window.cmmsDB.mediaOutbox.where('synced').equals(false).modify({ synced: true });
        console.log('[Sync] All offline transactions synced successfully!');
      }
    } catch (err) {
      console.error('[Sync] Error uploading offline outbox:', err);
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  CMMSSyncManager.init();
});
