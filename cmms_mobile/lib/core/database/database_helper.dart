import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi_web/sqflite_ffi_web.dart';
import 'package:path/path.dart' as p;

class DatabaseHelper {
  static final DatabaseHelper instance = DatabaseHelper._init();
  static Database? _database;

  DatabaseHelper._init();

  Future<Database> get database async {
    if (_database != null) return _database!;
    _database = await _initDB('cmms_offline.db');
    return _database!;
  }

  Future<Database> _initDB(String filePath) async {
    if (kIsWeb) {
      final factory = databaseFactoryFfiWeb;
      return await factory.openDatabase(
        filePath,
        options: OpenDatabaseOptions(
          version: 1,
          onCreate: _createDB,
        ),
      );
    }

    final dbPath = await getDatabasesPath();
    final path = p.join(dbPath, filePath);

    return await openDatabase(
      path,
      version: 1,
      onCreate: _createDB,
    );
  }

  Future<void> _createDB(Database db, int version) async {
    // 1. Work Orders Table
    await db.execute('''
      CREATE TABLE work_orders (
        id INTEGER PRIMARY KEY,
        code TEXT NOT NULL,
        description TEXT,
        priority TEXT,
        status TEXT,
        status_color TEXT,
        maintenance_type TEXT,
        project_code TEXT,
        work_instructions TEXT,
        delay_reason TEXT,
        asset_id INTEGER,
        asset_name TEXT,
        asset_code TEXT,
        asset_location TEXT,
        asset_site TEXT,
        team TEXT,
        suggested_start_date TEXT,
        suggested_completion_date TEXT,
        start_date TEXT,
        end_date TEXT,
        is_overdue INTEGER DEFAULT 0,
        customer_name TEXT,
        customer_title TEXT,
        customer_signature TEXT,
        technician_signature TEXT,
        updated_locally INTEGER DEFAULT 0
      )
    ''');

    // 2. Procedures Table
    await db.execute('''
      CREATE TABLE procedures (
        id INTEGER PRIMARY KEY,
        work_order_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        requires_attachment INTEGER DEFAULT 0,
        min_photos INTEGER DEFAULT 0,
        total_photos INTEGER DEFAULT 0,
        estimated_minutes INTEGER DEFAULT 0,
        is_completed INTEGER DEFAULT 0,
        status TEXT,
        notes TEXT,
        attachment_path TEXT,
        local_photo_paths TEXT,
        updated_locally INTEGER DEFAULT 0,
        FOREIGN KEY (work_order_id) REFERENCES work_orders (id) ON DELETE CASCADE
      )
    ''');

    // 3. Checklists Table
    await db.execute('''
      CREATE TABLE checklists (
        id INTEGER PRIMARY KEY,
        work_order_id INTEGER NOT NULL,
        parameter TEXT NOT NULL,
        standard TEXT,
        value TEXT,
        updated_locally INTEGER DEFAULT 0,
        FOREIGN KEY (work_order_id) REFERENCES work_orders (id) ON DELETE CASCADE
      )
    ''');

    // 4. Parts Used Table
    await db.execute('''
      CREATE TABLE parts_used (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server_id INTEGER,
        work_order_id INTEGER NOT NULL,
        part_id INTEGER,
        part_name TEXT,
        part_code TEXT,
        unit TEXT,
        quantity_used REAL DEFAULT 1.0,
        date_added TEXT,
        updated_locally INTEGER DEFAULT 0
      )
    ''');

    // 5. Work Logs Table
    await db.execute('''
      CREATE TABLE work_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server_id INTEGER,
        work_order_id INTEGER NOT NULL,
        user_name TEXT,
        log_text TEXT NOT NULL,
        created_at TEXT,
        updated_locally INTEGER DEFAULT 0
      )
    ''');

    // 6. Parts Catalog Table
    await db.execute('''
      CREATE TABLE parts_catalog (
        id INTEGER PRIMARY KEY,
        code TEXT,
        name TEXT,
        unit TEXT,
        price REAL
      )
    ''');

    // 7. Sync Outbox Queue Table
    await db.execute('''
      CREATE TABLE sync_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_type TEXT NOT NULL,
        work_order_id INTEGER NOT NULL,
        payload TEXT NOT NULL,
        file_paths TEXT,
        created_at TEXT NOT NULL,
        retry_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending'
      )
    ''');

    // 8. User Profile Cache Table
    await db.execute('''
      CREATE TABLE user_profile (
        id INTEGER PRIMARY KEY,
        nrp TEXT,
        name TEXT,
        role TEXT,
        phone_number TEXT,
        site_name TEXT,
        team_name TEXT,
        token TEXT,
        last_sync TEXT
      )
    ''');
  }

  // --- Outbox Queue Operations ---
  Future<int> enqueueSyncItem({
    required String actionType,
    required int workOrderId,
    required String payload,
    String? filePaths,
  }) async {
    final db = await instance.database;
    return await db.insert('sync_outbox', {
      'action_type': actionType,
      'work_order_id': workOrderId,
      'payload': payload,
      'file_paths': filePaths,
      'created_at': DateTime.now().toIso8601String(),
      'retry_count': 0,
      'status': 'pending',
    });
  }

  Future<List<Map<String, dynamic>>> getPendingSyncItems() async {
    final db = await instance.database;
    return await db.query(
      'sync_outbox',
      where: 'status = ?',
      whereArgs: ['pending'],
      orderBy: 'created_at ASC',
    );
  }

  Future<int> getPendingSyncCount() async {
    final db = await instance.database;
    final result = await db.rawQuery("SELECT COUNT(*) as count FROM sync_outbox WHERE status = 'pending'");
    return Sqflite.firstIntValue(result) ?? 0;
  }

  Future<void> removeSyncItem(int id) async {
    final db = await instance.database;
    await db.delete('sync_outbox', where: 'id = ?', whereArgs: [id]);
  }

  Future<void> clearSyncedItems() async {
    final db = await instance.database;
    await db.delete('sync_outbox', where: "status = 'synced'");
  }

  Future<void> clearAllCache() async {
    final db = await instance.database;
    await db.delete('work_orders');
    await db.delete('procedures');
    await db.delete('checklists');
    await db.delete('parts_used');
    await db.delete('work_logs');
    await db.delete('parts_catalog');
  }

  Future<void> close() async {
    final db = await instance.database;
    db.close();
  }
}
