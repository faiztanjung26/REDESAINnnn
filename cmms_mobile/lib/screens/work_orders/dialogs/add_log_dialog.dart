import 'package:flutter/material.dart';
import '../../../core/constants/app_colors.dart';

class AddLogDialog extends StatefulWidget {
  const AddLogDialog({Key? key}) : super(key: key);

  @override
  State<AddLogDialog> createState() => _AddLogDialogState();
}

class _AddLogDialogState extends State<AddLogDialog> {
  final TextEditingController _logController = TextEditingController();

  @override
  void dispose() {
    _logController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      title: Row(
        children: const [
          Icon(Icons.notes_rounded, color: AppColors.primary, size: 22),
          SizedBox(width: 10),
          Text(
            'Tambah Catatan Aktivitas',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
        ],
      ),
      content: TextField(
        controller: _logController,
        maxLines: 4,
        decoration: const InputDecoration(
          hintText: 'Tulis progres pekerjaan atau kendala yang ditemukan...',
          contentPadding: EdgeInsets.all(12),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(null),
          child: const Text('Batal'),
        ),
        ElevatedButton(
          onPressed: () {
            final text = _logController.text.trim();
            if (text.isEmpty) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Catatan tidak boleh kosong.')),
              );
              return;
            }
            Navigator.of(context).pop(text);
          },
          child: const Text('Simpan'),
        ),
      ],
    );
  }
}
