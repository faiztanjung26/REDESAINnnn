import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/constants/app_colors.dart';
import '../providers/sync_provider.dart';

class ConnectionBanner extends StatelessWidget {
  const ConnectionBanner({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Consumer<SyncProvider>(
      builder: (context, syncProv, child) {
        if (syncProv.isSyncing) {
          return Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            color: AppColors.bgHold,
            child: Row(
              children: [
                const SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation<Color>(AppColors.statusHold),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    syncProv.syncMessage ?? 'Menyinkronkan data dengan server...',
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFFB45309),
                    ),
                  ),
                ),
              ],
            ),
          );
        }

        if (!syncProv.isOnline) {
          return Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            color: AppColors.bgOverdue,
            child: Row(
              children: [
                const Icon(
                  Icons.wifi_off_rounded,
                  size: 16,
                  color: AppColors.statusOverdue,
                ),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text(
                    'Mode Offline Aktif • Data disimpan secara lokal di perangkat',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: AppColors.statusOverdue,
                    ),
                  ),
                ),
                if (syncProv.pendingCount > 0)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppColors.statusOverdue,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      '${syncProv.pendingCount} antrean',
                      style: const TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                        color: Colors.white,
                      ),
                    ),
                  ),
              ],
            ),
          );
        }

        if (syncProv.pendingCount > 0) {
          return Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            color: AppColors.bgInProgress,
            child: Row(
              children: [
                const Icon(
                  Icons.cloud_upload_outlined,
                  size: 16,
                  color: AppColors.primary,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '${syncProv.pendingCount} data perubahan belum tersinkronkan',
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: AppColors.primary,
                    ),
                  ),
                ),
                GestureDetector(
                  onTap: () => syncProv.triggerSync(),
                  child: const Text(
                    'Kirim Sekarang',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: AppColors.primary,
                      decoration: TextDecoration.underline,
                    ),
                  ),
                ),
              ],
            ),
          );
        }

        return const SizedBox.shrink();
      },
    );
  }
}
