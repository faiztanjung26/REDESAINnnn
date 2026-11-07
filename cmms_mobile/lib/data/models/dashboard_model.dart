import 'work_order_model.dart';

class DashboardMetrics {
  final int totalAssigned;
  final int assigned;
  final int inProgress;
  final int hold;
  final int solved;
  final int completed;
  final int overdue;
  final int dueToday;

  DashboardMetrics({
    this.totalAssigned = 0,
    this.assigned = 0,
    this.inProgress = 0,
    this.hold = 0,
    this.solved = 0,
    this.completed = 0,
    this.overdue = 0,
    this.dueToday = 0,
  });

  factory DashboardMetrics.fromJson(Map<String, dynamic> json) {
    return DashboardMetrics(
      totalAssigned: json['total_assigned'] ?? 0,
      assigned: json['assigned'] ?? 0,
      inProgress: json['in_progress'] ?? 0,
      hold: json['hold'] ?? 0,
      solved: json['solved'] ?? 0,
      completed: json['completed'] ?? 0,
      overdue: json['overdue'] ?? 0,
      dueToday: json['due_today'] ?? 0,
    );
  }
}

class DashboardData {
  final DashboardMetrics metrics;
  final List<WorkOrderModel> todayWorkOrders;
  final List<WorkOrderModel> urgentWorkOrders;
  final List<WorkOrderModel> recentWorkOrders;

  DashboardData({
    required this.metrics,
    required this.todayWorkOrders,
    required this.urgentWorkOrders,
    required this.recentWorkOrders,
  });

  factory DashboardData.fromJson(Map<String, dynamic> json) {
    final m = json['metrics'] is Map<String, dynamic>
        ? DashboardMetrics.fromJson(json['metrics'])
        : DashboardMetrics();

    List<WorkOrderModel> parseList(dynamic raw) {
      if (raw is List) {
        return raw.map((e) => WorkOrderModel.fromJson(e as Map<String, dynamic>)).toList();
      }
      return [];
    }

    return DashboardData(
      metrics: m,
      todayWorkOrders: parseList(json['today_work_orders']),
      urgentWorkOrders: parseList(json['urgent_work_orders']),
      recentWorkOrders: parseList(json['recent_work_orders']),
    );
  }
}
