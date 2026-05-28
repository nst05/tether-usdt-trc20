import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../core/models/server.dart';
import '../../core/models/vpn_status.dart';
import '../theme/app_theme.dart';

class ServerTile extends StatelessWidget {
  final VlessServer server;
  final bool isSelected;
  final bool isConnected;
  final VoidCallback onTap;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  final VoidCallback onTestPing;
  final VoidCallback onToggleFavorite;
  final VoidCallback? onConnect;

  const ServerTile({
    super.key,
    required this.server,
    required this.isSelected,
    required this.isConnected,
    required this.onTap,
    required this.onEdit,
    required this.onDelete,
    required this.onTestPing,
    required this.onToggleFavorite,
    this.onConnect,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        decoration: BoxDecoration(
          color: isSelected
              ? AppColors.primary.withOpacity(0.08)
              : AppColors.card,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected ? AppColors.primary : AppColors.border,
            width: isSelected ? 1.5 : 1,
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            children: [
              // Status indicator
              _buildStatusDot(),
              const SizedBox(width: 12),

              // Server info
              Expanded(child: _buildInfo()),

              // Ping badge
              _buildPingBadge(),
              const SizedBox(width: 8),

              // Menu
              _buildMenu(context),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStatusDot() {
    final color = isConnected
        ? AppColors.connected
        : isSelected
            ? AppColors.primary
            : AppColors.textMuted;

    return Container(
      width: 10,
      height: 10,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: color,
        boxShadow: isConnected
            ? [
                BoxShadow(
                  color: AppColors.connected.withOpacity(0.5),
                  blurRadius: 6,
                  spreadRadius: 1,
                )
              ]
            : null,
      ),
    );
  }

  Widget _buildInfo() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                server.displayName,
                style: TextStyle(
                  color: isSelected
                      ? AppColors.primary
                      : AppColors.textPrimary,
                  fontWeight: FontWeight.w600,
                  fontSize: 14,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (server.isFavorite)
              const Padding(
                padding: EdgeInsets.only(left: 4),
                child: Icon(Icons.star_rounded,
                    size: 14, color: AppColors.connecting),
              ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          '${server.address}:${server.port}',
          style: const TextStyle(
              color: AppColors.textSecondary, fontSize: 12),
          overflow: TextOverflow.ellipsis,
        ),
        const SizedBox(height: 2),
        Row(
          children: [
            _buildChip(server.networkLabel),
            const SizedBox(width: 4),
            _buildChip(server.securityLabel),
          ],
        ),
      ],
    );
  }

  Widget _buildChip(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: AppColors.border.withOpacity(0.5),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        label,
        style: const TextStyle(
            color: AppColors.textMuted,
            fontSize: 10,
            fontWeight: FontWeight.w500),
      ),
    );
  }

  Widget _buildPingBadge() {
    if (server.ping == null) {
      return const SizedBox.shrink();
    }

    Color color;
    if (server.ping! < 100) {
      color = AppColors.connected;
    } else if (server.ping! < 300) {
      color = AppColors.connecting;
    } else {
      color = AppColors.error;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Text(
        '${server.ping}ms',
        style: TextStyle(
            color: color, fontSize: 11, fontWeight: FontWeight.w600),
      ),
    );
  }

  Widget _buildMenu(BuildContext context) {
    return PopupMenuButton<String>(
      icon: const Icon(Icons.more_vert_rounded,
          color: AppColors.textSecondary, size: 20),
      color: AppColors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: const BorderSide(color: AppColors.border),
      ),
      itemBuilder: (_) => [
        if (onConnect != null)
          const PopupMenuItem(
            value: 'connect',
            child: _MenuItem(
                icon: Icons.power_settings_new_rounded,
                label: 'Подключиться'),
          ),
        const PopupMenuItem(
          value: 'ping',
          child: _MenuItem(icon: Icons.network_ping, label: 'Проверить пинг'),
        ),
        const PopupMenuItem(
          value: 'favorite',
          child: _MenuItem(icon: Icons.star_border_rounded, label: 'Избранное'),
        ),
        const PopupMenuItem(
          value: 'copy',
          child: _MenuItem(
              icon: Icons.copy_rounded, label: 'Копировать ссылку'),
        ),
        const PopupMenuItem(
          value: 'edit',
          child: _MenuItem(icon: Icons.edit_rounded, label: 'Изменить'),
        ),
        const PopupMenuDivider(),
        const PopupMenuItem(
          value: 'delete',
          child: _MenuItem(
            icon: Icons.delete_outline_rounded,
            label: 'Удалить',
            color: AppColors.error,
          ),
        ),
      ],
      onSelected: (value) async {
        switch (value) {
          case 'connect':
            onConnect?.call();
            break;
          case 'ping':
            onTestPing();
            break;
          case 'favorite':
            onToggleFavorite();
            break;
          case 'copy':
            // Copy vless:// URI to clipboard
            await Clipboard.setData(
              ClipboardData(text: _buildVlessUri()),
            );
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Ссылка скопирована')),
              );
            }
            break;
          case 'edit':
            onEdit();
            break;
          case 'delete':
            _confirmDelete(context);
            break;
        }
      },
    );
  }

  String _buildVlessUri() {
    final params = <String, String>{};
    params['type'] = server.network.name;
    params['security'] = server.security.name;
    if (server.sni != null) params['sni'] = server.sni!;
    if (server.path != null) params['path'] = server.path!;
    final query = params.entries.map((e) => '${e.key}=${e.value}').join('&');
    final name = Uri.encodeComponent(server.name);
    return 'vless://${server.uuid}@${server.address}:${server.port}?$query#$name';
  }

  void _confirmDelete(BuildContext context) {
    showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: const BorderSide(color: AppColors.border),
        ),
        title: const Text('Удалить сервер?',
            style: TextStyle(color: AppColors.textPrimary)),
        content: Text(
          'Сервер "${server.displayName}" будет удалён безвозвратно.',
          style: const TextStyle(color: AppColors.textSecondary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Отмена',
                style: TextStyle(color: AppColors.textSecondary)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.error,
            ),
            onPressed: () {
              Navigator.pop(ctx);
              onDelete();
            },
            child: const Text('Удалить'),
          ),
        ],
      ),
    );
  }
}

class _MenuItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;

  const _MenuItem({
    required this.icon,
    required this.label,
    this.color = AppColors.textPrimary,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(width: 12),
        Text(label, style: TextStyle(color: color, fontSize: 14)),
      ],
    );
  }
}
