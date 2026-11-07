import 'package:flutter/material.dart';

class AppColors {
  // Primary Palette
  static const Color primary = Color(0xFF1E40AF); // Deep Indigo
  static const Color primaryLight = Color(0xFF3B82F6);
  static const Color primaryDark = Color(0xFF1E3A8A);
  
  // Secondary / Accent
  static const Color secondary = Color(0xFF0EA5E9); // Sky
  static const Color accent = Color(0xFF6366F1); // Indigo-violet
  
  // Neutral Surfaces (Light)
  static const Color background = Color(0xFFF8FAFC);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color surfaceVariant = Color(0xFFF1F5F9);
  
  // Borders & Dividers
  static const Color border = Color(0xFFE2E8F0);
  static const Color borderLight = Color(0xFFF1F5F9);
  
  // Text Colors
  static const Color textPrimary = Color(0xFF0F172A);
  static const Color textSecondary = Color(0xFF64748B);
  static const Color textMuted = Color(0xFF94A3B8);
  static const Color textOnPrimary = Colors.white;

  // Status Colors
  static const Color statusDraft = Color(0xFF94A3B8);
  static const Color statusAssigned = Color(0xFF0EA5E9);
  static const Color statusInProgress = Color(0xFF2563EB);
  static const Color statusHold = Color(0xFFF59E0B);
  static const Color statusSolved = Color(0xFF8B5CF6);
  static const Color statusCompleted = Color(0xFF10B981);
  static const Color statusOverdue = Color(0xFFEF4444);

  // Status Backgrounds (Soft tints for chips)
  static const Color bgDraft = Color(0xFFF1F5F9);
  static const Color bgAssigned = Color(0xFFE0F2FE);
  static const Color bgInProgress = Color(0xFFDBEAFE);
  static const Color bgHold = Color(0xFFFEF3C7);
  static const Color bgSolved = Color(0xFFEDE9FE);
  static const Color bgCompleted = Color(0xFFD1FAE5);
  static const Color bgOverdue = Color(0xFFFEE2E2);

  // Priority Colors
  static const Color priorityHighest = Color(0xFFDC2626);
  static const Color priorityHigh = Color(0xFFEA580C);
  static const Color priorityMedium = Color(0xFF2563EB);
  static const Color priorityLow = Color(0xFF10B981);

  // Offline / Online Indicator
  static const Color online = Color(0xFF10B981);
  static const Color offline = Color(0xFFEF4444);
  static const Color syncing = Color(0xFFF59E0B);

  // Dark Theme Colors
  static const Color darkBackground = Color(0xFF0B1120);
  static const Color darkSurface = Color(0xFF1E293B);
  static const Color darkSurfaceVariant = Color(0xFF334155);
  static const Color darkBorder = Color(0xFF334155);
  static const Color darkTextPrimary = Color(0xFFF8FAFC);
  static const Color darkTextSecondary = Color(0xFF94A3B8);
}
