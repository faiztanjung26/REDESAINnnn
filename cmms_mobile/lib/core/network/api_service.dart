import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../constants/api_constants.dart';

class ApiException implements Exception {
  final String message;
  final int? statusCode;

  ApiException(this.message, [this.statusCode]);

  @override
  String toString() => message;
}

class ApiService {
  static final ApiService instance = ApiService._init();
  ApiService._init();

  String? _token;
  String? _customBaseUrl;

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString('auth_token');
    _customBaseUrl = prefs.getString('server_base_url');
  }

  void setToken(String? token) {
    _token = token;
  }

  Future<void> setBaseUrl(String url) async {
    final cleanUrl = url.trim().replaceAll(RegExp(r'/+$'), '');
    _customBaseUrl = cleanUrl;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('server_base_url', cleanUrl);
  }

  Future<String> getBaseUrl() async {
    if (_customBaseUrl != null && _customBaseUrl!.isNotEmpty) {
      return _customBaseUrl!;
    }
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString('server_base_url');
    if (saved != null && saved.isNotEmpty) {
      _customBaseUrl = saved;
      return saved;
    }
    return ApiConstants.defaultBaseUrl;
  }

  Map<String, String> _getHeaders({bool isMultipart = false}) {
    final headers = <String, String>{};
    if (!isMultipart) {
      headers['Content-Type'] = 'application/json';
      headers['Accept'] = 'application/json';
    }
    if (_token != null && _token!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $_token';
    }
    return headers;
  }

  Future<dynamic> get(String endpoint, {Map<String, dynamic>? queryParams}) async {
    final baseUrl = await getBaseUrl();
    var uri = Uri.parse('$baseUrl$endpoint');
    if (queryParams != null && queryParams.isNotEmpty) {
      final stringParams = queryParams.map((k, v) => MapEntry(k, v.toString()));
      uri = uri.replace(queryParameters: stringParams);
    }

    try {
      final response = await http
          .get(uri, headers: _getHeaders())
          .timeout(ApiConstants.timeoutDuration);

      return _handleResponse(response);
    } on http.ClientException {
      throw ApiException('Tidak dapat terhubung ke server. Periksa URL server dan jaringan Anda.');
    } catch (e) {
      if (e is ApiException) rethrow;
      throw ApiException('Terjadi kendala jaringan: $e');
    }
  }

  Future<dynamic> post(String endpoint, {dynamic body}) async {
    final baseUrl = await getBaseUrl();
    final uri = Uri.parse('$baseUrl$endpoint');

    try {
      final response = await http
          .post(
            uri,
            headers: _getHeaders(),
            body: body != null ? jsonEncode(body) : null,
          )
          .timeout(ApiConstants.timeoutDuration);

      return _handleResponse(response);
    } on http.ClientException {
      throw ApiException('Tidak dapat terhubung ke server.');
    } catch (e) {
      if (e is ApiException) rethrow;
      throw ApiException('Gagal mengirim data ke server: $e');
    }
  }

  Future<dynamic> delete(String endpoint) async {
    final baseUrl = await getBaseUrl();
    final uri = Uri.parse('$baseUrl$endpoint');

    try {
      final response = await http
          .delete(uri, headers: _getHeaders())
          .timeout(ApiConstants.timeoutDuration);

      return _handleResponse(response);
    } catch (e) {
      if (e is ApiException) rethrow;
      throw ApiException('Gagal menghapus data: $e');
    }
  }

  Future<dynamic> postMultipart(
    String endpoint, {
    Map<String, String>? fields,
    List<http.MultipartFile>? files,
  }) async {
    final baseUrl = await getBaseUrl();
    final uri = Uri.parse('$baseUrl$endpoint');

    try {
      final request = http.MultipartRequest('POST', uri);
      request.headers.addAll(_getHeaders(isMultipart: true));

      if (fields != null) {
        request.fields.addAll(fields);
      }

      if (files != null) {
        request.files.addAll(files);
      }

      final streamedResponse = await request.send().timeout(ApiConstants.syncTimeoutDuration);
      final response = await http.Response.fromStream(streamedResponse);

      return _handleResponse(response);
    } catch (e) {
      if (e is ApiException) rethrow;
      throw ApiException('Gagal mengunggah foto / berkas: $e');
    }
  }

  dynamic _handleResponse(http.Response response) {
    final code = response.statusCode;
    dynamic body;
    try {
      body = jsonDecode(utf8.decode(response.bodyBytes));
    } catch (_) {
      body = {'message': response.body};
    }

    if (code >= 200 && code < 300) {
      return body;
    } else if (code == 401) {
      throw ApiException('Sesi login telah kedaluwarsa. Silakan login kembali.', 401);
    } else if (code == 403) {
      throw ApiException(body['message'] ?? 'Akses ditolak.', 403);
    } else {
      final message = body is Map && body.containsKey('message')
          ? body['message']
          : 'Terjadi kesalahan server ($code)';
      throw ApiException(message, code);
    }
  }
}
