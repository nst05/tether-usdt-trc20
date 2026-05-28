import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../../core/models/server.dart';
import '../../core/providers/vpn_provider.dart';
import '../../core/services/vless_parser.dart';
import '../theme/app_theme.dart';
import '../widgets/server_tile.dart';
import 'add_server_screen.dart';

class ServersScreen extends StatelessWidget {
  const ServersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<VpnProvider>();
    final servers = provider.servers;

    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        title: const Text('Серверы'),
        actions: [
          if (provider.isTestingDelay)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                    strokeWidth: 2, color: AppColors.primary),
              ),
            )
          else
            IconButton(
              icon: const Icon(Icons.network_ping_rounded),
              tooltip: 'Проверить все пинги',
              onPressed: provider.testAllDelays,
            ),
          PopupMenuButton<String>(
            icon: const Icon(Icons.add_rounded),
            tooltip: 'Добавить сервер',
            color: AppColors.surface,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
              side: const BorderSide(color: AppColors.border),
            ),
            itemBuilder: (_) => const [
              PopupMenuItem(
                value: 'manual',
                child: _AddMenuItem(
                  icon: Icons.edit_outlined,
                  label: 'Вручную',
                ),
              ),
              PopupMenuItem(
                value: 'clipboard',
                child: _AddMenuItem(
                  icon: Icons.content_paste_rounded,
                  label: 'Из буфера обмена',
                ),
              ),
              PopupMenuItem(
                value: 'qr',
                child: _AddMenuItem(
                  icon: Icons.qr_code_scanner_rounded,
                  label: 'QR-код',
                ),
              ),
            ],
            onSelected: (v) => _handleAdd(context, v),
          ),
        ],
      ),
      body: servers.isEmpty
          ? _EmptyState(
              onAdd: () => Navigator.push(
                context,
                MaterialPageRoute(
                    builder: (_) => const AddServerScreen()),
              ),
            )
          : ListView.builder(
              padding: const EdgeInsets.symmetric(vertical: 8),
              itemCount: servers.length,
              itemBuilder: (_, i) {
                final s = servers[i];
                return ServerTile(
                  server: s,
                  isSelected: provider.selectedServer?.id == s.id,
                  isConnected: provider.status.isConnected &&
                      provider.status.connectedServerId == s.id,
                  onTap: () =>
                      context.read<VpnProvider>().selectServer(s),
                  onEdit: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                        builder: (_) => AddServerScreen(server: s)),
                  ),
                  onDelete: () =>
                      context.read<VpnProvider>().deleteServer(s.id),
                  onTestPing: () =>
                      context.read<VpnProvider>().testServerDelay(s.id),
                  onToggleFavorite: () =>
                      context.read<VpnProvider>().toggleFavorite(s.id),
                  onConnect: () async {
                    context.read<VpnProvider>().selectServer(s);
                    await context.read<VpnProvider>().connect(s);
                  },
                );
              },
            ),
      floatingActionButton: servers.isEmpty
          ? null
          : FloatingActionButton(
              onPressed: () => Navigator.push(
                context,
                MaterialPageRoute(
                    builder: (_) => const AddServerScreen()),
              ),
              child: const Icon(Icons.add_rounded),
            ),
    );
  }

  void _handleAdd(BuildContext context, String type) async {
    switch (type) {
      case 'manual':
        await Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => const AddServerScreen()),
        );
        break;
      case 'clipboard':
        await _importFromClipboard(context);
        break;
      case 'qr':
        await _importFromQr(context);
        break;
    }
  }

  Future<void> _importFromClipboard(BuildContext context) async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final text = data?.text?.trim();

    if (text == null || text.isEmpty) {
      if (context.mounted) {
        _showError(context, 'Буфер обмена пуст');
      }
      return;
    }

    if (context.mounted) {
      _tryImport(context, text);
    }
  }

  Future<void> _importFromQr(BuildContext context) async {
    final result = await Navigator.push<String>(
      context,
      MaterialPageRoute(builder: (_) => const _QrScannerScreen()),
    );
    if (result != null && context.mounted) {
      _tryImport(context, result);
    }
  }

  void _tryImport(BuildContext context, String text) {
    try {
      final server = VlessParser.parse(text);
      context.read<VpnProvider>().addServer(server);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Сервер "${server.displayName}" добавлен'),
          backgroundColor: AppColors.connected,
        ),
      );
    } on VlessParseException catch (e) {
      _showError(context, e.message);
    } catch (e) {
      _showError(context, 'Ошибка импорта: $e');
    }
  }

  void _showError(BuildContext context, String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: AppColors.error,
      ),
    );
  }
}

class _AddMenuItem extends StatelessWidget {
  final IconData icon;
  final String label;
  const _AddMenuItem({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 18, color: AppColors.textSecondary),
        const SizedBox(width: 12),
        Text(label,
            style: const TextStyle(
                color: AppColors.textPrimary, fontSize: 14)),
      ],
    );
  }
}

class _EmptyState extends StatelessWidget {
  final VoidCallback onAdd;
  const _EmptyState({required this.onAdd});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(40),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.dns_outlined,
                size: 72, color: AppColors.textMuted),
            const SizedBox(height: 24),
            const Text(
              'Нет серверов',
              style: TextStyle(
                  color: AppColors.textPrimary,
                  fontSize: 22,
                  fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            const Text(
              'Добавьте VLESS сервер вручную,\nвставьте ссылку или отсканируйте QR-код',
              textAlign: TextAlign.center,
              style: TextStyle(
                  color: AppColors.textSecondary, fontSize: 14),
            ),
            const SizedBox(height: 32),
            ElevatedButton.icon(
              onPressed: onAdd,
              icon: const Icon(Icons.add_rounded),
              label: const Text('Добавить сервер'),
            ),
          ],
        ),
      ),
    );
  }
}

// QR Scanner screen
class _QrScannerScreen extends StatefulWidget {
  const _QrScannerScreen();

  @override
  State<_QrScannerScreen> createState() => _QrScannerScreenState();
}

class _QrScannerScreenState extends State<_QrScannerScreen> {
  bool _scanned = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        title: const Text('Сканировать QR-код'),
        foregroundColor: Colors.white,
      ),
      body: Stack(
        children: [
          // mobile_scanner widget — uncomment when package is added
          // MobileScanner(
          //   onDetect: (capture) {
          //     if (_scanned) return;
          //     final barcode = capture.barcodes.first;
          //     if (barcode.rawValue != null) {
          //       setState(() => _scanned = true);
          //       Navigator.pop(context, barcode.rawValue);
          //     }
          //   },
          // ),
          Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  width: 240,
                  height: 240,
                  decoration: BoxDecoration(
                    border:
                        Border.all(color: AppColors.primary, width: 2),
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
                const SizedBox(height: 24),
                const Text(
                  'Наведите камеру на QR-код',
                  style: TextStyle(color: Colors.white, fontSize: 16),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
