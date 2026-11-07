import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:sqflite/sqflite.dart';
import '../../core/constants/api_constants.dart';
import '../../core/network/api_service.dart';
import '../../core/database/database_helper.dart';
import '../models/work_order_model.dart';
import '../models/procedure_model.dart';
import '../models/checklist_model.dart';
import '../models/part_model.dart';
import '../models/work_log_model.dart';

class WorkOrderRepository {
  final ApiService _api = ApiService.instance;
  final DatabaseHelper _db = DatabaseHelper.instance;

  // ==========================================
  // READ OPERATIONS (OFFLINE-FIRST)
  // ==========================================

  Future<List<WorkOrderModel>> getWorkOrders({
    String status = 'all',
    String? priority,
    String? search,
    bool forceRefresh = false,
  }) async {
    // 1. If forceRefresh, attempt online fetch first
    if (forceRefresh) {
      try {
        await refreshWorkOrdersFromApi();
      } catch (_) {
        // Network error, proceed with local db
      }
    }

    // 2. Query from local SQLite database
    final db = await _db.database;
    String whereClause = '1=1';
    List<dynamic> whereArgs = [];

    if (status != 'all') {
      if (status == 'assigned') {
        whereClause += " AND status IN ('Assigned', 'Confirmed')";
      } else if (status == 'in_progress') {
        whereClause += " AND status = 'In Progress'";
      } else if (status == 'hold') {
        whereClause += " AND status = 'Hold'";
      } else if (status == 'solved') {
        whereClause += " AND status = 'Solved'";
      } else if (status == 'completed') {
        whereClause += " AND status IN ('Completed', 'Closed')";
      }
    }

    if (priority != null && priority.isNotEmpty && priority != 'Semua') {
      whereClause += " AND priority = ?";
      whereArgs.add(priority);
    }

    if (search != null && search.trim().isNotEmpty) {
      final s = '%${search.trim()}%';
      whereClause += " AND (code LIKE ? OR description LIKE ? OR asset_name LIKE ?)";
      whereArgs.addAll([s, s, s]);
    }

    final List<Map<String, dynamic>> maps = await db.query(
      'work_orders',
      where: whereClause,
      whereArgs: whereArgs,
      orderBy: 'CASE priority WHEN "Highest" THEN 1 WHEN "High" THEN 2 WHEN "Medium" THEN 3 ELSE 4 END, suggested_completion_date ASC',
    );

    List<WorkOrderModel> results = [];
    for (var m in maps) {
      final wo = WorkOrderModel.fromDb(m);

      // Load procedure count and completion from local DB
      final procs = await db.query(
        'procedures',
        where: 'work_order_id = ?',
        whereArgs: [wo.id],
      );
      wo.procedures = procs.map((p) => ProcedureModel.fromDb(p)).toList();

      results.add(wo);
    }

    // If local was empty and not forced, try fetch from API once
    if (results.isEmpty && !forceRefresh) {
      try {
        final onlineWos = await refreshWorkOrdersFromApi();
        return onlineWos;
      } catch (_) {}
    }

    return results;
  }

  Future<List<WorkOrderModel>> refreshWorkOrdersFromApi() async {
    final response = await _api.get(ApiConstants.workOrders, queryParams: {'limit': 100});
    if (response['status'] == 'success') {
      final data = response['data'] as List;
      final wos = data.map((json) => WorkOrderModel.fromJson(json)).toList();

      // Upsert into SQLite
      final db = await _db.database;
      final batch = db.batch();

      for (var wo in wos) {
        batch.insert(
          'work_orders',
          wo.toDbMap(),
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      }
      await batch.commit(noResult: true);
      return wos;
    }
    return [];
  }

  Future<WorkOrderModel> getWorkOrderDetail(int id) async {
    final db = await _db.database;

    // First attempt to fetch from API when possible to stay in sync
    try {
      final response = await _api.get(ApiConstants.workOrderDetail(id));
      if (response['status'] == 'success') {
        final wo = WorkOrderModel.fromJson(response['data']);
        await _saveWorkOrderDetailToLocal(wo);
        return wo;
      }
    } catch (_) {
      // Offline fallback: load from local DB
    }

    // Load from local DB
    final woMaps = await db.query('work_orders', where: 'id = ?', whereArgs: [id]);
    if (woMaps.isEmpty) {
      throw Exception('Work Order tidak ditemukan di penyimpanan offline.');
    }

    final wo = WorkOrderModel.fromDb(woMaps.first);

    // Load procedures
    final procMaps = await db.query('procedures', where: 'work_order_id = ?', whereArgs: [id]);
    wo.procedures = procMaps.map((p) => ProcedureModel.fromDb(p)).toList();

    // Load checklists
    final chkMaps = await db.query('checklists', where: 'work_order_id = ?', whereArgs: [id]);
    wo.checklists = chkMaps.map((c) => ChecklistModel.fromDb(c)).toList();

    // Load parts used
    final partMaps = await db.query('parts_used', where: 'work_order_id = ?', whereArgs: [id]);
    wo.partsUsed = partMaps.map((p) => UsedPartModel.fromDb(p)).toList();

    // Load logs
    final logMaps = await db.query('work_logs', where: 'work_order_id = ?', whereArgs: [id], orderBy: 'created_at DESC');
    wo.logs = logMaps.map((l) => WorkLogModel.fromDb(l)).toList();

    // Set allowed actions according to status
    if (wo.status == 'Draft' || wo.status == 'Assigned' || wo.status == 'Confirmed') {
      wo.allowedActions = ['start'];
    } else if (wo.status == 'In Progress') {
      wo.allowedActions = ['hold', 'solve'];
    } else if (wo.status == 'Hold') {
      wo.allowedActions = ['resume'];
    }

    return wo;
  }

  Future<void> _saveWorkOrderDetailToLocal(WorkOrderModel wo) async {
    final db = await _db.database;
    final batch = db.batch();

    batch.insert('work_orders', wo.toDbMap(), conflictAlgorithm: ConflictAlgorithm.replace);

    for (var proc in wo.procedures) {
      batch.insert('procedures', proc.toDbMap(), conflictAlgorithm: ConflictAlgorithm.replace);
    }

    for (var chk in wo.checklists) {
      batch.insert('checklists', chk.toDbMap(), conflictAlgorithm: ConflictAlgorithm.replace);
    }

    for (var part in wo.partsUsed) {
      batch.insert('parts_used', part.toDbMap(), conflictAlgorithm: ConflictAlgorithm.replace);
    }

    for (var log in wo.logs) {
      batch.insert('work_logs', log.toDbMap(), conflictAlgorithm: ConflictAlgorithm.replace);
    }

    await batch.commit(noResult: true);
  }

  // ==========================================
  // WRITE OPERATIONS (OFFLINE-FIRST + OUTBOX)
  // ==========================================

  Future<void> updateStatus(int id, String action, {String? reason}) async {
    final db = await _db.database;

    // 1. Calculate new status locally
    String newStatus = 'In Progress';
    String newColor = '#2563eb';
    String? startDate;
    String? endDate;

    if (action == 'start') {
      newStatus = 'In Progress';
      newColor = '#2563eb';
      startDate = DateTime.now().toIso8601String();
    } else if (action == 'hold') {
      newStatus = 'Hold';
      newColor = '#f59e0b';
    } else if (action == 'resume') {
      newStatus = 'In Progress';
      newColor = '#2563eb';
    } else if (action == 'solve') {
      newStatus = 'Solved';
      newColor = '#8b5cf6';
      endDate = DateTime.now().toIso8601String();
    }

    // 2. Update local work order table
    await db.update(
      'work_orders',
      {
        'status': newStatus,
        'status_color': newColor,
        if (startDate != null) 'start_date': startDate,
        if (endDate != null) 'end_date': endDate,
        if (reason != null) 'delay_reason': reason,
        'updated_locally': 1,
      },
      where: 'id = ?',
      whereArgs: [id],
    );

    // 3. Add to sync outbox queue
    await _db.enqueueSyncItem(
      actionType: 'status_change',
      workOrderId: id,
      payload: jsonEncode({'action': action, 'reason': reason}),
    );

    // 4. Try online sync if available
    try {
      await _api.post(
        ApiConstants.updateStatus(id),
        body: {'action': action, 'reason': reason},
      );
    } catch (_) {
      // Offline mode: queued in outbox for background sync
    }
  }

  Future<void> updateProcedure({
    required int workOrderId,
    required int procedureId,
    required bool isCompleted,
    required String notes,
    List<String> newLocalPhotos = const [],
  }) async {
    final db = await _db.database;

    // 1. Update in local SQLite
    final existing = await db.query('procedures', where: 'id = ?', whereArgs: [procedureId]);
    List<String> currentLocals = [];
    if (existing.isNotEmpty && existing.first['local_photo_paths'] != null) {
      currentLocals = (existing.first['local_photo_paths'] as String)
          .split('|')
          .where((s) => s.isNotEmpty)
          .toList();
    }
    currentLocals.addAll(newLocalPhotos);

    await db.update(
      'procedures',
      {
        'is_completed': isCompleted ? 1 : 0,
        'status': isCompleted ? 'Done' : 'Pending',
        'notes': notes,
        'local_photo_paths': currentLocals.join('|'),
        'updated_locally': 1,
      },
      where: 'id = ?',
      whereArgs: [procedureId],
    );

    // 2. Queue in outbox
    await _db.enqueueSyncItem(
      actionType: 'procedure_update',
      workOrderId: workOrderId,
      payload: jsonEncode({
        'id': procedureId,
        'is_completed': isCompleted,
        'status': isCompleted ? 'Done' : 'Pending',
        'notes': notes,
      }),
      filePaths: newLocalPhotos.isNotEmpty ? newLocalPhotos.join('|') : null,
    );

    // 3. Try immediate upload if online
    try {
      await _api.post(
        ApiConstants.updateProcedure(workOrderId, procedureId),
        body: {
          'is_completed': isCompleted,
          'notes': notes,
        },
      );
    } catch (_) {}
  }

  Future<void> deleteProcedurePhoto({
    required int workOrderId,
    required int procedureId,
    String? localPath,
    String? photoUrlOrPath,
  }) async {
    final db = await _db.database;

    final existing = await db.query('procedures', where: 'id = ?', whereArgs: [procedureId]);
    if (existing.isEmpty) return;

    final proc = ProcedureModel.fromDb(existing.first);

    // 1. Remove local photo
    if (localPath != null && localPath.isNotEmpty) {
      proc.localPhotoPaths.removeWhere((p) => p == localPath);
      if (!kIsWeb) {
        try {
          final f = File(localPath);
          if (f.existsSync()) {
            f.deleteSync();
          }
        } catch (_) {}
      }

      // Clean from pending sync items if queued
      final pendingItems = await _db.getPendingSyncItems();
      for (var item in pendingItems) {
        if (item['action_type'] == 'procedure_update' && item['work_order_id'] == workOrderId) {
          final filePaths = (item['file_paths'] as String?)?.split('|') ?? [];
          if (filePaths.contains(localPath)) {
            filePaths.remove(localPath);
            await db.update(
              'sync_outbox',
              {'file_paths': filePaths.isNotEmpty ? filePaths.join('|') : null},
              where: 'id = ?',
              whereArgs: [item['id']],
            );
          }
        }
      }
    }

    // 2. Remove server photo
    if (photoUrlOrPath != null && photoUrlOrPath.isNotEmpty) {
      final clean = photoUrlOrPath
          .replaceAll('/static/', '')
          .replaceAll(RegExp(r'^https?://[^/]+/static/'), '')
          .trim();
      proc.photos.removeWhere((p) => p == photoUrlOrPath || p == clean || p.endsWith(clean));
      final curAttachments = proc.attachmentPath.split('|').where((s) => s.isNotEmpty).toList();
      curAttachments.removeWhere((p) => p == clean || photoUrlOrPath.endsWith(p));
      proc.attachmentPath = curAttachments.join('|');

      // Call online API or queue outbox
      try {
        await _api.post(
          ApiConstants.deleteProcedurePhoto(workOrderId, procedureId),
          body: {'photo_path': clean},
        );
      } catch (_) {
        await _db.enqueueSyncItem(
          actionType: 'delete_procedure_photo',
          workOrderId: workOrderId,
          payload: jsonEncode({'procedure_id': procedureId, 'photo_path': clean}),
        );
      }
    }

    // 3. Update completion status if requirement not satisfied anymore
    if (!proc.satisfiesAttachmentRequirement && proc.isCompleted) {
      proc.isCompleted = false;
      proc.status = 'Pending';
    }

    // 4. Save to local SQLite
    await db.update(
      'procedures',
      proc.toDbMap(),
      where: 'id = ?',
      whereArgs: [procedureId],
    );
  }

  Future<void> saveChecklists({
    required int workOrderId,
    required List<Map<String, dynamic>> items,
  }) async {
    final db = await _db.database;
    final batch = db.batch();

    for (var item in items) {
      final chkId = item['id'];
      final val = item['value'];
      batch.update(
        'checklists',
        {'value': val, 'updated_locally': 1},
        where: 'id = ?',
        whereArgs: [chkId],
      );
    }
    await batch.commit(noResult: true);

    // Enqueue
    await _db.enqueueSyncItem(
      actionType: 'checklist_update',
      workOrderId: workOrderId,
      payload: jsonEncode({'items': items}),
    );

    // Online attempt
    try {
      await _api.post(
        ApiConstants.updateChecklists(workOrderId),
        body: {'items': items},
      );
    } catch (_) {}
  }

  Future<void> addUsedPart({
    required int workOrderId,
    required int partId,
    required String partName,
    required String partCode,
    required double quantity,
    required String unit,
  }) async {
    final db = await _db.database;

    await db.insert('parts_used', {
      'work_order_id': workOrderId,
      'part_id': partId,
      'part_name': partName,
      'part_code': partCode,
      'quantity_used': quantity,
      'unit': unit,
      'date_added': DateTime.now().toIso8601String(),
      'updated_locally': 1,
    });

    await _db.enqueueSyncItem(
      actionType: 'add_part',
      workOrderId: workOrderId,
      payload: jsonEncode({
        'part_id': partId,
        'quantity': quantity,
      }),
    );

    try {
      await _api.post(
        ApiConstants.addPart(workOrderId),
        body: {'part_id': partId, 'quantity': quantity},
      );
    } catch (_) {}
  }

  Future<void> addWorkLog({
    required int workOrderId,
    required String text,
    required String userName,
  }) async {
    final db = await _db.database;

    await db.insert('work_logs', {
      'work_order_id': workOrderId,
      'user_name': userName,
      'log_text': text,
      'created_at': DateTime.now().toIso8601String(),
      'updated_locally': 1,
    });

    await _db.enqueueSyncItem(
      actionType: 'add_log',
      workOrderId: workOrderId,
      payload: jsonEncode({'log_text': text}),
    );

    try {
      await _api.post(
        ApiConstants.addLog(workOrderId),
        body: {'log_text': text},
      );
    } catch (_) {}
  }

  Future<void> saveSignatures({
    required int workOrderId,
    String? technicianSignature,
    String? customerSignature,
    String? customerName,
    String? customerTitle,
  }) async {
    final db = await _db.database;

    await db.update(
      'work_orders',
      {
        if (technicianSignature != null) 'technician_signature': technicianSignature,
        if (customerSignature != null) 'customer_signature': customerSignature,
        if (customerName != null) 'customer_name': customerName,
        if (customerTitle != null) 'customer_title': customerTitle,
        'updated_locally': 1,
      },
      where: 'id = ?',
      whereArgs: [workOrderId],
    );

    await _db.enqueueSyncItem(
      actionType: 'save_signature',
      workOrderId: workOrderId,
      payload: jsonEncode({
        'technician_signature': technicianSignature,
        'customer_signature': customerSignature,
        'customer_name': customerName,
        'customer_title': customerTitle,
      }),
    );

    try {
      await _api.post(
        ApiConstants.saveSignature(workOrderId),
        body: {
          'technician_signature': technicianSignature,
          'customer_signature': customerSignature,
          'customer_name': customerName,
          'customer_title': customerTitle,
        },
      );
    } catch (e) {
      // Signature saved locally and queued for sync - user won't lose data
      debugPrint('Signature sync deferred: $e');
    }
  }

  Future<List<PartModel>> searchParts(String query) async {
    final db = await _db.database;
    final results = await db.query(
      'parts_catalog',
      where: 'name LIKE ? OR code LIKE ?',
      whereArgs: ['%$query%', '%$query%'],
      limit: 30,
    );

    if (results.isNotEmpty) {
      return results.map((m) => PartModel.fromDb(m)).toList();
    }

    // Try online search
    try {
      final res = await _api.get(ApiConstants.parts, queryParams: {'q': query});
      if (res['status'] == 'success') {
        final list = (res['data'] as List).map((p) => PartModel.fromJson(p)).toList();
        return list;
      }
    } catch (_) {}

    return [];
  }
}
