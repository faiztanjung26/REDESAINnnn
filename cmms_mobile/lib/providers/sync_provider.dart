import 'package:flutter/material.dart';
import '../core/database/database_helper.dart';
import '../core/network/network_info.dart';
import '../core/sync/sync_service.dart';

class SyncProvider extends ChangeNotifier {
  final SyncService _syncService = SyncService.instance;
  final DatabaseHelper _db = DatabaseHelper.instance;
  final NetworkInfo _network = NetworkInfo.instance;

  bool _isOnline = true;
  bool _isSyncing = false;
  int _pendingCount = 0;
  String? _lastSyncTime;
  String? _syncMessage;

  bool get isOnline => _isOnline;
  bool get isSyncing => _isSyncing;
  int get pendingCount => _pendingCount;
  String? get lastSyncTime => _lastSyncTime;
  String? get syncMessage => _syncMessage;

  Future<void> init() async {
    _isOnline = await _network.checkConnection();
    _lastSyncTime = await _syncService.getLastSyncTime();
    await refreshPendingCount();

    // Listen to network changes
    _network.onConnectionChange.listen((online) async {
      final wasOffline = !_isOnline;
      _isOnline = online;
      notifyListeners();

      // Auto-sync when reconnecting if there are pending outbox items
      if (wasOffline && online && _pendingCount > 0) {
        triggerSync(isAutomatic: true);
      }
    });
  }

  Future<void> refreshPendingCount() async {
    _pendingCount = await _db.getPendingSyncCount();
    notifyListeners();
  }

  Future<bool> triggerSync({bool isAutomatic = false}) async {
    if (_isSyncing) return false;

    _isSyncing = true;
    _syncMessage = isAutomatic ? 'Menyinkronkan otomatis di latar belakang...' : 'Memulai sinkronisasi data...';
    notifyListeners();

    try {
      final result = await _syncService.performFullSync();
      _syncMessage = result.message;
      _lastSyncTime = await _syncService.getLastSyncTime();
      await refreshPendingCount();
      _isSyncing = false;
      notifyListeners();
      return result.success;
    } catch (e) {
      _syncMessage = 'Sinkronisasi gagal: $e';
      _isSyncing = false;
      notifyListeners();
      return false;
    }
  }

  Future<void> clearSyncedData() async {
    await _db.clearAllCache();
    await refreshPendingCount();
  }
}
