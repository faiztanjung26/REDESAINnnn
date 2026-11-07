class UserModel {
  final int id;
  final String nrp;
  final String name;
  final String role;
  final String phoneNumber;
  final int? siteId;
  final String siteName;
  final int? teamId;
  final String teamName;
  final String? lastLogin;

  UserModel({
    required this.id,
    required this.nrp,
    required this.name,
    required this.role,
    required this.phoneNumber,
    this.siteId,
    required this.siteName,
    this.teamId,
    required this.teamName,
    this.lastLogin,
  });

  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      id: json['id'] is int ? json['id'] : int.tryParse(json['id'].toString()) ?? 0,
      nrp: json['nrp'] ?? '',
      name: json['name'] ?? '',
      role: json['role'] ?? 'Technician',
      phoneNumber: json['phone_number'] ?? '',
      siteId: json['site_id'] is int ? json['site_id'] : int.tryParse(json['site_id']?.toString() ?? ''),
      siteName: json['site_name'] ?? 'Semua Site',
      teamId: json['team_id'] is int ? json['team_id'] : int.tryParse(json['team_id']?.toString() ?? ''),
      teamName: json['team_name'] ?? '-',
      lastLogin: json['last_login'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'nrp': nrp,
      'name': name,
      'role': role,
      'phone_number': phoneNumber,
      'site_id': siteId,
      'site_name': siteName,
      'team_id': teamId,
      'team_name': teamName,
      'last_login': lastLogin,
    };
  }

  Map<String, dynamic> toDbMap(String token) {
    return {
      'id': id,
      'nrp': nrp,
      'name': name,
      'role': role,
      'phone_number': phoneNumber,
      'site_name': siteName,
      'team_name': teamName,
      'token': token,
      'last_sync': DateTime.now().toIso8601String(),
    };
  }
}
