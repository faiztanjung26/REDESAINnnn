/**
 * CMMS Offline Storage Manager (IndexedDB via Dexie.js)
 */
(function() {
  if (typeof Dexie === 'undefined') {
    console.warn('Dexie library not loaded yet. Make sure Dexie.js script tag is included.');
    return;
  }

  window.cmmsDB = new Dexie('CMMS_Offline_DB');

  // Define IndexedDB Schema
  window.cmmsDB.version(1).stores({
    workOrders: 'id, wo_number, status, site_id, assigned_to_id, priority',
    procedures: 'id, work_order_id, is_completed, status, min_photos, synced',
    checklists: 'id, work_order_id, parameter, value, synced',
    mediaOutbox: '++id, proc_id, work_order_id, file_blob, file_name, timestamp, synced'
  });

  console.log('[OfflineDB] IndexedDB initialized successfully.');
})();
