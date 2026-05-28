import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:provider/provider.dart';
import '../../core/models/vpn_status.dart';
import '../../core/providers/vpn_provider.dart';
import '../theme/app_theme.dart';
import '../widgets/connection_button.dart';
import '../widgets/stats_card.dart';
import 'servers_screen.dart';
import 'settings_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _currentIndex = 0;

  final _pages = const [
    _ConnectTab(),
    ServersScreen(),
    SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _currentIndex,
        children: _pages,
      ),
      bottomNavigationBar: _buildNavBar(),
    );
  }

  Widget _buildNavBar() {
    return Container(
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (i) => setState(() => _currentIndex = i),
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.shield_outlined),
            activeIcon: Icon(Icons.shield_rounded),
            label: 'VPN',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.dns_outlined),
            activeIcon: Icon(Icons.dns_rounded),
            label: 'Серверы',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.settings_outlined),
            activeIcon: Icon(Icons.settings_rounded),
            label: 'Настройки',
          ),
        ],
      ),
    );
  }
}

class _ConnectTab extends StatelessWidget {
  const _ConnectTab();

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<VpnProvider>();
    final status = provider.status;
    final server = provider.selectedServer;

    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        title: const Row(
          children: [
            Icon(Icons.shield_rounded, color: AppColors.primary, size: 22),
            SizedBox(width: 8),
            Text('VPN'),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Проверить все пинги',
            onPressed: provider.testAllDelays,
          ),
        ],
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          child: Column(
            children: [
              const SizedBox(height: 32),

              // Status label
              _StatusBadge(status: status)
                  .animate()
                  .fadeIn(duration: 400.ms),

              const SizedBox(height: 40),

              // Big connect button
              ConnectionButton(
                status: status,
                onTap: () => _handleConnect(context, provider),
              )
                  .animate()
                  .fadeIn(duration: 500.ms, delay: 100.ms)
                  .scale(begin: const Offset(0.8, 0.8)),

              const SizedBox(height: 40),

              // Selected server card
              if (server != null) _SelectedServerCard(server: server)
                  .animate()
                  .fadeIn(duration: 400.ms, delay: 200.ms),

              if (server == null) _NoServerHint()
                  .animate()
                  .fadeIn(duration: 400.ms, delay: 200.ms),

              const SizedBox(height: 24),

              // Stats
              if (status.isConnected || status.totalDownload != null)
                StatsCard(status: status)
                    .animate()
                    .fadeIn(duration: 400.ms, delay: 300.ms),

              if (!status.isConnected && status.totalDownload == null)
                _PlaceholderStats()
                    .animate()
                    .fadeIn(duration: 400.ms, delay: 300.ms),

              const SizedBox(height: 32),
            ],
          ),
        ),
      ),
    );
  }

  void _handleConnect(BuildContext context, VpnProvider provider) async {
    if (provider.selectedServer == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Сначала добавьте и выберите сервер')),
      );
      return;
    }
    await provider.toggleConnection();
  }
}

class _StatusBadge extends StatelessWidget {
  final VpnStatus status;
  const _StatusBadge({required this.status});

  @override
  Widget build(BuildContext context) {
    Color color;
    Color bgColor;
    switch (status.state) {
      case VpnState.connected:
        color = AppColors.connected;
        bgColor = AppColors.connected.withOpacity(0.12);
        break;
      case VpnState.connecting:
      case VpnState.disconnecting:
        color = AppColors.connecting;
        bgColor = AppColors.connecting.withOpacity(0.12);
        break;
      case VpnState.error:
        color = AppColors.error;
        bgColor = AppColors.error.withOpacity(0.12);
        break;
      case VpnState.disconnected:
        color = AppColors.textSecondary;
        bgColor = AppColors.textSecondary.withOpacity(0.08);
        break;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            status.stateLabel,
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.w600,
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }
}

class _SelectedServerCard extends StatelessWidget {
  final server;
  const _SelectedServerCard({required this.server});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 24),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.primary.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          const Icon(Icons.dns_rounded,
              color: AppColors.primary, size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  server.displayName,
                  style: const TextStyle(
                    color: AppColors.textPrimary,
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                  ),
                ),
                Text(
                  '${server.address}:${server.port}  •  ${server.networkLabel}  •  ${server.securityLabel}',
                  style: const TextStyle(
                      color: AppColors.textSecondary, fontSize: 12),
                ),
              ],
            ),
          ),
          const Icon(Icons.check_circle_rounded,
              color: AppColors.primary, size: 18),
        ],
      ),
    );
  }
}

class _NoServerHint extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 24),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        children: [
          const Icon(Icons.add_circle_outline_rounded,
              color: AppColors.textMuted, size: 40),
          const SizedBox(height: 12),
          const Text(
            'Серверы не добавлены',
            style: TextStyle(
                color: AppColors.textSecondary,
                fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          const Text(
            'Перейдите на вкладку «Серверы»\nи добавьте VLESS конфигурацию',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textMuted, fontSize: 13),
          ),
        ],
      ),
    );
  }
}

class _PlaceholderStats extends StatelessWidget {
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
      child: Row(
        children: [
          Expanded(
            child: _buildStat(
                Icons.arrow_upward_rounded, AppColors.primary, '↑'),
          ),
          Container(width: 1, height: 50, color: AppColors.border),
          Expanded(
            child: _buildStat(
                Icons.arrow_downward_rounded, AppColors.connected, '↓'),
          ),
        ],
      ),
    );
  }

  Widget _buildStat(IconData icon, Color color, String arrow) {
    return Column(
      children: [
        Icon(icon, color: color, size: 18),
        const SizedBox(height: 4),
        const Text(
          '—',
          style: TextStyle(
            color: AppColors.textMuted,
            fontSize: 20,
            fontWeight: FontWeight.w600,
          ),
        ),
        const Text(
          '0 B',
          style: TextStyle(color: AppColors.textMuted, fontSize: 11),
        ),
      ],
    );
  }
}
