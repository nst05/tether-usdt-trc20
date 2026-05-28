import 'package:flutter/material.dart';
import '../../core/models/vpn_status.dart';
import '../theme/app_theme.dart';

class StatsCard extends StatelessWidget {
  final VpnStatus status;

  const StatsCard({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 24),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        children: [
          // Duration
          if (status.isConnected) ...[
            _buildDurationRow(),
            const Divider(height: 24, color: AppColors.border),
          ],
          // Speed row
          Row(
            children: [
              Expanded(
                child: _buildStatItem(
                  icon: Icons.arrow_upward_rounded,
                  color: AppColors.primary,
                  label: 'Исходящий',
                  value: status.uploadSpeedFormatted,
                  sub: status.totalUploadFormatted,
                ),
              ),
              Container(width: 1, height: 60, color: AppColors.border),
              Expanded(
                child: _buildStatItem(
                  icon: Icons.arrow_downward_rounded,
                  color: AppColors.connected,
                  label: 'Входящий',
                  value: status.downloadSpeedFormatted,
                  sub: status.totalDownloadFormatted,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildDurationRow() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Icon(Icons.timer_outlined, size: 16, color: AppColors.textSecondary),
        const SizedBox(width: 6),
        Text(
          status.durationFormatted,
          style: const TextStyle(
            color: AppColors.textPrimary,
            fontSize: 22,
            fontWeight: FontWeight.w700,
            fontFeatures: [FontFeature.tabularFigures()],
          ),
        ),
        const SizedBox(width: 8),
        const Text(
          'онлайн',
          style: TextStyle(color: AppColors.textSecondary, fontSize: 14),
        ),
      ],
    );
  }

  Widget _buildStatItem({
    required IconData icon,
    required Color color,
    required String label,
    required String value,
    required String sub,
  }) {
    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 14, color: color),
            const SizedBox(width: 4),
            Text(label,
                style: const TextStyle(
                    color: AppColors.textSecondary, fontSize: 11)),
          ],
        ),
        const SizedBox(height: 6),
        Text(
          value,
          style: const TextStyle(
            color: AppColors.textPrimary,
            fontSize: 18,
            fontWeight: FontWeight.w700,
            fontFeatures: [FontFeature.tabularFigures()],
          ),
        ),
        Text(
          sub,
          style: const TextStyle(color: AppColors.textMuted, fontSize: 11),
        ),
      ],
    );
  }
}
