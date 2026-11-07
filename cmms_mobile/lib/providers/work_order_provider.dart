import 'package:flutter/material.dart';
import '../data/models/work_order_model.dart';
import '../data/repositories/work_order_repository.dart';

class WorkOrderProvider extends ChangeNotifier {
  final WorkOrderRepository _repo = WorkOrderRepository();

  List<WorkOrderModel> _workOrders = [];
  bool _isLoading = false;
  String? _errorMessage;

  String _statusFilter = 'all';
  String _priorityFilter = 'Semua';
  String _searchQuery = '';

  List<WorkOrderModel> get workOrders => _workOrders;
  bool get isLoading => _isLoading;
  String? get errorMessage => _errorMessage;
  String get statusFilter => _statusFilter;
  String get priorityFilter => _priorityFilter;
  String get searchQuery => _searchQuery;

  Future<void> loadWorkOrders({bool forceRefresh = false}) async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    try {
      _workOrders = await _repo.getWorkOrders(
        status: _statusFilter,
        priority: _priorityFilter,
        search: _searchQuery,
        forceRefresh: forceRefresh,
      );
    } catch (e) {
      _errorMessage = 'Gagal memuat Work Order: $e';
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  void setStatusFilter(String status) {
    if (_statusFilter != status) {
      _statusFilter = status;
      loadWorkOrders();
    }
  }

  void setPriorityFilter(String priority) {
    if (_priorityFilter != priority) {
      _priorityFilter = priority;
      loadWorkOrders();
    }
  }

  void setSearchQuery(String query) {
    _searchQuery = query;
    loadWorkOrders();
  }

  Future<WorkOrderModel> getDetail(int id) async {
    return await _repo.getWorkOrderDetail(id);
  }
}
