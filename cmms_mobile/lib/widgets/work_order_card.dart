import 'package:flutter/material.dart';
import '../core/constants/app_colors.dart';
import '../core/utils/formatters.dart';
import '../data/models/work_order_model.dart';
import 'status_badge.dart';
import 'priority_badge.dart';

class WorkOrderCard extends StatelessWidget {
  final WorkOrderModel workOrder;
  final VoidCallback onTap;

  const WorkOrderCard({
    Key? key,
    required this.workOrder,
    required this.onTap,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: isDark ? AppColors.darkSurface : AppColors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: workOrder.isOverdue
                ? AppColors.statusOverdue.withOpacity(0.5)
                : (isDark ? AppColors.darkBorder : AppColors.border),
            width: workOrder.isOverdue ? 1.5 : 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.02),
              blurRadius: 10,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Top Row: Code, Priority, Status
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Row(
                  children: [
                    Text(
                      workOrder.code,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w800,
                        color: isDark ? AppColors.darkTextPrimary : AppColors.primary,
                        letterSpacing: -0.2,
                      ),
                    ),
                    const SizedBox(width: 8),
                    PriorityBadge(priority: workOrder.priority),
                  ],
                ),
                StatusBadge(status: workOrder.status, isSmall: true),
              ],
            ),
            const SizedBox(height: 10),

            // Description
            Text(
              workOrder.description,
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: isDark ? AppColors.darkTextPrimary : AppColors.textPrimary,
                height: 1.3,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            const SizedBox(height: 12),

            // Asset & Location
            Row(
              children: [
                const Icon(
                  Icons.build_circle_outlined,
                  size: 15,
                  color: AppColors.textSecondary,
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    workOrder.assetName,
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: AppColors.textSecondary,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                const Icon(
                  Icons.location_on_outlined,
                  size: 15,
                  color: AppColors.textSecondary,
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    workOrder.assetLocation,
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: AppColors.textSecondary,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),

            const Divider(height: 1, color: AppColors.border),
            const SizedBox(height: 10),

            // Bottom Footer: Target Date & Procedure Progress
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                // Target Date
                Row(
                  children: [
                    Icon(
                      Icons.schedule_rounded,
                      size: 14,
                      color: workOrder.isOverdue ? AppColors.statusOverdue : AppColors.textMuted,
                    ),
                    const SizedBox(width: 5),
                    Text(
                      workOrder.suggestedCompletionDate != null
                          ? Formatters.formatDateShort(workOrder.suggestedCompletionDate)
                          : 'Fleksibel',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: workOrder.isOverdue ? FontWeight.w700 : FontWeight.w500,
                        color: workOrder.isOverdue ? AppColors.statusOverdue : AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),

                // Procedure Progress
                if (workOrder.proceduresCount > 0)
                  Row(
                    children: [
                      Text(
                        '${workOrder.proceduresCompletedCount}/${workOrder.proceduresCount} Selesai',
                        style: const TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: AppColors.primary,
                        ),
                      ),
                      const SizedBox(width: 6),
                      SizedBox(
                        width: 40,
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(4),
                          child: LinearProgressIndicator(
                            value: workOrder.proceduresCount > 0
                                ? (workOrder.proceduresCompletedCount / workOrder.proceduresCount)
                                : 0,
                            minHeight: 5,
                            backgroundColor: AppColors.bgInProgress,
                            valueColor: const AlwaysStoppedAnimation<Color>(AppColors.primary),
                          ),
                        ),
                      ),
                    ],
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
