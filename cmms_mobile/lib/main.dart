import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:provider/provider.dart';

import 'core/constants/app_theme.dart';
import 'core/database/database_helper.dart';
import 'core/network/api_service.dart';
import 'core/network/network_info.dart';
import 'providers/auth_provider.dart';
import 'providers/dashboard_provider.dart';
import 'providers/work_order_provider.dart';
import 'providers/sync_provider.dart';
import 'providers/theme_provider.dart';
import 'screens/splash_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Initialize Core Services safely
  try {
    await ApiService.instance.init();
    await NetworkInfo.instance.init();
    await DatabaseHelper.instance.database;
  } catch (e, stack) {
    debugPrint('Init core services warning: $e\n$stack');
  }

  // Initialize Providers
  final themeProvider = ThemeProvider();
  try {
    await themeProvider.init();
  } catch (_) {}

  final syncProvider = SyncProvider();
  try {
    await syncProvider.init();
  } catch (_) {}

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: themeProvider),
        ChangeNotifierProvider.value(value: syncProvider),
        ChangeNotifierProvider(create: (_) => AuthProvider()),
        ChangeNotifierProvider(create: (_) => DashboardProvider()),
        ChangeNotifierProvider(create: (_) => WorkOrderProvider()),
      ],
      child: const CmmsApp(),
    ),
  );
}

class CmmsApp extends StatelessWidget {
  const CmmsApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    final themeProv = Provider.of<ThemeProvider>(context);

    return MaterialApp(
      title: 'CMMS Teknisi',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: themeProv.isDarkMode ? ThemeMode.dark : ThemeMode.light,
      locale: const Locale('id', 'ID'),
      supportedLocales: const [
        Locale('id', 'ID'),
        Locale('en', 'US'),
      ],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      home: const SplashScreen(),
    );
  }
}
