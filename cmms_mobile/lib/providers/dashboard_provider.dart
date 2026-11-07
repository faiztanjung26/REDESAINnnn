import 'package:flutter/material.dart';
import '../core/constants/api_constants.dart';
import '../core/network/api_service.dart';
import '../core/database/database_helper.dart';
import '../data/models/dashboard_model.dart';
import '../data/models/work_order_model.dart';

class DashboardProvider extends ChangeNotifier {
  final ApiService _api = ApiService.instance;
  final DatabaseHelper _db = DatabaseHelper.instance;

  DashboardData? _data;
  bool _isLoading = false;
  String? _errorMessage;

  DashboardData? get data => _data;
  bool get isLoading => _isLoading;
  String? get errorMessage => _errorMessage;

  Future<void> loadDashboard() async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    try {
      final response = await _api.get(ApiConstants.dashboard);
      if (response['status'] == 'success') {
        _data = DashboardData.fromJson(response);
        _isLoading = false;
        notifyListeners();
        return;
      }
    } catch (_) {
      // Offline fallback: compute from local SQLite database
    }

    try {
      final db = await _db.database;
      final maps = await db.query('work_orders');
      final allWos = maps.map((m) => WorkOrderModel.fromDb(m)).toList();

      int assigned = 0;
      int inProgress = 0;
      int hold = 0;
      int solved = 0;
      int completed = 0;
      int overdue = 0;
      int dueToday = 0;

      final now = DateTime.now();
      final todayStr = "${now.year}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}";

      List<WorkOrderModel> todayWos = [];
      List<WorkOrderModel> urgentWos = [];
      List<WorkOrderModel> recentWos = [];

      for (var wo in allWos) {
        if (wo.status == 'Assigned' || wo.status == 'Confirmed') assigned++;
        if (wo.status == 'In Progress') inProgress++;
        if (wo.status == 'Hold') hold++;
        if (wo.status == 'Solved') solved++;
        if (wo.status == 'Completed' || wo.status == 'Closed') completed++;
        if (wo.isOverdue) overdue++;

        if (wo.suggestedCompletionDate != null && wo.suggestedCompletionDate!.startsWith(todayStr)) {
          dueToday++;
          if (todayWos.length < 5) todayWos.add(wo);
        }

        if ((wo.priority == 'Highest' || wo.priority == 'High' || wo.isOverdue) &&
            wo.status != 'Solved' && wo.status != 'Completed' && wo.status != 'Closed') {
          if (urgentWos.length < 5) urgentWos.add(wo);
        }

        if (recentWos.length < 5) recentWos.add(wo);
      }

      _data = DashboardData(
        metrics: DashboardMetrics(
          totalAssigned: allWos.length,
          assigned: assigned,
          inProgress: inProgress,
          hold: hold,
          solved: solved,
          completed: completed,
          overdue: overdue,
          dueToday: dueToday,
        ),
        todayWorkOrders: todayWos,
        urgentWorkOrders: urgentWos,
        recentWorkOrders: recentWos,
      );
    } catch (e) {
      _errorMessage = 'Gagal memuat dashboard: $e';
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
}
