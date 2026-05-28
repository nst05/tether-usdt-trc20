import 'dart:async';
import 'package:flutter/foundation.dart';
import '../models/server.dart';
import '../models/vpn_status.dart';
import '../services/storage_service.dart';
import '../services/vpn_service.dart';

class VpnProvider extends ChangeNotifier {
  final StorageService _storage;
  final VpnService _vpnService;

  List<VlessServer> _servers = [];
  VlessServer? _selectedServer;
  VpnStatus _status = const VpnStatus.disconnected();
  StreamSubscription<VpnStatus>? _statusSub;
  Map<String, dynamic> _settings = {};
  bool _isTestingDelay = false;

  VpnProvider({
    required StorageService storage,
    required VpnService vpnService,
  })  : _storage = storage,
        _vpnService = vpnService;

  List<VlessServer> get servers => List.unmodifiable(_servers);
  VlessServer? get selectedServer => _selectedServer;
  VpnStatus get status => _status;
  Map<String, dynamic> get settings => Map.unmodifiable(_settings);
  bool get isTestingDelay => _isTestingDelay;

  Future<void> init() async {
    await _storage.init();
    _servers = _storage.loadServers();
    _settings = _storage.loadSettings();

    final selectedId = _storage.loadSelectedServerId();
    if (selectedId != null) {
      _selectedServer = _servers.cast<VlessServer?>().firstWhere(
            (s) => s?.id == selectedId,
            orElse: () => null,
          );
    }
    if (_selectedServer == null && _servers.isNotEmpty) {
      _selectedServer = _servers.first;
    }

    await _vpnService.init();
    _statusSub = _vpnService.statusStream.listen((s) {
      _status = s;
      notifyListeners();
    });

    notifyListeners();
  }

  // ── Connection ────────────────────────────────────────────────────────────

  Future<void> toggleConnection() async {
    if (_status.isConnected || _status.isConnecting) {
      await disconnect();
    } else {
      await connect();
    }
  }

  Future<bool> connect([VlessServer? server]) async {
    final target = server ?? _selectedServer;
    if (target == null) return false;
    if (server != null) selectServer(server);
    return await _vpnService.connect(target);
  }

  Future<void> disconnect() async {
    await _vpnService.disconnect();
  }

  // ── Server management ─────────────────────────────────────────────────────

  void selectServer(VlessServer server) {
    _selectedServer = server;
    _storage.saveSelectedServerId(server.id);
    notifyListeners();
  }

  Future<void> addServer(VlessServer server) async {
    _servers.add(server);
    await _storage.saveServers(_servers);
    if (_servers.length == 1) selectServer(server);
    notifyListeners();
  }

  Future<void> addServerFromLink(String link) async {
    // Subclasses override this to inject VlessParser.
    throw UnimplementedError(
        'Override addServerFromLink in your app entry point');
  }

  Future<void> updateServer(VlessServer updated) async {
    final idx = _servers.indexWhere((s) => s.id == updated.id);
    if (idx == -1) return;
    _servers[idx] = updated;
    await _storage.saveServers(_servers);
    if (_selectedServer?.id == updated.id) _selectedServer = updated;
    notifyListeners();
  }

  Future<void> deleteServer(String id) async {
    _servers.removeWhere((s) => s.id == id);
    await _storage.deleteServer(id);
    if (_selectedServer?.id == id) {
      _selectedServer = _servers.isNotEmpty ? _servers.first : null;
    }
    notifyListeners();
  }

  Future<void> toggleFavorite(String id) async {
    final idx = _servers.indexWhere((s) => s.id == id);
    if (idx == -1) return;
    _servers[idx] = _servers[idx].copyWith(
      isFavorite: !_servers[idx].isFavorite,
    );
    await _storage.saveServers(_servers);
    notifyListeners();
  }

  Future<void> testServerDelay(String id) async {
    final idx = _servers.indexWhere((s) => s.id == id);
    if (idx == -1) return;

    _isTestingDelay = true;
    notifyListeners();

    final delay = await _vpnService.testDelay(_servers[idx]);
    _servers[idx] = _servers[idx].copyWith(ping: delay);
    await _storage.saveServers(_servers);

    _isTestingDelay = false;
    notifyListeners();
  }

  Future<void> testAllDelays() async {
    _isTestingDelay = true;
    notifyListeners();

    await Future.wait(_servers.map((s) async {
      final delay = await _vpnService.testDelay(s);
      final idx = _servers.indexWhere((x) => x.id == s.id);
      if (idx != -1) _servers[idx] = _servers[idx].copyWith(ping: delay);
    }));

    await _storage.saveServers(_servers);
    _isTestingDelay = false;
    notifyListeners();
  }

  // ── Settings ──────────────────────────────────────────────────────────────

  Future<void> updateSettings(Map<String, dynamic> newSettings) async {
    _settings = {..._settings, ...newSettings};
    await _storage.saveSettings(_settings);
    notifyListeners();
  }

  @override
  void dispose() {
    _statusSub?.cancel();
    _vpnService.dispose();
    super.dispose();
  }
}
