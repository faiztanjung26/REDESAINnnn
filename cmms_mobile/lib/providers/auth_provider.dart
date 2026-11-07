import 'package:flutter/material.dart';
import '../data/models/user_model.dart';
import '../data/repositories/auth_repository.dart';

class AuthProvider extends ChangeNotifier {
  final AuthRepository _repo = AuthRepository();

  UserModel? _user;
  bool _isLoading = false;
  String? _errorMessage;

  UserModel? get user => _user;
  bool get isLoggedIn => _user != null;
  bool get isLoading => _isLoading;
  String? get errorMessage => _errorMessage;

  Future<void> checkInitialAuth() async {
    _isLoading = true;
    notifyListeners();
    try {
      _user = await _repo.getCachedUser();
      if (_user != null) {
        // Try background refresh if online
        _repo.fetchProfileOnline().then((onlineUser) {
          _user = onlineUser;
          notifyListeners();
        }).catchError((_) {});
      }
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> login(String nrp, String password) async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    try {
      _user = await _repo.login(nrp, password);
      _isLoading = false;
      notifyListeners();
      return true;
    } catch (e) {
      _isLoading = false;
      _errorMessage = e.toString();
      notifyListeners();
      return false;
    }
  }

  Future<bool> updateProfile(String name, String phone) async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    try {
      await _repo.updateProfile(name, phone);
      if (_user != null) {
        _user = UserModel(
          id: _user!.id,
          nrp: _user!.nrp,
          name: name,
          role: _user!.role,
          phoneNumber: phone,
          siteId: _user!.siteId,
          siteName: _user!.siteName,
          teamId: _user!.teamId,
          teamName: _user!.teamName,
          lastLogin: _user!.lastLogin,
        );
      }
      _isLoading = false;
      notifyListeners();
      return true;
    } catch (e) {
      _isLoading = false;
      _errorMessage = e.toString();
      notifyListeners();
      return false;
    }
  }

  Future<bool> changePassword(String currentPassword, String newPassword, String confirmPassword) async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    try {
      await _repo.changePassword(currentPassword, newPassword, confirmPassword);
      _isLoading = false;
      notifyListeners();
      return true;
    } catch (e) {
      _isLoading = false;
      _errorMessage = e.toString();
      notifyListeners();
      return false;
    }
  }

  Future<void> logout() async {
    await _repo.logout();
    _user = null;
    notifyListeners();
  }
}
