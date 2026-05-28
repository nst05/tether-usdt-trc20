import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/providers/vpn_provider.dart';
import '../theme/app_theme.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<VpnProvider>();
    final settings = provider.settings;

    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(title: const Text('Настройки')),
      body: ListView(
        children: [
          _sectionHeader('Прокси'),
          _numberTile(
            context: context,
            icon: Icons.settings_ethernet_rounded,
            title: 'SOCKS порт',
            subtitle: 'Локальный SOCKS5 прокси',
            value: settings['socksPort'] as int? ?? 10808,
            onChanged: (v) =>
                provider.updateSettings({'socksPort': v}),
          ),
          _numberTile(
            context: context,
            icon: Icons.http_rounded,
            title: 'HTTP порт',
            subtitle: 'Локальный HTTP прокси',
            value: settings['httpPort'] as int? ?? 10809,
            onChanged: (v) =>
                provider.updateSettings({'httpPort': v}),
          ),

          _sectionHeader('Маршрутизация'),
          _switchTile(
            icon: Icons.home_outlined,
            title: 'Обходить локальную сеть',
            subtitle: 'Трафик 192.168.x.x идёт напрямую',
            value: settings['bypassLan'] as bool? ?? true,
            onChanged: (v) =>
                provider.updateSettings({'bypassLan': v}),
          ),
          _switchTile(
            icon: Icons.flag_outlined,
            title: 'Обходить китайские сайты',
            subtitle: 'geoip:cn и geosite:cn идут напрямую',
            value: settings['bypassChina'] as bool? ?? false,
            onChanged: (v) =>
                provider.updateSettings({'bypassChina': v}),
          ),

          _sectionHeader('Производительность'),
          _switchTile(
            icon: Icons.compress_rounded,
            title: 'Мультиплексирование (Mux)',
            subtitle: 'Объединяет несколько соединений в одно',
            value: settings['enableMux'] as bool? ?? false,
            onChanged: (v) =>
                provider.updateSettings({'enableMux': v}),
          ),

          _sectionHeader('Поведение'),
          _switchTile(
            icon: Icons.play_circle_outline_rounded,
            title: 'Подключаться при запуске',
            subtitle: 'Автоматически подключаться при открытии',
            value: settings['connectOnStart'] as bool? ?? false,
            onChanged: (v) =>
                provider.updateSettings({'connectOnStart': v}),
          ),

          _sectionHeader('О приложении'),
          _infoTile(
            icon: Icons.info_outline_rounded,
            title: 'Версия',
            trailing: '1.0.0',
          ),
          _infoTile(
            icon: Icons.code_rounded,
            title: 'Ядро',
            trailing: 'Xray-core',
          ),
          _infoTile(
            icon: Icons.verified_outlined,
            title: 'Протокол',
            trailing: 'VLESS',
          ),

          const SizedBox(height: 32),
        ],
      ),
    );
  }

  Widget _sectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 24, 16, 8),
      child: Text(
        title.toUpperCase(),
        style: const TextStyle(
          color: AppColors.primary,
          fontSize: 11,
          fontWeight: FontWeight.w700,
          letterSpacing: 1,
        ),
      ),
    );
  }

  Widget _switchTile({
    required IconData icon,
    required String title,
    required String subtitle,
    required bool value,
    required ValueChanged<bool> onChanged,
  }) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: SwitchListTile(
        secondary: Icon(icon, color: AppColors.textSecondary),
        title: Text(title,
            style: const TextStyle(
                color: AppColors.textPrimary, fontSize: 14)),
        subtitle: Text(subtitle,
            style: const TextStyle(
                color: AppColors.textMuted, fontSize: 12)),
        value: value,
        onChanged: onChanged,
        dense: true,
      ),
    );
  }

  Widget _numberTile({
    required BuildContext context,
    required IconData icon,
    required String title,
    required String subtitle,
    required int value,
    required ValueChanged<int> onChanged,
  }) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: ListTile(
        leading: Icon(icon, color: AppColors.textSecondary),
        title: Text(title,
            style: const TextStyle(
                color: AppColors.textPrimary, fontSize: 14)),
        subtitle: Text(subtitle,
            style: const TextStyle(
                color: AppColors.textMuted, fontSize: 12)),
        trailing: GestureDetector(
          onTap: () => _editPort(context, title, value, onChanged),
          child: Container(
            padding:
                const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: AppColors.bg,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: AppColors.border),
            ),
            child: Text(
              value.toString(),
              style: const TextStyle(
                  color: AppColors.primary,
                  fontWeight: FontWeight.w600,
                  fontSize: 14),
            ),
          ),
        ),
        dense: true,
      ),
    );
  }

  Widget _infoTile({
    required IconData icon,
    required String title,
    required String trailing,
  }) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: ListTile(
        leading: Icon(icon, color: AppColors.textSecondary),
        title: Text(title,
            style: const TextStyle(
                color: AppColors.textPrimary, fontSize: 14)),
        trailing: Text(
          trailing,
          style: const TextStyle(
              color: AppColors.textSecondary, fontSize: 13),
        ),
        dense: true,
      ),
    );
  }

  void _editPort(
    BuildContext context,
    String label,
    int current,
    ValueChanged<int> onChanged,
  ) {
    final ctrl = TextEditingController(text: current.toString());
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: const BorderSide(color: AppColors.border),
        ),
        title: Text(label,
            style: const TextStyle(color: AppColors.textPrimary)),
        content: TextField(
          controller: ctrl,
          keyboardType: TextInputType.number,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Порт'),
          style: const TextStyle(color: AppColors.textPrimary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Отмена',
                style: TextStyle(color: AppColors.textSecondary)),
          ),
          ElevatedButton(
            onPressed: () {
              final n = int.tryParse(ctrl.text);
              if (n != null && n > 0 && n < 65536) {
                onChanged(n);
              }
              Navigator.pop(ctx);
            },
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }
}
