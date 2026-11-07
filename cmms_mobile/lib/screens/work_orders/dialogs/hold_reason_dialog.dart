import 'package:flutter/material.dart';
import '../../../core/constants/app_colors.dart';

class HoldReasonDialog extends StatefulWidget {
  const HoldReasonDialog({Key? key}) : super(key: key);

  @override
  State<HoldReasonDialog> createState() => _HoldReasonDialogState();
}

class _HoldReasonDialogState extends State<HoldReasonDialog> {
  final TextEditingController _reasonController = TextEditingController();
  final List<String> _quickReasons = [
    'Menunggu ketersediaan suku cadang',
    'Menunggu izin kerja / access permit',
    'Kendala operasional mesin di lokasi',
    'Menunggu tim spesialis / vendor',
  ];

  @override
  void dispose() {
    _reasonController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      title: Row(
        children: const [
          Icon(Icons.pause_circle_outline, color: AppColors.statusHold, size: 24),
          SizedBox(width: 10),
          Text(
            'Tunda Pengerjaan (Hold)',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
        ],
      ),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Silakan tulis alasan penundaan pengerjaan Work Order ini:',
              style: TextStyle(fontSize: 13, color: AppColors.textSecondary),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _reasonController,
              maxLines: 3,
              decoration: const InputDecoration(
                hintText: 'Tulis alasan penundaan...',
                contentPadding: EdgeInsets.all(12),
              ),
            ),
            const SizedBox(height: 14),
            const Text(
              'Alasan Cepat:',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.textSecondary),
            ),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: _quickReasons.map((r) {
                return InkWell(
                  onTap: () => setState(() => _reasonController.text = r),
                  borderRadius: BorderRadius.circular(16),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: AppColors.bgHold,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Text(
                      r,
                      style: const TextStyle(fontSize: 11, color: Color(0xFFB45309), fontWeight: FontWeight.w600),
                    ),
                  ),
                );
              }).toList(),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(null),
          child: const Text('Batal'),
        ),
        ElevatedButton(
          style: ElevatedButton.styleFrom(backgroundColor: AppColors.statusHold),
          onPressed: () {
            final reason = _reasonController.text.trim();
            if (reason.isEmpty) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Alasan penundaan wajib diisi!')),
              );
              return;
            }
            Navigator.of(context).pop(reason);
          },
          child: const Text('Tunda WO', style: TextStyle(color: Colors.white)),
        ),
      ],
    );
  }
}
