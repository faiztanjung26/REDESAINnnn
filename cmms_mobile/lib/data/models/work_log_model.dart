class WorkLogModel {
  final int? localId;
  final int? serverId;
  final int workOrderId;
  final String userName;
  final String logText;
  final String createdAt;
  final bool updatedLocally;

  WorkLogModel({
    this.localId,
    this.serverId,
    required this.workOrderId,
    required this.userName,
    required this.logText,
    required this.createdAt,
    this.updatedLocally = false,
  });

  factory WorkLogModel.fromJson(Map<String, dynamic> json, int woId) {
    return WorkLogModel(
      serverId: json['id'] is int ? json['id'] : int.tryParse(json['id']?.toString() ?? ''),
      workOrderId: woId,
      userName: json['user_name'] ?? 'Teknisi',
      logText: json['log_text'] ?? '',
      createdAt: json['created_at'] ?? '',
      updatedLocally: false,
    );
  }

  factory WorkLogModel.fromDb(Map<String, dynamic> map) {
    return WorkLogModel(
      localId: map['id'],
      serverId: map['server_id'],
      workOrderId: map['work_order_id'],
      userName: map['user_name'] ?? 'Teknisi',
      logText: map['log_text'] ?? '',
      createdAt: map['created_at'] ?? '',
      updatedLocally: map['updated_locally'] == 1,
    );
  }

  Map<String, dynamic> toDbMap() {
    return {
      if (localId != null) 'id': localId,
      'server_id': serverId,
      'work_order_id': workOrderId,
      'user_name': userName,
      'log_text': logText,
      'created_at': createdAt,
      'updated_locally': updatedLocally ? 1 : 0,
    };
  }
}
