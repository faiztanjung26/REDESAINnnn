import 'package:flutter/material.dart';
import '../core/constants/app_colors.dart';

class StatusBadge extends StatelessWidget {
  final String status;
  final bool isSmall;

  const StatusBadge({
    Key? key,
    required this.status,
    this.isSmall = false,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    Color bg;
    Color fg;
    String label = status;

    switch (status) {
      case 'Draft':
        bg = AppColors.bgDraft;
        fg = AppColors.statusDraft;
        label = 'Draf';
        break;
      case 'Assigned':
      case 'Confirmed':
        bg = AppColors.bgAssigned;
        fg = AppColors.statusAssigned;
        label = 'Ditugaskan';
        break;
      case 'In Progress':
        bg = AppColors.bgInProgress;
        fg = AppColors.statusInProgress;
        label = 'Dikerjakan';
        break;
      case 'Hold':
        bg = AppColors.bgHold;
        fg = AppColors.statusHold;
        label = 'Ditunda';
        break;
      case 'Solved':
        bg = AppColors.bgSolved;
        fg = AppColors.statusSolved;
        label = 'Selesai Teknisi';
        break;
      case 'Completed':
      case 'Closed':
        bg = AppColors.bgCompleted;
        fg = AppColors.statusCompleted;
        label = 'Ditutup';
        break;
      default:
        bg = AppColors.surfaceVariant;
        fg = AppColors.textSecondary;
        label = status;
    }

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: isSmall ? 8 : 12,
        vertical: isSmall ? 3 : 5,
      ),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: fg.withOpacity(0.3), width: 1),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: fg,
          fontSize: isSmall ? 11 : 12,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.1,
        ),
      ),
    );
  }
}
