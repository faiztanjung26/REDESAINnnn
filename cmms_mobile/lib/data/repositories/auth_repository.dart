import 'dart:convert';
import 'package:sqflite/sqflite.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../core/constants/api_constants.dart';
import '../../core/network/api_service.dart';
import '../../core/database/database_helper.dart';
import '../models/user_model.dart';

class AuthRepository {
  final ApiService _api = ApiService.instance;
  final DatabaseHelper _db = DatabaseHelper.instance;

  Future<UserModel> login(String nrp, String password) async {
    final response = await _api.post(
      ApiConstants.login,
      body: {'nrp': nrp, 'password': password},
    );

    if (response['status'] == 'success') {
      final token = response['token'] as String;
      final user = UserModel.fromJson(response['user']);

      // Persist token and user in SharedPreferences
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('auth_token', token);
      await prefs.setString('user_profile_json', jsonEncode(user.toJson()));
      _api.setToken(token);

      // Cache user in SQLite for offline identification
      final db = await _db.database;
      await db.insert(
        'user_profile',
        user.toDbMap(token),
        conflictAlgorithm: ConflictAlgorithm.replace,
      );

      return user;
    } else {
      throw ApiException(response['message'] ?? 'Login gagal');
    }
  }

  Future<UserModel?> getCachedUser() async {
    final prefs = await SharedPreferences.getInstance();
    final userJson = prefs.getString('user_profile_json');
    if (userJson != null) {
      try {
        return UserModel.fromJson(jsonDecode(userJson));
      } catch (_) {}
    }

    // Fallback to SQLite
    final db = await _db.database;
    final res = await db.query('user_profile', limit: 1);
    if (res.isNotEmpty) {
      final row = res.first;
      return UserModel(
        id: row['id'] as int,
        nrp: row['nrp'] as String? ?? '',
        name: row['name'] as String? ?? '',
        role: row['role'] as String? ?? 'Technician',
        phoneNumber: row['phone_number'] as String? ?? '',
        siteName: row['site_name'] as String? ?? 'Semua Site',
        teamName: row['team_name'] as String? ?? '-',
      );
    }
    return null;
  }

  Future<UserModel> fetchProfileOnline() async {
    final response = await _api.get(ApiConstants.profile);
    if (response['status'] == 'success') {
      final user = UserModel.fromJson(response['user']);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('user_profile_json', jsonEncode(user.toJson()));
      return user;
    } else {
      throw ApiException(response['message'] ?? 'Gagal memuat profil');
    }
  }

  Future<void> updateProfile(String name, String phone) async {
    final response = await _api.post(
      ApiConstants.updateProfile,
      body: {'name': name, 'phone_number': phone},
    );
    if (response['status'] == 'success') {
      final prefs = await SharedPreferences.getInstance();
      final cached = await getCachedUser();
      if (cached != null) {
        final updated = UserModel(
          id: cached.id,
          nrp: cached.nrp,
          name: name,
          role: cached.role,
          phoneNumber: phone,
          siteId: cached.siteId,
          siteName: cached.siteName,
          teamId: cached.teamId,
          teamName: cached.teamName,
          lastLogin: cached.lastLogin,
        );
        await prefs.setString('user_profile_json', jsonEncode(updated.toJson()));
      }
    } else {
      throw ApiException(response['message'] ?? 'Gagal memperbarui profil');
    }
  }

  Future<void> changePassword(String currentPassword, String newPassword, String confirmPassword) async {
    final response = await _api.post(
      ApiConstants.changePassword,
      body: {
        'current_password': currentPassword,
        'new_password': newPassword,
        'confirm_password': confirmPassword,
      },
    );
    if (response['status'] != 'success') {
      throw ApiException(response['message'] ?? 'Gagal mengubah kata sandi');
    }
  }

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('auth_token');
    await prefs.remove('user_profile_json');
    _api.setToken(null);
  }
}
