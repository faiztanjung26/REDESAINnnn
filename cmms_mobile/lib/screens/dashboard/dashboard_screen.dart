import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/constants/app_colors.dart';
import '../../providers/auth_provider.dart';
import '../../providers/dashboard_provider.dart';
import '../../providers/sync_provider.dart';
import '../../providers/work_order_provider.dart';
import '../../widgets/stat_card.dart';
import '../../widgets/work_order_card.dart';
import '../work_orders/work_order_detail_screen.dart';

class DashboardScreen extends StatefulWidget {
  final Function(int) onTabChange;

  const DashboardScreen({Key? key, required this.onTabChange}) : super(key: key);

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadData();
    });
  }

  Future<void> _loadData() async {
    final dashProv = Provider.of<DashboardProvider>(context, listen: false);
    await dashProv.loadDashboard();
  }

  @override
  Widget build(BuildContext context) {
    final authProv = Provider.of<AuthProvider>(context);
    final dashProv = Provider.of<DashboardProvider>(context);
    final syncProv = Provider.of<SyncProvider>(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final user = authProv.user;
    final data = dashProv.data;
    final metrics = data?.metrics;

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _loadData,
        color: AppColors.primary,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            // Sliver App Bar Header
            SliverAppBar(
              floating: true,
              pinned: true,
              elevation: 0,
              backgroundColor: isDark ? AppColors.darkSurface : AppColors.surface,
              title: Row(
                children: [
                  Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      color: AppColors.primary.withOpacity(0.12),
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(Icons.person, color: AppColors.primary, size: 20),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          user?.name ?? 'Teknisi',
                          style: TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                            color: isDark ? AppColors.darkTextPrimary : AppColors.textPrimary,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        Text(
                          '${user?.role ?? 'Teknisi'} • ${user?.siteName ?? 'Site'}',
                          style: const TextStyle(
                            fontSize: 11,
                            color: AppColors.textSecondary,
                            fontWeight: FontWeight.w500,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  // Online / Offline Status Chip
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: syncProv.isOnline ? AppColors.bgCompleted : AppColors.bgOverdue,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          width: 7,
                          height: 7,
                          decoration: BoxDecoration(
                            color: syncProv.isOnline ? AppColors.statusCompleted : AppColors.statusOverdue,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 5),
                        Text(
                          syncProv.isOnline ? 'Online' : 'Offline',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: syncProv.isOnline ? AppColors.statusCompleted : AppColors.statusOverdue,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            // Dashboard Content Body
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
              sliver: SliverList(
                delegate: SliverChildListDelegate([
                  // Sync Notice Banner if pending
                  if (syncProv.pendingCount > 0) ...[
                    InkWell(
                      onTap: () => widget.onTabChange(2), // Switch to Sync tab
                      child: Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: AppColors.bgInProgress,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: AppColors.primary.withOpacity(0.3)),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.cloud_upload_rounded, color: AppColors.primary, size: 22),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    '${syncProv.pendingCount} Perubahan Tersimpan Offline',
                                    style: const TextStyle(
                                      fontSize: 13,
                                      fontWeight: FontWeight.w700,
                                      color: AppColors.primary,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  const Text(
                                    'Ketuk untuk memeriksa dan menyinkronkan data ke server.',
                                    style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
                                  ),
                                ],
                              ),
                            ),
                            const Icon(Icons.chevron_right, color: AppColors.primary),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],

                  // KPI Statistics Grid
                  const Text(
                    'Ringkasan Penugasan',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, letterSpacing: -0.3),
                  ),
                  const SizedBox(height: 12),
                  GridView.count(
                    crossAxisCount: 2,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    mainAxisSpacing: 12,
                    crossAxisSpacing: 12,
                    childAspectRatio: 1.5,
                    children: [
                      StatCard(
                        label: 'Ditugaskan',
                        value: '${metrics?.assigned ?? 0}',
                        icon: Icons.assignment_outlined,
                        color: AppColors.statusAssigned,
                        onTap: () {
                          Provider.of<WorkOrderProvider>(context, listen: false).setStatusFilter('assigned');
                          widget.onTabChange(1);
                        },
                      ),
                      StatCard(
                        label: 'Sedang Dikerjakan',
                        value: '${metrics?.inProgress ?? 0}',
                        icon: Icons.play_circle_outline,
                        color: AppColors.statusInProgress,
                        onTap: () {
                          Provider.of<WorkOrderProvider>(context, listen: false).setStatusFilter('in_progress');
                          widget.onTabChange(1);
                        },
                      ),
                      StatCard(
                        label: 'Ditunda (Hold)',
                        value: '${metrics?.hold ?? 0}',
                        icon: Icons.pause_circle_outline,
                        color: AppColors.statusHold,
                        onTap: () {
                          Provider.of<WorkOrderProvider>(context, listen: false).setStatusFilter('hold');
                          widget.onTabChange(1);
                        },
                      ),
                      StatCard(
                        label: 'Terlambat (Overdue)',
                        value: '${metrics?.overdue ?? 0}',
                        icon: Icons.error_outline_rounded,
                        color: AppColors.statusOverdue,
                        onTap: () {
                          widget.onTabChange(1);
                        },
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),

                  // Today's Work Orders Section
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'Work Order Hari Ini',
                        style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, letterSpacing: -0.3),
                      ),
                      TextButton(
                        onPressed: () => widget.onTabChange(1),
                        child: const Text('Lihat Semua', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),

                  if (dashProv.isLoading)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(child: CircularProgressIndicator()),
                    )
                  else if (data == null || data.todayWorkOrders.isEmpty)
                    Container(
                      padding: const EdgeInsets.symmetric(vertical: 24),
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: isDark ? AppColors.darkSurface : AppColors.surface,
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: isDark ? AppColors.darkBorder : AppColors.border),
                      ),
                      child: Column(
                        children: const [
                          Icon(Icons.event_available_outlined, size: 36, color: AppColors.statusCompleted),
                          SizedBox(height: 8),
                          Text(
                            'Tidak ada jadwal WO yang jatuh tempo hari ini.',
                            style: TextStyle(fontSize: 13, color: AppColors.textSecondary, fontWeight: FontWeight.w500),
                          ),
                        ],
                      ),
                    )
                  else
                    ListView.separated(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: data.todayWorkOrders.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 10),
                      itemBuilder: (ctx, i) {
                        final wo = data.todayWorkOrders[i];
                        return WorkOrderCard(
                          workOrder: wo,
                          onTap: () {
                            Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) => WorkOrderDetailScreen(workOrderId: wo.id),
                              ),
                            );
                          },
                        );
                      },
                    ),

                  const SizedBox(height: 24),

                  // Urgent Work Orders Section
                  if (data != null && data.urgentWorkOrders.isNotEmpty) ...[
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: const [
                        Text(
                          'Pekerjaan Mendesak / Prioritas',
                          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, letterSpacing: -0.3),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    ListView.separated(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: data.urgentWorkOrders.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 10),
                      itemBuilder: (ctx, i) {
                        final wo = data.urgentWorkOrders[i];
                        return WorkOrderCard(
                          workOrder: wo,
                          onTap: () {
                            Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) => WorkOrderDetailScreen(workOrderId: wo.id),
                              ),
                            );
                          },
                        );
                      },
                    ),
                    const SizedBox(height: 20),
                  ],
                ]),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
