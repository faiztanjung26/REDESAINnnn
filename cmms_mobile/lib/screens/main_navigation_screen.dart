import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/constants/app_colors.dart';
import '../providers/sync_provider.dart';
import '../widgets/connection_banner.dart';
import 'dashboard/dashboard_screen.dart';
import 'work_orders/work_orders_screen.dart';
import 'sync/sync_screen.dart';
import 'profile/profile_screen.dart';

class MainNavigationScreen extends StatefulWidget {
  const MainNavigationScreen({Key? key}) : super(key: key);

  @override
  State<MainNavigationScreen> createState() => _MainNavigationScreenState();
}

class _MainNavigationScreenState extends State<MainNavigationScreen> {
  int _currentIndex = 0;

  void _onTabTapped(int index) {
    setState(() => _currentIndex = index);
  }

  @override
  Widget build(BuildContext context) {
    final syncProv = Provider.of<SyncProvider>(context);

    final List<Widget> screens = [
      DashboardScreen(onTabChange: _onTabTapped),
      const WorkOrdersScreen(),
      const SyncScreen(),
      const ProfileScreen(),
    ];

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // Connectivity Banner (Online/Offline/Syncing status)
            const ConnectionBanner(),

            // Active Screen Content
            Expanded(
              child: IndexedStack(
                index: _currentIndex,
                children: screens,
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _currentIndex,
        onDestinationSelected: _onTabTapped,
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard, color: AppColors.primary),
            label: 'Beranda',
          ),
          const NavigationDestination(
            icon: Icon(Icons.assignment_outlined),
            selectedIcon: Icon(Icons.assignment, color: AppColors.primary),
            label: 'Work Order',
          ),
          NavigationDestination(
            icon: syncProv.pendingCount > 0
                ? Badge(
                    label: Text('${syncProv.pendingCount}'),
                    backgroundColor: AppColors.statusHold,
                    child: const Icon(Icons.sync),
                  )
                : const Icon(Icons.sync),
            selectedIcon: const Icon(Icons.sync, color: AppColors.primary),
            label: 'Sinkronisasi',
          ),
          const NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person, color: AppColors.primary),
            label: 'Profil',
          ),
        ],
      ),
    );
  }
}
