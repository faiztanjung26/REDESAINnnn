import 'dart:convert';
import 'package:cross_file/cross_file.dart';
import 'package:http/http.dart' as http;
import 'package:sqflite/sqflite.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../constants/api_constants.dart';
import '../network/api_service.dart';
import '../network/network_info.dart';
import '../database/database_helper.dart';
import '../../data/models/work_order_model.dart';
import '../../data/models/procedure_model.dart';
import '../../data/models/checklist_model.dart';
import '../../data/models/part_model.dart';

class SyncResult {
  final bool success;
  final String message;
  final int downloadedWorkOrders;
  final int uploadedItems;

  SyncResult({
    required this.success,
    required this.message,
    this.downloadedWorkOrders = 0,
    this.uploadedItems = 0,
  });
}

class SyncService {
  static final SyncService instance = SyncService._init();
  SyncService._init();

  final ApiService _api = ApiService.instance;
  final DatabaseHelper _db = DatabaseHelper.instance;
  final NetworkInfo _network = NetworkInfo.instance;

  bool _isSyncing = false;
  bool get isSyncing => _isSyncing;

  Future<String?> getLastSyncTime() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('last_sync_time');
  }

  Future<SyncResult> performFullSync() async {
    if (_isSyncing) {
      return SyncResult(success: false, message: 'Sinkronisasi sedang berlangsung.');
    }

    _isSyncing = true;
    try {
      final isOnline = await _network.checkConnection();
      if (!isOnline) {
        return SyncResult(
          success: false,
          message: 'Gagal terhubung ke jaringan. Pastikan koneksi internet atau WiFi aktif.',
        );
      }

      // 1. Upload outbox queue first
      final uploadCount = await uploadOutboxQueue();

      // 2. Download all assigned WOs and bundle
      final downloadCount = await downloadOfflineBundle();

      // 3. Record last sync timestamp
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('last_sync_time', DateTime.now().toIso8601String());

      return SyncResult(
        success: true,
        message: 'Sinkronisasi berhasil! $uploadCount perubahan terkirim, $downloadCount WO terunduh.',
        downloadedWorkOrders: downloadCount,
        uploadedItems: uploadCount,
      );
    } catch (e) {
      return SyncResult(
        success: false,
        message: 'Gagal melakukan sinkronisasi: $e',
      );
    } finally {
      _isSyncing = false;
    }
  }

  Future<int> downloadOfflineBundle() async {
    final response = await _api.get(ApiConstants.syncDownload);
    if (response['status'] != 'success') {
      throw ApiException(response['message'] ?? 'Gagal mengunduh data offline.');
    }

    final db = await _db.database;
    final batch = db.batch();

    // 1. Clear old synced data (keeping un-synced local changes)
    await db.delete('work_orders', where: 'updated_locally = 0');
    await db.delete('procedures', where: 'updated_locally = 0');
    await db.delete('checklists', where: 'updated_locally = 0');
    await db.delete('parts_used', where: 'updated_locally = 0');

    // 2. Insert Work Orders
    final wosList = (response['work_orders'] as List? ?? []);
    for (var w in wosList) {
      final wo = WorkOrderModel.fromJson(w as Map<String, dynamic>);
      batch.insert('work_orders', wo.toDbMap(), conflictAlgorithm: ConflictAlgorithm.replace);
    }

    // 3. Insert Procedures
    final procsList = (response['procedures'] as List? ?? []);
    for (var p in procsList) {
      final proc = ProcedureModel.fromJson(p as Map<String, dynamic>);
      batch.insert('procedures', proc.toDbMap(), conflictAlgorithm: ConflictAlgorithm.replace);
    }

    // 4. Insert Checklists
    final chksList = (response['checklists'] as List? ?? []);
    for (var c in chksList) {
      final chk = ChecklistModel.fromJson(c as Map<String, dynamic>);
      batch.insert('checklists', chk.toDbMap(), conflictAlgorithm: ConflictAlgorithm.replace);
    }

    // 5. Insert Used Parts
    final partsUsedList = (response['parts_used'] as List? ?? []);
    for (var pu in partsUsedList) {
      final part = UsedPartModel.fromJson(pu as Map<String, dynamic>, pu['work_order_id']);
      batch.insert('parts_used', part.toDbMap(), conflictAlgorithm: ConflictAlgorithm.replace);
    }

    // 6. Insert Parts Catalog
    final catalogList = (response['parts_catalog'] as List? ?? []);
    for (var cat in catalogList) {
      final p = PartModel.fromJson(cat as Map<String, dynamic>);
      batch.insert('parts_catalog', p.toDbMap(), conflictAlgorithm: ConflictAlgorithm.replace);
    }

    await batch.commit(noResult: true);
    return wosList.length;
  }

  Future<int> uploadOutboxQueue() async {
    final pendingItems = await _db.getPendingSyncItems();
    if (pendingItems.isEmpty) return 0;

    List<Map<String, dynamic>> statusChanges = [];
    List<Map<String, dynamic>> procedures = [];
    List<Map<String, dynamic>> checklists = [];
    List<Map<String, dynamic>> logs = [];
    List<Map<String, dynamic>> parts = [];
    List<Map<String, dynamic>> signatures = [];
    List<Map<String, dynamic>> deletedPhotos = [];
    List<http.MultipartFile> multipartFiles = [];

    List<int> processedItemIds = [];

    for (var item in pendingItems) {
      final id = item['id'] as int;
      final type = item['action_type'] as String;
      final woId = item['work_order_id'] as int;
      final payloadStr = item['payload'] as String;
      final dynamic parsed = jsonDecode(payloadStr);

      processedItemIds.add(id);

      switch (type) {
        case 'status_change':
          statusChanges.add({
            'work_order_id': woId,
            'action': parsed['action'],
            'reason': parsed['reason'],
          });
          break;

        case 'procedure_update':
          procedures.add({
            'id': parsed['id'],
            'is_completed': parsed['is_completed'],
            'status': parsed['status'],
            'notes': parsed['notes'],
          });

          // Check if file paths exist to upload
          final filesStr = item['file_paths'] as String?;
          if (filesStr != null && filesStr.isNotEmpty) {
            final paths = filesStr.split('|');
            for (int i = 0; i < paths.length; i++) {
              try {
                final xFile = XFile(paths[i]);
                final bytes = await xFile.readAsBytes();
                if (bytes.isNotEmpty) {
                  final mf = http.MultipartFile.fromBytes(
                    'file_${parsed['id']}_$i',
                    bytes,
                    filename: xFile.name.isNotEmpty ? xFile.name : 'photo_$i.jpg',
                  );
                  multipartFiles.add(mf);
                }
              } catch (_) {}
            }
          }
          break;

        case 'checklist_update':
          if (parsed['items'] is List) {
            for (var chk in (parsed['items'] as List)) {
              checklists.add(chk as Map<String, dynamic>);
            }
          }
          break;

        case 'add_part':
          parts.add({
            'work_order_id': woId,
            'part_id': parsed['part_id'],
            'quantity': parsed['quantity'],
          });
          break;

        case 'add_log':
          logs.add({
            'work_order_id': woId,
            'log_text': parsed['log_text'],
          });
          break;

        case 'save_signature':
          signatures.add({
            'work_order_id': woId,
            'customer_name': parsed['customer_name'],
            'customer_title': parsed['customer_title'],
            'customer_signature': parsed['customer_signature'],
            'technician_signature': parsed['technician_signature'],
          });
          break;

        case 'delete_procedure_photo':
          deletedPhotos.add({
            'procedure_id': parsed['procedure_id'],
            'photo_path': parsed['photo_path'],
          });
          break;
      }
    }

    final batchPayload = {
      'status_changes': statusChanges,
      'procedures': procedures,
      'checklists': checklists,
      'logs': logs,
      'parts': parts,
      'signatures': signatures,
      'deleted_photos': deletedPhotos,
    };

    dynamic uploadRes;
    if (multipartFiles.isNotEmpty) {
      uploadRes = await _api.postMultipart(
        ApiConstants.syncUpload,
        fields: {'payload': jsonEncode(batchPayload)},
        files: multipartFiles,
      );
    } else {
      uploadRes = await _api.post(
        ApiConstants.syncUpload,
        body: batchPayload,
      );
    }

    if (uploadRes['status'] == 'success') {
      // Remove all processed items from local outbox queue
      final db = await _db.database;
      final batch = db.batch();
      for (var id in processedItemIds) {
        batch.delete('sync_outbox', where: 'id = ?', whereArgs: [id]);
      }
      // Reset updated_locally flags
      batch.update('work_orders', {'updated_locally': 0});
      batch.update('procedures', {'updated_locally': 0});
      batch.update('checklists', {'updated_locally': 0});
      await batch.commit(noResult: true);

      return processedItemIds.length;
    } else {
      throw ApiException(uploadRes['message'] ?? 'Gagal mengunggah data outbox.');
    }
  }
}
