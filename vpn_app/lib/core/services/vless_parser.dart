import 'package:uuid/uuid.dart';
import '../models/server.dart';

class VlessParseException implements Exception {
  final String message;
  const VlessParseException(this.message);
  @override
  String toString() => 'VlessParseException: $message';
}

class VlessParser {
  static const _uuid = Uuid();

  static VlessServer parse(String rawLink) {
    final trimmed = rawLink.trim();

    if (trimmed.startsWith('vless://')) {
      return _parseVlessUri(trimmed);
    }

    if (trimmed.startsWith('{')) {
      return _parseJsonConfig(trimmed);
    }

    throw const VlessParseException('Неизвестный формат конфигурации');
  }

  static VlessServer _parseVlessUri(String uri) {
    // vless://uuid@host:port?params#name
    try {
      final withoutScheme = uri.substring('vless://'.length);
      final hashIdx = withoutScheme.indexOf('#');
      final name = hashIdx != -1
          ? Uri.decodeComponent(withoutScheme.substring(hashIdx + 1))
          : '';
      final main =
          hashIdx != -1 ? withoutScheme.substring(0, hashIdx) : withoutScheme;

      final atIdx = main.lastIndexOf('@');
      if (atIdx == -1) throw const VlessParseException('Нет символа @');

      final userInfo = main.substring(0, atIdx);
      final hostPart = main.substring(atIdx + 1);

      final qIdx = hostPart.indexOf('?');
      final hostPort = qIdx != -1 ? hostPart.substring(0, qIdx) : hostPart;
      final queryStr = qIdx != -1 ? hostPart.substring(qIdx + 1) : '';

      final lastColon = hostPort.lastIndexOf(':');
      if (lastColon == -1) throw const VlessParseException('Нет порта');

      final host = hostPort.substring(0, lastColon);
      final port = int.tryParse(hostPort.substring(lastColon + 1));
      if (port == null) throw const VlessParseException('Неверный порт');

      final uuid = userInfo;
      final params = Uri.splitQueryString(queryStr);

      final networkStr = params['type'] ?? 'tcp';
      final securityStr = params['security'] ?? 'none';

      return VlessServer(
        id: _uuid.v4(),
        name: name,
        address: host,
        port: port,
        uuid: uuid,
        encryption: params['encryption'] ?? 'none',
        flow: params['flow'] ?? '',
        network: _parseNetwork(networkStr),
        security: _parseSecurity(securityStr),
        sni: params['sni'],
        fingerprint: params['fp'],
        path: params['path'] != null
            ? Uri.decodeComponent(params['path']!)
            : null,
        host: params['host'],
        publicKey: params['pbk'],
        shortId: params['sid'],
        spiderX: params['spx'] != null
            ? Uri.decodeComponent(params['spx']!)
            : null,
        grpcServiceName: params['serviceName'],
      );
    } on VlessParseException {
      rethrow;
    } catch (e) {
      throw VlessParseException('Ошибка разбора VLESS URI: $e');
    }
  }

  static VlessServer _parseJsonConfig(String json) {
    throw const VlessParseException(
        'Импорт из JSON конфига пока не поддерживается');
  }

  static NetworkType _parseNetwork(String s) {
    switch (s.toLowerCase()) {
      case 'ws':
        return NetworkType.ws;
      case 'grpc':
        return NetworkType.grpc;
      case 'quic':
        return NetworkType.quic;
      case 'h2':
      case 'http':
        return NetworkType.h2;
      default:
        return NetworkType.tcp;
    }
  }

  static SecurityType _parseSecurity(String s) {
    switch (s.toLowerCase()) {
      case 'tls':
        return SecurityType.tls;
      case 'reality':
        return SecurityType.reality;
      default:
        return SecurityType.none;
    }
  }

  static String toVlessUri(VlessServer server) {
    final params = <String, String>{};
    params['type'] = server._networkString;
    params['security'] = server.security.name;
    if (server.encryption.isNotEmpty) params['encryption'] = server.encryption;
    if (server.flow.isNotEmpty) params['flow'] = server.flow;
    if (server.sni != null && server.sni!.isNotEmpty) {
      params['sni'] = server.sni!;
    }
    if (server.fingerprint != null && server.fingerprint!.isNotEmpty) {
      params['fp'] = server.fingerprint!;
    }
    if (server.path != null && server.path!.isNotEmpty) {
      params['path'] = Uri.encodeComponent(server.path!);
    }
    if (server.host != null && server.host!.isNotEmpty) {
      params['host'] = server.host!;
    }
    if (server.publicKey != null && server.publicKey!.isNotEmpty) {
      params['pbk'] = server.publicKey!;
    }
    if (server.shortId != null && server.shortId!.isNotEmpty) {
      params['sid'] = server.shortId!;
    }
    if (server.spiderX != null && server.spiderX!.isNotEmpty) {
      params['spx'] = Uri.encodeComponent(server.spiderX!);
    }
    if (server.grpcServiceName != null &&
        server.grpcServiceName!.isNotEmpty) {
      params['serviceName'] = server.grpcServiceName!;
    }

    final query = params.entries.map((e) => '${e.key}=${e.value}').join('&');
    final fragment = Uri.encodeComponent(server.name);
    return 'vless://${server.uuid}@${server.address}:${server.port}?$query#$fragment';
  }
}

extension _NetworkStr on VlessServer {
  String get _networkString {
    switch (network) {
      case NetworkType.ws:
        return 'ws';
      case NetworkType.grpc:
        return 'grpc';
      case NetworkType.quic:
        return 'quic';
      case NetworkType.h2:
        return 'h2';
      case NetworkType.tcp:
        return 'tcp';
    }
  }
}
