import 'package:flutter/material.dart';
import '../../core/constants/app_colors.dart';
import '../../core/network/api_service.dart';

class ServerSettingsDialog extends StatefulWidget {
  const ServerSettingsDialog({Key? key}) : super(key: key);

  @override
  State<ServerSettingsDialog> createState() => _ServerSettingsDialogState();
}

class _ServerSettingsDialogState extends State<ServerSettingsDialog> {
  final TextEditingController _urlController = TextEditingController();
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadCurrentUrl();
  }

  Future<void> _loadCurrentUrl() async {
    final url = await ApiService.instance.getBaseUrl();
    _urlController.text = url;
    setState(() => _isLoading = false);
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final url = _urlController.text.trim();
    if (url.isEmpty) return;

    await ApiService.instance.setBaseUrl(url);
    if (!mounted) return;
    Navigator.of(context).pop(true);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Alamat server berhasil diperbarui.'),
        backgroundColor: AppColors.statusCompleted,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      title: Row(
        children: const [
          Icon(Icons.dns_outlined, color: AppColors.primary, size: 22),
          SizedBox(width: 10),
          Text(
            'Pengaturan Server',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
        ],
      ),
      content: _isLoading
          ? const SizedBox(
              height: 100,
              child: Center(child: CircularProgressIndicator()),
            )
          : Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Masukkan alamat URL backend CMMS Anda. Pastikan diawali http:// atau https://',
                  style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _urlController,
                  decoration: const InputDecoration(
                    labelText: 'URL Server CMMS',
                    hintText: 'http://192.168.1.5:5000',
                    prefixIcon: Icon(Icons.link, size: 20),
                  ),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 6,
                  children: [
                    ActionChip(
                      label: const Text('Emulator (10.0.2.2:5000)', style: TextStyle(fontSize: 11)),
                      onPressed: () => _urlController.text = 'http://10.0.2.2:5000',
                    ),
                    ActionChip(
                      label: const Text('Localhost:5000', style: TextStyle(fontSize: 11)),
                      onPressed: () => _urlController.text = 'http://localhost:5000',
                    ),
                  ],
                ),
              ],
            ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Batal'),
        ),
        ElevatedButton(
          onPressed: _save,
          child: const Text('Simpan'),
        ),
      ],
    );
  }
}
