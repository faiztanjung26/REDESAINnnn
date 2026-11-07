class SyncQueueItem {
  final int id;
  final String actionType;
  final int workOrderId;
  final String payload;
  final String? filePaths;
  final String createdAt;
  final int retryCount;
  final String status;

  SyncQueueItem({
    required this.id,
    required this.actionType,
    required this.workOrderId,
    required this.payload,
    this.filePaths,
    required this.createdAt,
    this.retryCount = 0,
    this.status = 'pending',
  });

  factory SyncQueueItem.fromDb(Map<String, dynamic> map) {
    return SyncQueueItem(
      id: map['id'],
      actionType: map['action_type'],
      workOrderId: map['work_order_id'],
      payload: map['payload'],
      filePaths: map['file_paths'],
      createdAt: map['created_at'],
      retryCount: map['retry_count'] ?? 0,
      status: map['status'] ?? 'pending',
    );
  }

  String get actionTitle {
    switch (actionType) {
      case 'status_change':
        return 'Perubahan Status WO';
      case 'procedure_update':
        return 'Pembaruan Prosedur';
      case 'checklist_update':
        return 'Pembaruan Parameter Checklist';
      case 'add_part':
        return 'Penggunaan Suku Cadang';
      case 'add_log':
        return 'Catatan / Log Pekerjaan';
      case 'save_signature':
        return 'Tanda Tangan Digital';
      default:
        return 'Sinkronisasi Data';
    }
  }
}
