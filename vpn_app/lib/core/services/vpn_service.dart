import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_v2ray/flutter_v2ray.dart';
import '../models/server.dart';
import '../models/vpn_status.dart';

class VpnService {
  late FlutterV2ray _flutterV2ray;
  final _statusController = StreamController<VpnStatus>.broadcast();
  VpnStatus _current = const VpnStatus.disconnected();
  Timer? _durationTimer;
  DateTime? _connectTime;
  V2RayStatus? _lastV2Status;

  Stream<VpnStatus> get statusStream => _statusController.stream;
  VpnStatus get current => _current;

  Future<void> init() async {
    _flutterV2ray = FlutterV2ray(
      onStatusChanged: _onV2RayStatusChanged,
    );
    await _flutterV2ray.initializeV2Ray(
      notificationIconResourceType: 'mipmap',
      notificationIconResourceName: 'ic_launcher',
    );
  }

  void _onV2RayStatusChanged(V2RayStatus status) {
    _lastV2Status = status;
    _updateStatus(status);
  }

  void _updateStatus(V2RayStatus v2Status) {
    final state = _mapV2State(v2Status.state);

    if (state == VpnState.connected && _connectTime == null) {
      _connectTime = DateTime.now();
      _startDurationTimer();
    }

    if (state == VpnState.disconnected) {
      _stopDurationTimer();
      _connectTime = null;
    }

    _current = VpnStatus(
      state: state,
      message: v2Status.state,
      uploadSpeed: v2Status.uploadSpeed,
      downloadSpeed: v2Status.downloadSpeed,
      totalUpload: v2Status.upload,
      totalDownload: v2Status.download,
      duration: _connectTime != null
          ? DateTime.now().difference(_connectTime!)
          : null,
      connectedServerId: state == VpnState.connected ? _current.connectedServerId : null,
    );

    _statusController.add(_current);
  }

  VpnState _mapV2State(String state) {
    switch (state.toUpperCase()) {
      case 'CONNECTED':
        return VpnState.connected;
      case 'CONNECTING':
        return VpnState.connecting;
      case 'DISCONNECTING':
        return VpnState.disconnecting;
      case 'DISCONNECTED':
        return VpnState.disconnected;
      default:
        return VpnState.disconnected;
    }
  }

  Future<bool> requestPermission() async {
    if (Platform.isAndroid || Platform.isIOS) {
      return await _flutterV2ray.requestPermission();
    }
    return true;
  }

  Future<bool> connect(VlessServer server) async {
    try {
      _emit(VpnStatus(
        state: VpnState.connecting,
        connectedServerId: server.id,
      ));

      final hasPermission = await requestPermission();
      if (!hasPermission) {
        _emit(const VpnStatus(
          state: VpnState.error,
          message: 'Нет разрешения на использование VPN',
        ));
        return false;
      }

      final config = server.toXrayConfig();

      await _flutterV2ray.startV2Ray(
        remark: server.displayName,
        config: config,
        blockedApps: null,
        bypassSubnets: null,
        proxyOnly: false,
      );

      _current = _current.copyWith(connectedServerId: server.id);
      return true;
    } catch (e) {
      _emit(VpnStatus(
        state: VpnState.error,
        message: 'Ошибка подключения: $e',
      ));
      return false;
    }
  }

  Future<void> disconnect() async {
    try {
      _emit(const VpnStatus(state: VpnState.disconnecting));
      await _flutterV2ray.stopV2Ray();
    } catch (e) {
      _emit(const VpnStatus.disconnected());
    }
  }

  Future<int?> testDelay(VlessServer server) async {
    try {
      final config = server.toXrayConfig();
      final result = await _flutterV2ray.getServerDelay(config: config);
      return result;
    } catch (_) {
      return null;
    }
  }

  void _emit(VpnStatus status) {
    _current = status;
    _statusController.add(status);
  }

  void _startDurationTimer() {
    _durationTimer?.cancel();
    _durationTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_connectTime == null) return;
      _current = _current.copyWith(
        duration: DateTime.now().difference(_connectTime!),
      );
      _statusController.add(_current);
    });
  }

  void _stopDurationTimer() {
    _durationTimer?.cancel();
    _durationTimer = null;
  }

  void dispose() {
    _stopDurationTimer();
    _statusController.close();
  }
}
