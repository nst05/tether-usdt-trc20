import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/server.dart';

class StorageService {
  static const _serversKey = 'vless_servers';
  static const _selectedServerKey = 'selected_server_id';
  static const _appSettingsKey = 'app_settings';

  late SharedPreferences _prefs;

  Future<void> init() async {
    _prefs = await SharedPreferences.getInstance();
  }

  // ── Servers ──────────────────────────────────────────────────────────────

  List<VlessServer> loadServers() {
    final jsonStr = _prefs.getString(_serversKey);
    if (jsonStr == null) return [];
    try {
      final list = jsonDecode(jsonStr) as List;
      return list
          .map((e) => VlessServer.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return [];
    }
  }

  Future<void> saveServers(List<VlessServer> servers) async {
    final jsonStr = jsonEncode(servers.map((s) => s.toJson()).toList());
    await _prefs.setString(_serversKey, jsonStr);
  }

  Future<void> addServer(VlessServer server) async {
    final servers = loadServers();
    servers.add(server);
    await saveServers(servers);
  }

  Future<void> updateServer(VlessServer updated) async {
    final servers = loadServers();
    final idx = servers.indexWhere((s) => s.id == updated.id);
    if (idx != -1) {
      servers[idx] = updated;
      await saveServers(servers);
    }
  }

  Future<void> deleteServer(String id) async {
    final servers = loadServers();
    servers.removeWhere((s) => s.id == id);
    await saveServers(servers);
    if (loadSelectedServerId() == id) {
      await clearSelectedServer();
    }
  }

  // ── Selection ─────────────────────────────────────────────────────────────

  String? loadSelectedServerId() => _prefs.getString(_selectedServerKey);

  Future<void> saveSelectedServerId(String id) async {
    await _prefs.setString(_selectedServerKey, id);
  }

  Future<void> clearSelectedServer() async {
    await _prefs.remove(_selectedServerKey);
  }

  // ── Settings ──────────────────────────────────────────────────────────────

  Map<String, dynamic> loadSettings() {
    final jsonStr = _prefs.getString(_appSettingsKey);
    if (jsonStr == null) return _defaultSettings;
    try {
      return jsonDecode(jsonStr) as Map<String, dynamic>;
    } catch (_) {
      return _defaultSettings;
    }
  }

  Future<void> saveSettings(Map<String, dynamic> settings) async {
    await _prefs.setString(_appSettingsKey, jsonEncode(settings));
  }

  static const _defaultSettings = {
    'socksPort': 10808,
    'httpPort': 10809,
    'bypassLan': true,
    'bypassChina': false,
    'enableMux': false,
    'connectOnStart': false,
    'darkMode': true,
  };
}
