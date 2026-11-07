import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/constants/app_colors.dart';
import '../../providers/work_order_provider.dart';
import '../../widgets/work_order_card.dart';
import '../../widgets/empty_state.dart';
import 'work_order_detail_screen.dart';

class WorkOrdersScreen extends StatefulWidget {
  const WorkOrdersScreen({Key? key}) : super(key: key);

  @override
  State<WorkOrdersScreen> createState() => _WorkOrdersScreenState();
}

class _WorkOrdersScreenState extends State<WorkOrdersScreen> {
  final TextEditingController _searchController = TextEditingController();

  final List<Map<String, String>> _statusTabs = [
    {'key': 'all', 'label': 'Semua'},
    {'key': 'assigned', 'label': 'Ditugaskan'},
    {'key': 'in_progress', 'label': 'Dikerjakan'},
    {'key': 'hold', 'label': 'Ditunda'},
    {'key': 'solved', 'label': 'Selesai'},
  ];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Provider.of<WorkOrderProvider>(context, listen: false).loadWorkOrders();
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final woProv = Provider.of<WorkOrderProvider>(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Daftar Work Order'),
        actions: [
          PopupMenuButton<String>(
            icon: const Icon(Icons.filter_list_rounded),
            tooltip: 'Filter Prioritas',
            onSelected: (val) => woProv.setPriorityFilter(val),
            itemBuilder: (ctx) => [
              'Semua',
              'Highest',
              'High',
              'Medium',
              'Low',
            ].map((p) {
              return PopupMenuItem(
                value: p,
                child: Row(
                  children: [
                    if (woProv.priorityFilter == p)
                      const Icon(Icons.check, size: 16, color: AppColors.primary)
                    else
                      const SizedBox(width: 16),
                    const SizedBox(width: 8),
                    Text(p == 'Semua' ? 'Semua Prioritas' : p),
                  ],
                ),
              );
            }).toList(),
          ),
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Perbarui Data',
            onPressed: () => woProv.loadWorkOrders(forceRefresh: true),
          ),
        ],
      ),
      body: Column(
        children: [
          // Search Input Bar
          Container(
            color: isDark ? AppColors.darkSurface : AppColors.surface,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: TextField(
              controller: _searchController,
              onChanged: (val) => woProv.setSearchQuery(val),
              decoration: InputDecoration(
                hintText: 'Cari kode, deskripsi, atau aset...',
                prefixIcon: const Icon(Icons.search, size: 20),
                suffixIcon: _searchController.text.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear, size: 18),
                        onPressed: () {
                          _searchController.clear();
                          woProv.setSearchQuery('');
                        },
                      )
                    : null,
                contentPadding: const EdgeInsets.symmetric(vertical: 10),
                filled: true,
                fillColor: isDark ? AppColors.darkSurfaceVariant : AppColors.surfaceVariant,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide.none,
                ),
              ),
            ),
          ),

          // Horizontal Status Filter Tabs
          Container(
            color: isDark ? AppColors.darkSurface : AppColors.surface,
            height: 48,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              itemCount: _statusTabs.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (ctx, i) {
                final tab = _statusTabs[i];
                final isSelected = woProv.statusFilter == tab['key'];

                return ChoiceChip(
                  label: Text(tab['label']!),
                  selected: isSelected,
                  onSelected: (_) => woProv.setStatusFilter(tab['key']!),
                  labelStyle: TextStyle(
                    fontSize: 12,
                    fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                    color: isSelected ? Colors.white : (isDark ? AppColors.darkTextPrimary : AppColors.textPrimary),
                  ),
                  selectedColor: AppColors.primary,
                  backgroundColor: isDark ? AppColors.darkSurfaceVariant : AppColors.surfaceVariant,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
                  side: BorderSide.none,
                );
              },
            ),
          ),

          const Divider(height: 1, color: AppColors.border),

          // Work Order List
          Expanded(
            child: woProv.isLoading
                ? const Center(child: CircularProgressIndicator())
                : woProv.workOrders.isEmpty
                    ? EmptyState(
                        icon: Icons.assignment_outlined,
                        title: 'Tidak Ada Work Order',
                        subtitle: 'Tidak ditemukan penugasan yang sesuai dengan filter yang Anda pilih.',
                        buttonText: 'Muat Ulang',
                        onButtonPressed: () => woProv.loadWorkOrders(forceRefresh: true),
                      )
                    : RefreshIndicator(
                        onRefresh: () => woProv.loadWorkOrders(forceRefresh: true),
                        color: AppColors.primary,
                        child: ListView.separated(
                          padding: const EdgeInsets.all(16),
                          itemCount: woProv.workOrders.length,
                          separatorBuilder: (_, __) => const SizedBox(height: 12),
                          itemBuilder: (ctx, index) {
                            final wo = woProv.workOrders[index];
                            return WorkOrderCard(
                              workOrder: wo,
                              onTap: () {
                                Navigator.of(context).push(
                                  MaterialPageRoute(
                                    builder: (_) => WorkOrderDetailScreen(workOrderId: wo.id),
                                  ),
                                ).then((_) => woProv.loadWorkOrders());
                              },
                            );
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }
}
