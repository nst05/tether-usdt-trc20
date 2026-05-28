import 'dart:convert';

enum NetworkType { tcp, ws, grpc, quic, h2 }
enum SecurityType { none, tls, reality }

class VlessServer {
  final String id;
  final String name;
  final String address;
  final int port;
  final String uuid;
  final String encryption;
  final String flow;
  final NetworkType network;
  final SecurityType security;
  final String? sni;
  final String? fingerprint;
  final String? path;
  final String? host;
  final String? publicKey;
  final String? shortId;
  final String? spiderX;
  final String? grpcServiceName;
  int? ping;
  bool isFavorite;
  DateTime addedAt;

  VlessServer({
    required this.id,
    required this.name,
    required this.address,
    required this.port,
    required this.uuid,
    this.encryption = 'none',
    this.flow = '',
    this.network = NetworkType.tcp,
    this.security = SecurityType.none,
    this.sni,
    this.fingerprint,
    this.path,
    this.host,
    this.publicKey,
    this.shortId,
    this.spiderX,
    this.grpcServiceName,
    this.ping,
    this.isFavorite = false,
    DateTime? addedAt,
  }) : addedAt = addedAt ?? DateTime.now();

  String get displayName => name.isNotEmpty ? name : '$address:$port';

  String get networkLabel {
    switch (network) {
      case NetworkType.ws:
        return 'WebSocket';
      case NetworkType.grpc:
        return 'gRPC';
      case NetworkType.quic:
        return 'QUIC';
      case NetworkType.h2:
        return 'HTTP/2';
      case NetworkType.tcp:
        return 'TCP';
    }
  }

  String get securityLabel {
    switch (security) {
      case SecurityType.tls:
        return 'TLS';
      case SecurityType.reality:
        return 'REALITY';
      case SecurityType.none:
        return 'None';
    }
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'address': address,
        'port': port,
        'uuid': uuid,
        'encryption': encryption,
        'flow': flow,
        'network': network.index,
        'security': security.index,
        'sni': sni,
        'fingerprint': fingerprint,
        'path': path,
        'host': host,
        'publicKey': publicKey,
        'shortId': shortId,
        'spiderX': spiderX,
        'grpcServiceName': grpcServiceName,
        'ping': ping,
        'isFavorite': isFavorite,
        'addedAt': addedAt.toIso8601String(),
      };

  factory VlessServer.fromJson(Map<String, dynamic> json) => VlessServer(
        id: json['id'] as String,
        name: json['name'] as String? ?? '',
        address: json['address'] as String,
        port: json['port'] as int,
        uuid: json['uuid'] as String,
        encryption: json['encryption'] as String? ?? 'none',
        flow: json['flow'] as String? ?? '',
        network: NetworkType.values[json['network'] as int? ?? 0],
        security: SecurityType.values[json['security'] as int? ?? 0],
        sni: json['sni'] as String?,
        fingerprint: json['fingerprint'] as String?,
        path: json['path'] as String?,
        host: json['host'] as String?,
        publicKey: json['publicKey'] as String?,
        shortId: json['shortId'] as String?,
        spiderX: json['spiderX'] as String?,
        grpcServiceName: json['grpcServiceName'] as String?,
        ping: json['ping'] as int?,
        isFavorite: json['isFavorite'] as bool? ?? false,
        addedAt: json['addedAt'] != null
            ? DateTime.parse(json['addedAt'] as String)
            : DateTime.now(),
      );

  VlessServer copyWith({
    String? id,
    String? name,
    String? address,
    int? port,
    String? uuid,
    String? encryption,
    String? flow,
    NetworkType? network,
    SecurityType? security,
    String? sni,
    String? fingerprint,
    String? path,
    String? host,
    String? publicKey,
    String? shortId,
    String? spiderX,
    String? grpcServiceName,
    int? ping,
    bool? isFavorite,
    DateTime? addedAt,
  }) =>
      VlessServer(
        id: id ?? this.id,
        name: name ?? this.name,
        address: address ?? this.address,
        port: port ?? this.port,
        uuid: uuid ?? this.uuid,
        encryption: encryption ?? this.encryption,
        flow: flow ?? this.flow,
        network: network ?? this.network,
        security: security ?? this.security,
        sni: sni ?? this.sni,
        fingerprint: fingerprint ?? this.fingerprint,
        path: path ?? this.path,
        host: host ?? this.host,
        publicKey: publicKey ?? this.publicKey,
        shortId: shortId ?? this.shortId,
        spiderX: spiderX ?? this.spiderX,
        grpcServiceName: grpcServiceName ?? this.grpcServiceName,
        ping: ping ?? this.ping,
        isFavorite: isFavorite ?? this.isFavorite,
        addedAt: addedAt ?? this.addedAt,
      );

  String toXrayConfig({int socksPort = 10808, int httpPort = 10809}) {
    final streamSettings = _buildStreamSettings();
    final outbound = {
      'protocol': 'vless',
      'settings': {
        'vnext': [
          {
            'address': address,
            'port': port,
            'users': [
              {
                'id': uuid,
                'encryption': encryption,
                if (flow.isNotEmpty) 'flow': flow,
              }
            ],
          }
        ]
      },
      'streamSettings': streamSettings,
      'tag': 'proxy',
    };

    final config = {
      'log': {'loglevel': 'warning'},
      'inbounds': [
        {
          'port': socksPort,
          'listen': '127.0.0.1',
          'protocol': 'socks',
          'settings': {'auth': 'noauth', 'udp': true},
          'tag': 'socks-in',
        },
        {
          'port': httpPort,
          'listen': '127.0.0.1',
          'protocol': 'http',
          'tag': 'http-in',
        },
      ],
      'outbounds': [
        outbound,
        {'protocol': 'freedom', 'tag': 'direct'},
        {'protocol': 'blackhole', 'tag': 'block'},
      ],
      'routing': {
        'domainStrategy': 'IPIfNonMatch',
        'rules': [
          {
            'type': 'field',
            'ip': ['geoip:private'],
            'outboundTag': 'direct',
          },
          {
            'type': 'field',
            'ip': ['geoip:cn'],
            'outboundTag': 'direct',
          },
          {
            'type': 'field',
            'domain': ['geosite:cn'],
            'outboundTag': 'direct',
          },
        ],
      },
    };

    return jsonEncode(config);
  }

  Map<String, dynamic> _buildStreamSettings() {
    final settings = <String, dynamic>{
      'network': _networkString,
    };

    switch (security) {
      case SecurityType.tls:
        settings['security'] = 'tls';
        settings['tlsSettings'] = {
          if (sni != null && sni!.isNotEmpty) 'serverName': sni,
          if (fingerprint != null && fingerprint!.isNotEmpty)
            'fingerprint': fingerprint,
          'allowInsecure': false,
        };
        break;
      case SecurityType.reality:
        settings['security'] = 'reality';
        settings['realitySettings'] = {
          'serverName': sni ?? address,
          'fingerprint': fingerprint ?? 'chrome',
          'publicKey': publicKey ?? '',
          if (shortId != null) 'shortId': shortId,
          if (spiderX != null) 'spiderX': spiderX,
        };
        break;
      case SecurityType.none:
        settings['security'] = 'none';
        break;
    }

    switch (network) {
      case NetworkType.ws:
        settings['wsSettings'] = {
          'path': path ?? '/',
          'headers': {
            if (host != null && host!.isNotEmpty) 'Host': host,
          },
        };
        break;
      case NetworkType.grpc:
        settings['grpcSettings'] = {
          'serviceName': grpcServiceName ?? '',
        };
        break;
      case NetworkType.h2:
        settings['httpSettings'] = {
          'path': path ?? '/',
          if (host != null && host!.isNotEmpty) 'host': [host],
        };
        break;
      case NetworkType.tcp:
      case NetworkType.quic:
        break;
    }

    return settings;
  }

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
