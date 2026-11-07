class ChecklistModel {
  final int id;
  final int workOrderId;
  final String parameter;
  final String standard;
  String value;
  bool updatedLocally;

  ChecklistModel({
    required this.id,
    required this.workOrderId,
    required this.parameter,
    required this.standard,
    required this.value,
    this.updatedLocally = false,
  });

  factory ChecklistModel.fromJson(Map<String, dynamic> json) {
    return ChecklistModel(
      id: json['id'] is int ? json['id'] : int.tryParse(json['id'].toString()) ?? 0,
      workOrderId: json['work_order_id'] is int ? json['work_order_id'] : int.tryParse(json['work_order_id']?.toString() ?? '') ?? 0,
      parameter: json['parameter'] ?? '',
      standard: json['standard'] ?? '',
      value: json['value'] ?? '',
      updatedLocally: json['updated_locally'] == 1,
    );
  }

  factory ChecklistModel.fromDb(Map<String, dynamic> map) {
    return ChecklistModel(
      id: map['id'],
      workOrderId: map['work_order_id'],
      parameter: map['parameter'],
      standard: map['standard'] ?? '',
      value: map['value'] ?? '',
      updatedLocally: map['updated_locally'] == 1,
    );
  }

  Map<String, dynamic> toDbMap() {
    return {
      'id': id,
      'work_order_id': workOrderId,
      'parameter': parameter,
      'standard': standard,
      'value': value,
      'updated_locally': updatedLocally ? 1 : 0,
    };
  }

  bool get isFilled => value.trim().isNotEmpty;
}
