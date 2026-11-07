class ApiConstants {
  // Default base URL (Android emulator: 10.0.2.2, Physical device: change in settings)
  static const String defaultBaseUrl = 'http://10.0.2.2:5000';
  
  static const Duration timeoutDuration = Duration(seconds: 15);
  static const Duration syncTimeoutDuration = Duration(seconds: 45);

  // Auth & Profile
  static const String login = '/api/mobile/login';
  static const String profile = '/api/mobile/profile';
  static const String updateProfile = '/api/mobile/profile/update';
  static const String changePassword = '/api/mobile/profile/change-password';

  // Dashboard
  static const String dashboard = '/api/mobile/dashboard';

  // Work Orders
  static const String workOrders = '/api/mobile/work-orders';
  static String workOrderDetail(int id) => '/api/mobile/work-orders/$id';
  static String updateStatus(int id) => '/api/mobile/work-orders/$id/status';
  static String updateProcedure(int id, int procId) => '/api/mobile/work-orders/$id/procedures/$procId';
  static String deleteProcedurePhoto(int id, int procId) => '/api/mobile/work-orders/$id/procedures/$procId/photos/delete';
  static String updateChecklists(int id) => '/api/mobile/work-orders/$id/checklists';
  static String addPart(int id) => '/api/mobile/work-orders/$id/parts';
  static String removePart(int id, int partUsageId) => '/api/mobile/work-orders/$id/parts/$partUsageId';
  static String addLog(int id) => '/api/mobile/work-orders/$id/logs';
  static String saveSignature(int id) => '/api/mobile/work-orders/$id/signature';

  // Parts
  static const String parts = '/api/mobile/parts';

  // Offline Sync
  static const String syncDownload = '/api/mobile/sync/download';
  static const String syncUpload = '/api/mobile/sync/upload';
}
