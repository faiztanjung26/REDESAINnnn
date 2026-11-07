import 'package:flutter/material.dart';
import '../core/constants/app_colors.dart';

class PriorityBadge extends StatelessWidget {
  final String priority;

  const PriorityBadge({Key? key, required this.priority}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    Color color;
    String label = priority;

    switch (priority) {
      case 'Highest':
        color = AppColors.priorityHighest;
        label = 'Tertinggi';
        break;
      case 'High':
        color = AppColors.priorityHigh;
        label = 'Tinggi';
        break;
      case 'Medium':
        color = AppColors.priorityMedium;
        label = 'Sedang';
        break;
      case 'Low':
        color = AppColors.priorityLow;
        label = 'Rendah';
        break;
      default:
        color = AppColors.textMuted;
        label = priority;
    }

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle,
          ),
        ),
        const SizedBox(width: 5),
        Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: color,
          ),
        ),
      ],
    );
  }
}
