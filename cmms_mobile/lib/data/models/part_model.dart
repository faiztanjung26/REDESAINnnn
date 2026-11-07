class PartModel {
  final int id;
  final String code;
  final String name;
  final String unit;
  final double price;

  PartModel({
    required this.id,
    required this.code,
    required this.name,
    this.unit = 'Pcs',
    this.price = 0.0,
  });

  factory PartModel.fromJson(Map<String, dynamic> json) {
    return PartModel(
      id: json['id'] is int ? json['id'] : int.tryParse(json['id'].toString()) ?? 0,
      code: json['code'] ?? '',
      name: json['name'] ?? '',
      unit: json['unit'] ?? 'Pcs',
      price: (json['price'] is num) ? (json['price'] as num).toDouble() : 0.0,
    );
  }

  factory PartModel.fromDb(Map<String, dynamic> map) {
    return PartModel(
      id: map['id'],
      code: map['code'] ?? '',
      name: map['name'] ?? '',
      unit: map['unit'] ?? 'Pcs',
      price: (map['price'] is num) ? (map['price'] as num).toDouble() : 0.0,
    );
  }

  Map<String, dynamic> toDbMap() {
    return {
      'id': id,
      'code': code,
      'name': name,
      'unit': unit,
      'price': price,
    };
  }
}

class UsedPartModel {
  final int? localId;
  final int? serverId;
  final int workOrderId;
  final int partId;
  final String partName;
  final String partCode;
  final String unit;
  final double quantityUsed;
  final String? dateAdded;
  final bool updatedLocally;

  UsedPartModel({
    this.localId,
    this.serverId,
    required this.workOrderId,
    required this.partId,
    required this.partName,
    required this.partCode,
    this.unit = 'Pcs',
    this.quantityUsed = 1.0,
    this.dateAdded,
    this.updatedLocally = false,
  });

  factory UsedPartModel.fromJson(Map<String, dynamic> json, int woId) {
    return UsedPartModel(
      serverId: json['id'] is int ? json['id'] : int.tryParse(json['id']?.toString() ?? ''),
      workOrderId: woId,
      partId: json['part_id'] is int ? json['part_id'] : int.tryParse(json['part_id']?.toString() ?? '') ?? 0,
      partName: json['part_name'] ?? '-',
      partCode: json['part_code'] ?? '-',
      unit: json['unit'] ?? 'Pcs',
      quantityUsed: (json['quantity_used'] is num) ? (json['quantity_used'] as num).toDouble() : 1.0,
      dateAdded: json['date_added'],
      updatedLocally: false,
    );
  }

  factory UsedPartModel.fromDb(Map<String, dynamic> map) {
    return UsedPartModel(
      localId: map['id'],
      serverId: map['server_id'],
      workOrderId: map['work_order_id'],
      partId: map['part_id'],
      partName: map['part_name'] ?? '-',
      partCode: map['part_code'] ?? '-',
      unit: map['unit'] ?? 'Pcs',
      quantityUsed: (map['quantity_used'] is num) ? (map['quantity_used'] as num).toDouble() : 1.0,
      dateAdded: map['date_added'],
      updatedLocally: map['updated_locally'] == 1,
    );
  }

  Map<String, dynamic> toDbMap() {
    return {
      if (localId != null) 'id': localId,
      'server_id': serverId,
      'work_order_id': workOrderId,
      'part_id': partId,
      'part_name': partName,
      'part_code': partCode,
      'unit': unit,
      'quantity_used': quantityUsed,
      'date_added': dateAdded ?? DateTime.now().toIso8601String(),
      'updated_locally': updatedLocally ? 1 : 0,
    };
  }
}
