import 'procedure_model.dart';
import 'checklist_model.dart';
import 'part_model.dart';
import 'work_log_model.dart';

class WorkOrderModel {
  final int id;
  final String code;
  final String description;
  final String priority;
  String status;
  String statusColor;
  final String maintenanceType;
  final String projectCode;
  final String workInstructions;
  String delayReason;
  final int assetId;
  final String assetName;
  final String assetCode;
  final String assetLocation;
  final String assetSite;
  final String team;
  final String? suggestedStartDate;
  final String? suggestedCompletionDate;
  String? startDate;
  String? endDate;
  final bool isOverdue;
  String customerName;
  String customerTitle;
  String customerSignature;
  String technicianSignature;
  bool updatedLocally;

  // Embedded details
  List<ProcedureModel> procedures;
  List<ChecklistModel> checklists;
  List<UsedPartModel> partsUsed;
  List<WorkLogModel> logs;
  List<String> allowedActions;

  WorkOrderModel({
    required this.id,
    required this.code,
    required this.description,
    required this.priority,
    required this.status,
    required this.statusColor,
    required this.maintenanceType,
    this.projectCode = '',
    this.workInstructions = '',
    this.delayReason = '',
    this.assetId = 0,
    required this.assetName,
    required this.assetCode,
    required this.assetLocation,
    required this.assetSite,
    required this.team,
    this.suggestedStartDate,
    this.suggestedCompletionDate,
    this.startDate,
    this.endDate,
    this.isOverdue = false,
    this.customerName = '',
    this.customerTitle = '',
    this.customerSignature = '',
    this.technicianSignature = '',
    this.updatedLocally = false,
    List<ProcedureModel>? procedures,
    List<ChecklistModel>? checklists,
    List<UsedPartModel>? partsUsed,
    List<WorkLogModel>? logs,
    List<String>? allowedActions,
  })  : procedures = procedures ?? [],
        checklists = checklists ?? [],
        partsUsed = partsUsed ?? [],
        logs = logs ?? [],
        allowedActions = allowedActions ?? [];

  factory WorkOrderModel.fromJson(Map<String, dynamic> json) {
    // Procedures
    List<ProcedureModel> procs = [];
    if (json['procedures'] is List) {
      procs = (json['procedures'] as List)
          .map((p) => ProcedureModel.fromJson(p as Map<String, dynamic>))
          .toList();
    }

    // Checklists
    List<ChecklistModel> chks = [];
    if (json['checklists'] is List) {
      chks = (json['checklists'] as List)
          .map((c) => ChecklistModel.fromJson(c as Map<String, dynamic>))
          .toList();
    }

    // Parts
    List<UsedPartModel> parts = [];
    final woId = json['id'] is int ? json['id'] : int.tryParse(json['id'].toString()) ?? 0;
    if (json['parts_used'] is List) {
      parts = (json['parts_used'] as List)
          .map((p) => UsedPartModel.fromJson(p as Map<String, dynamic>, woId))
          .toList();
    }

    // Logs
    List<WorkLogModel> logsList = [];
    if (json['logs'] is List) {
      logsList = (json['logs'] as List)
          .map((l) => WorkLogModel.fromJson(l as Map<String, dynamic>, woId))
          .toList();
    }

    // Signatures
    String custName = '';
    String custTitle = '';
    String custSig = '';
    String techSig = '';
    if (json['signatures'] is Map) {
      final sigs = json['signatures'] as Map<String, dynamic>;
      custName = sigs['customer_name'] ?? '';
      custTitle = sigs['customer_title'] ?? '';
      custSig = sigs['customer_signature'] ?? '';
      techSig = sigs['technician_signature'] ?? '';
    } else {
      custName = json['customer_name'] ?? '';
      custTitle = json['customer_title'] ?? '';
      custSig = json['customer_signature'] ?? '';
      techSig = json['technician_signature'] ?? '';
    }

    // Asset
    int aId = 0;
    String aName = '-';
    String aCode = '-';
    String aLoc = '-';
    String aSite = '-';

    if (json['asset'] is Map) {
      final aMap = json['asset'] as Map<String, dynamic>;
      aId = aMap['id'] is int ? aMap['id'] : int.tryParse(aMap['id']?.toString() ?? '') ?? 0;
      aName = aMap['name'] ?? '-';
      aCode = aMap['code'] ?? '-';
      aLoc = aMap['location'] ?? '-';
      aSite = aMap['site'] ?? '-';
    } else {
      aId = json['asset_id'] is int ? json['asset_id'] : int.tryParse(json['asset_id']?.toString() ?? '') ?? 0;
      aName = json['asset_name'] ?? '-';
      aCode = json['asset_code'] ?? '-';
      aLoc = json['location'] ?? '-';
      aSite = json['site'] ?? '-';
    }

    List<String> actions = [];
    if (json['allowed_actions'] is List) {
      actions = (json['allowed_actions'] as List).map((e) => e.toString()).toList();
    }

    return WorkOrderModel(
      id: woId,
      code: json['code'] ?? 'WO-$woId',
      description: json['description'] ?? '',
      priority: json['priority'] ?? 'Medium',
      status: json['status'] ?? 'Draft',
      statusColor: json['status_color'] ?? '#0ea5e9',
      maintenanceType: json['maintenance_type'] ?? 'Corrective',
      projectCode: json['project_code'] ?? '',
      workInstructions: json['work_instructions'] ?? '',
      delayReason: json['delay_reason'] ?? '',
      assetId: aId,
      assetName: aName,
      assetCode: aCode,
      assetLocation: aLoc,
      assetSite: aSite,
      team: json['team'] ?? '-',
      suggestedStartDate: json['suggested_start_date'],
      suggestedCompletionDate: json['suggested_completion_date'],
      startDate: json['start_date'],
      endDate: json['end_date'],
      isOverdue: json['is_overdue'] == true || json['is_overdue'] == 1,
      customerName: custName,
      customerTitle: custTitle,
      customerSignature: custSig,
      technicianSignature: techSig,
      updatedLocally: json['updated_locally'] == 1,
      procedures: procs,
      checklists: chks,
      partsUsed: parts,
      logs: logsList,
      allowedActions: actions,
    );
  }

  factory WorkOrderModel.fromDb(Map<String, dynamic> map) {
    return WorkOrderModel(
      id: map['id'],
      code: map['code'] ?? '',
      description: map['description'] ?? '',
      priority: map['priority'] ?? 'Medium',
      status: map['status'] ?? 'Draft',
      statusColor: map['status_color'] ?? '#0ea5e9',
      maintenanceType: map['maintenance_type'] ?? 'Corrective',
      projectCode: map['project_code'] ?? '',
      workInstructions: map['work_instructions'] ?? '',
      delayReason: map['delay_reason'] ?? '',
      assetId: map['asset_id'] ?? 0,
      assetName: map['asset_name'] ?? '-',
      assetCode: map['asset_code'] ?? '-',
      assetLocation: map['asset_location'] ?? '-',
      assetSite: map['asset_site'] ?? '-',
      team: map['team'] ?? '-',
      suggestedStartDate: map['suggested_start_date'],
      suggestedCompletionDate: map['suggested_completion_date'],
      startDate: map['start_date'],
      endDate: map['end_date'],
      isOverdue: map['is_overdue'] == 1,
      customerName: map['customer_name'] ?? '',
      customerTitle: map['customer_title'] ?? '',
      customerSignature: map['customer_signature'] ?? '',
      technicianSignature: map['technician_signature'] ?? '',
      updatedLocally: map['updated_locally'] == 1,
    );
  }

  Map<String, dynamic> toDbMap() {
    return {
      'id': id,
      'code': code,
      'description': description,
      'priority': priority,
      'status': status,
      'status_color': statusColor,
      'maintenance_type': maintenanceType,
      'project_code': projectCode,
      'work_instructions': workInstructions,
      'delay_reason': delayReason,
      'asset_id': assetId,
      'asset_name': assetName,
      'asset_code': assetCode,
      'asset_location': assetLocation,
      'asset_site': assetSite,
      'team': team,
      'suggested_start_date': suggestedStartDate,
      'suggested_completion_date': suggestedCompletionDate,
      'start_date': startDate,
      'end_date': endDate,
      'is_overdue': isOverdue ? 1 : 0,
      'customer_name': customerName,
      'customer_title': customerTitle,
      'customer_signature': customerSignature,
      'technician_signature': technicianSignature,
      'updated_locally': updatedLocally ? 1 : 0,
    };
  }

  // Helper Getters
  int get proceduresCount => procedures.length;
  int get proceduresCompletedCount => procedures.where((p) => p.isCompleted).length;

  int get progressPercent {
    if (procedures.isEmpty) return 0;
    return ((proceduresCompletedCount / procedures.length) * 100).round();
  }

  bool get canStart => status == 'Draft' || status == 'Assigned' || status == 'Confirmed';
  bool get canHold => status == 'In Progress';
  bool get canResume => status == 'Hold';
  bool get canSolve => status == 'In Progress';
}
