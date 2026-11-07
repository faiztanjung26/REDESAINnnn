class ProcedureModel {
  final int id;
  final int workOrderId;
  final String name;
  final bool requiresAttachment;
  final int minPhotos;
  final int estimatedMinutes;
  bool isCompleted;
  String status;
  String notes;
  String attachmentPath;
  List<String> photos;
  List<String> localPhotoPaths;
  bool updatedLocally;

  ProcedureModel({
    required this.id,
    required this.workOrderId,
    required this.name,
    this.requiresAttachment = false,
    this.minPhotos = 0,
    this.estimatedMinutes = 0,
    this.isCompleted = false,
    this.status = 'Pending',
    this.notes = '',
    this.attachmentPath = '',
    List<String>? photos,
    List<String>? localPhotoPaths,
    this.updatedLocally = false,
  })  : photos = photos ?? [],
        localPhotoPaths = localPhotoPaths ?? [];

  factory ProcedureModel.fromJson(Map<String, dynamic> json) {
    List<String> photoUrls = [];
    if (json['photos'] is List) {
      photoUrls = (json['photos'] as List).map((e) => e.toString()).toList();
    } else if (json['attachment_path'] != null && json['attachment_path'].toString().isNotEmpty) {
      photoUrls = json['attachment_path'].toString().split('|').where((s) => s.isNotEmpty).toList();
    }

    return ProcedureModel(
      id: json['id'] is int ? json['id'] : int.tryParse(json['id'].toString()) ?? 0,
      workOrderId: json['work_order_id'] is int ? json['work_order_id'] : int.tryParse(json['work_order_id']?.toString() ?? '') ?? 0,
      name: json['name'] ?? '',
      requiresAttachment: json['requires_attachment'] == true || json['requires_attachment'] == 1,
      minPhotos: json['min_photos'] is int ? json['min_photos'] : int.tryParse(json['min_photos']?.toString() ?? '') ?? 0,
      estimatedMinutes: json['estimated_minutes'] is int ? json['estimated_minutes'] : int.tryParse(json['estimated_minutes']?.toString() ?? '') ?? 0,
      isCompleted: json['is_completed'] == true || json['is_completed'] == 1,
      status: json['status'] ?? 'Pending',
      notes: json['notes'] ?? '',
      attachmentPath: json['attachment_path'] ?? '',
      photos: photoUrls,
      localPhotoPaths: [],
      updatedLocally: json['updated_locally'] == 1,
    );
  }

  factory ProcedureModel.fromDb(Map<String, dynamic> map) {
    List<String> photos = [];
    if (map['attachment_path'] != null && map['attachment_path'].toString().isNotEmpty) {
      photos = map['attachment_path'].toString().split('|').where((s) => s.isNotEmpty).toList();
    }

    List<String> localPhotos = [];
    if (map['local_photo_paths'] != null && map['local_photo_paths'].toString().isNotEmpty) {
      localPhotos = map['local_photo_paths'].toString().split('|').where((s) => s.isNotEmpty).toList();
    }

    return ProcedureModel(
      id: map['id'],
      workOrderId: map['work_order_id'],
      name: map['name'],
      requiresAttachment: map['requires_attachment'] == 1,
      minPhotos: map['min_photos'] ?? 0,
      estimatedMinutes: map['estimated_minutes'] ?? 0,
      isCompleted: map['is_completed'] == 1,
      status: map['status'] ?? 'Pending',
      notes: map['notes'] ?? '',
      attachmentPath: map['attachment_path'] ?? '',
      photos: photos,
      localPhotoPaths: localPhotos,
      updatedLocally: map['updated_locally'] == 1,
    );
  }

  Map<String, dynamic> toDbMap() {
    return {
      'id': id,
      'work_order_id': workOrderId,
      'name': name,
      'requires_attachment': requiresAttachment ? 1 : 0,
      'min_photos': minPhotos,
      'estimated_minutes': estimatedMinutes,
      'is_completed': isCompleted ? 1 : 0,
      'status': status,
      'notes': notes,
      'attachment_path': attachmentPath,
      'local_photo_paths': localPhotoPaths.join('|'),
      'updated_locally': updatedLocally ? 1 : 0,
    };
  }

  int get totalPhotosCount => photos.length + localPhotoPaths.length;

  bool get satisfiesAttachmentRequirement {
    if (!requiresAttachment && minPhotos == 0) return true;
    if (minPhotos > 0) return totalPhotosCount >= minPhotos;
    return totalPhotosCount > 0;
  }
}
