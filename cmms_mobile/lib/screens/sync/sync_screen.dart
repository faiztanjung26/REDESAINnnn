import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/constants/app_colors.dart';
import '../../core/utils/formatters.dart';
import '../../core/database/database_helper.dart';
import '../../providers/sync_provider.dart';
import '../../data/models/sync_queue_item.dart';

class SyncScreen extends StatefulWidget {
  const SyncScreen({Key? key}) : super(key: key);

  @override
  State<SyncScreen> createState() => _SyncScreenState();
}

class _SyncScreenState extends State<SyncScreen> {
  List<SyncQueueItem> _pendingItems = [];
  bool _isLoadingOutbox = false;

  @override
  void initState() {
    super.initState();
    _loadOutbox();
  }

  Future<void> _loadOutbox() async {
    setState(() => _isLoadingOutbox = true);
    final items = await DatabaseHelper.instance.getPendingSyncItems();
    setState(() {
      _pendingItems = items.map((m) => SyncQueueItem.fromDb(m)).toList();
      _isLoadingOutbox = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final syncProv = Provider.of<SyncProvider>(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Sinkronisasi Offline'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              syncProv.refreshPendingCount();
              _loadOutbox();
            },
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Status Card
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: syncProv.isOnline
                      ? [AppColors.primary, AppColors.primaryLight]
                      : [const Color(0xFF475569), const Color(0xFF334155)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(20),
                boxShadow: [
                  BoxShadow(
                    color: (syncProv.isOnline ? AppColors.primary : Colors.black).withOpacity(0.2),
                    blurRadius: 16,
                    offset: const Offset(0, 6),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.2),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Row(
                          children: [
                            Icon(
                              syncProv.isOnline ? Icons.wifi : Icons.wifi_off,
                              color: Colors.white,
                              size: 14,
                            ),
                            const SizedBox(width: 6),
                            Text(
                              syncProv.isOnline ? 'Terhubung Jaringan' : 'Mode Luar Jaringan (Offline)',
                              style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700),
                            ),
                          ],
                        ),
                      ),
                      if (syncProv.pendingCount > 0)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            color: AppColors.statusHold,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Text(
                            '${syncProv.pendingCount} Belum Sinkron',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 18),
                  const Text(
                    'Manajer Data Lapangan',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                      color: Colors.white,
                      letterSpacing: -0.3,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Terakhir Sinkron: ${Formatters.formatDate(syncProv.lastSyncTime)}',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.white.withOpacity(0.85),
                    ),
                  ),
                  const SizedBox(height: 20),
                  ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: syncProv.isOnline ? AppColors.primary : AppColors.textPrimary,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                    onPressed: syncProv.isSyncing
                        ? null
                        : () async {
                            final ok = await syncProv.triggerSync();
                            _loadOutbox();
                            if (mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                  content: Text(syncProv.syncMessage ?? (ok ? 'Sinkronisasi berhasil!' : 'Sinkronisasi gagal.')),
                                  backgroundColor: ok ? AppColors.statusCompleted : AppColors.statusOverdue,
                                ),
                              );
                            }
                          },
                    icon: syncProv.isSyncing
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.sync_rounded),
                    label: Text(
                      syncProv.isSyncing ? 'Sedang Menyinkronkan...' : 'Sinkronkan Sekarang',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // Outbox List Section Header
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Antrean Outbox (Data Belum Terkirim)',
                  style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, letterSpacing: -0.2),
                ),
                Text(
                  '${_pendingItems.length} item',
                  style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, fontWeight: FontWeight.w600),
                ),
              ],
            ),
            const SizedBox(height: 12),

            if (_isLoadingOutbox)
              const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator()))
            else if (_pendingItems.isEmpty)
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: isDark ? AppColors.darkSurface : AppColors.surface,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: isDark ? AppColors.darkBorder : AppColors.border),
                ),
                child: Column(
                  children: const [
                    Icon(Icons.cloud_done_outlined, size: 40, color: AppColors.statusCompleted),
                    SizedBox(height: 10),
                    Text(
                      'Semua data telah tersinkronisasi ke server!',
                      style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                    ),
                    SizedBox(height: 4),
                    Text(
                      'Tidak ada perubahan lokal yang tertunda di antrean.',
                      style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
                    ),
                  ],
                ),
              )
            else
              ListView.separated(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: _pendingItems.length,
                separatorBuilder: (_, __) => const SizedBox(height: 8),
                itemBuilder: (ctx, i) {
                  final item = _pendingItems[i];
                  return Card(
                    child: ListTile(
                      leading: Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: AppColors.bgHold,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: const Icon(Icons.outbox_rounded, color: AppColors.statusHold, size: 20),
                      ),
                      title: Text(
                        item.actionTitle,
                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
                      ),
                      subtitle: Text(
                        'WO ID: ${item.workOrderId} • Dibuat: ${Formatters.timeAgo(item.createdAt)}',
                        style: const TextStyle(fontSize: 11),
                      ),
                      trailing: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: AppColors.bgHold,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Text(
                          'Tertunda',
                          style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: Color(0xFFB45309)),
                        ),
                      ),
                    ),
                  );
                },
              ),

            const SizedBox(height: 28),

            // How it works info card
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: isDark ? AppColors.darkSurfaceVariant : AppColors.surfaceVariant,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: const [
                  Text(
                    'Cara Kerja Mode Offline:',
                    style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
                  ),
                  SizedBox(height: 8),
                  Text(
                    '1. Tekan "Sinkronkan Sekarang" saat di kantor untuk mengunduh penugasan WO terbaru.\n'
                    '2. Di lapangan (basement, ruang mesin, luar kota), Anda dapat mengerjakan tugas, mencentang prosedur, mengambil foto, dan mengisi checklist tanpa sinyal.\n'
                    '3. Begitu HP Anda kembali terhubung ke internet/WiFi, aplikasi akan otomatis mengirimkan hasil pekerjaan Anda ke server.',
                    style: TextStyle(fontSize: 12, height: 1.4, color: AppColors.textSecondary),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
