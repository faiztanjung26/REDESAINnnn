import 'dart:async';
import 'package:connectivity_plus/connectivity_plus.dart';

class NetworkInfo {
  static final NetworkInfo instance = NetworkInfo._init();
  NetworkInfo._init();

  final Connectivity _connectivity = Connectivity();
  final StreamController<bool> _connectionStreamController = StreamController<bool>.broadcast();

  Stream<bool> get onConnectionChange => _connectionStreamController.stream;

  Future<void> init() async {
    _connectivity.onConnectivityChanged.listen((results) async {
      final isOnline = await checkConnection();
      _connectionStreamController.add(isOnline);
    });
  }

  Future<bool> checkConnection() async {
    try {
      final connectivityResults = await _connectivity.checkConnectivity();
      if (connectivityResults.contains(ConnectivityResult.none)) {
        return false;
      }
      return true;
    } catch (_) {
      return true;
    }
  }
}
