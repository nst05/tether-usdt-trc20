import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'app.dart';
import 'core/providers/vpn_provider.dart';
import 'core/services/storage_service.dart';
import 'core/services/vpn_service.dart';
import 'core/services/vless_parser.dart';
import 'core/models/server.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
    systemNavigationBarColor: Color(0xFF0D1117),
    systemNavigationBarIconBrightness: Brightness.light,
  ));

  final storage = StorageService();
  final vpnService = VpnService();

  final provider = _createProvider(storage, vpnService);
  await provider.init();

  runApp(
    ChangeNotifierProvider.value(
      value: provider,
      child: const VpnApp(),
    ),
  );
}

VpnProvider _createProvider(
    StorageService storage, VpnService vpnService) {
  // Patch the VlessParserHelper so it can be used from compute()
  // In production use, the parse is done on main isolate for simplicity
  return _AppVpnProvider(storage: storage, vpnService: vpnService);
}

// ── Override to wire up VlessParser ─────────────────────────────────────────
class _AppVpnProvider extends VpnProvider {
  _AppVpnProvider({
    required super.storage,
    required super.vpnService,
  });

  @override
  Future<void> addServerFromLink(String link) async {
    final server = VlessParser.parse(link);
    await addServer(server);
  }
}
