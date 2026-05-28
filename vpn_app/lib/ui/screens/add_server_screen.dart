import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';
import '../../core/models/server.dart';
import '../../core/providers/vpn_provider.dart';
import '../../core/services/vless_parser.dart';
import '../theme/app_theme.dart';

class AddServerScreen extends StatefulWidget {
  final VlessServer? server;
  const AddServerScreen({super.key, this.server});

  @override
  State<AddServerScreen> createState() => _AddServerScreenState();
}

class _AddServerScreenState extends State<AddServerScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tab;
  final _formKey = GlobalKey<FormState>();
  static const _uuid = Uuid();

  // Form fields
  late TextEditingController _name;
  late TextEditingController _address;
  late TextEditingController _port;
  late TextEditingController _uuidCtrl;
  late TextEditingController _flow;
  late TextEditingController _sni;
  late TextEditingController _fingerprint;
  late TextEditingController _path;
  late TextEditingController _host;
  late TextEditingController _publicKey;
  late TextEditingController _shortId;
  late TextEditingController _spiderX;
  late TextEditingController _grpcService;

  NetworkType _network = NetworkType.tcp;
  SecurityType _security = SecurityType.none;

  // Link import
  final _linkCtrl = TextEditingController();
  String? _linkError;

  bool get _isEditing => widget.server != null;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 2, vsync: this);
    final s = widget.server;
    _name = TextEditingController(text: s?.name ?? '');
    _address = TextEditingController(text: s?.address ?? '');
    _port = TextEditingController(text: s?.port.toString() ?? '443');
    _uuidCtrl = TextEditingController(text: s?.uuid ?? '');
    _flow = TextEditingController(text: s?.flow ?? '');
    _sni = TextEditingController(text: s?.sni ?? '');
    _fingerprint =
        TextEditingController(text: s?.fingerprint ?? 'chrome');
    _path = TextEditingController(text: s?.path ?? '/');
    _host = TextEditingController(text: s?.host ?? '');
    _publicKey = TextEditingController(text: s?.publicKey ?? '');
    _shortId = TextEditingController(text: s?.shortId ?? '');
    _spiderX = TextEditingController(text: s?.spiderX ?? '');
    _grpcService =
        TextEditingController(text: s?.grpcServiceName ?? '');
    if (s != null) {
      _network = s.network;
      _security = s.security;
    }
  }

  @override
  void dispose() {
    _tab.dispose();
    for (final c in [
      _name, _address, _port, _uuidCtrl, _flow, _sni,
      _fingerprint, _path, _host, _publicKey, _shortId,
      _spiderX, _grpcService, _linkCtrl
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        title: Text(_isEditing ? 'Изменить сервер' : 'Добавить сервер'),
        bottom: _isEditing
            ? null
            : TabBar(
                controller: _tab,
                tabs: const [
                  Tab(text: 'Вручную'),
                  Tab(text: 'По ссылке'),
                ],
                indicatorColor: AppColors.primary,
                labelColor: AppColors.primary,
                unselectedLabelColor: AppColors.textSecondary,
              ),
      ),
      body: _isEditing
          ? _buildManualForm()
          : TabBarView(
              controller: _tab,
              children: [
                _buildManualForm(),
                _buildLinkImport(),
              ],
            ),
    );
  }

  // ── Manual form ──────────────────────────────────────────────────────────

  Widget _buildManualForm() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _section('Основные'),
            _field(
              controller: _name,
              label: 'Название (необязательно)',
              hint: 'Мой сервер',
              icon: Icons.label_outline_rounded,
            ),
            _field(
              controller: _address,
              label: 'Адрес сервера *',
              hint: 'example.com или 1.2.3.4',
              icon: Icons.dns_outlined,
              validator: _required,
            ),
            Row(
              children: [
                Expanded(
                  flex: 2,
                  child: _field(
                    controller: _uuidCtrl,
                    label: 'UUID *',
                    hint: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
                    icon: Icons.vpn_key_outlined,
                    validator: _required,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _field(
                    controller: _port,
                    label: 'Порт *',
                    hint: '443',
                    icon: Icons.electrical_services_rounded,
                    keyboardType: TextInputType.number,
                    validator: _portValidator,
                  ),
                ),
              ],
            ),

            _section('Транспорт'),
            _dropdown<NetworkType>(
              label: 'Тип сети',
              value: _network,
              items: NetworkType.values,
              itemLabel: (v) => v.name.toUpperCase(),
              onChanged: (v) => setState(() => _network = v!),
            ),
            _dropdown<SecurityType>(
              label: 'Безопасность',
              value: _security,
              items: SecurityType.values,
              itemLabel: (v) => v.name.toUpperCase(),
              onChanged: (v) => setState(() => _security = v!),
            ),

            if (_network == NetworkType.ws ||
                _network == NetworkType.h2) ...[
              _field(
                  controller: _path, label: 'Path', hint: '/'),
              _field(
                  controller: _host,
                  label: 'Host (заголовок)',
                  hint: 'cdn.example.com'),
            ],
            if (_network == NetworkType.grpc)
              _field(
                  controller: _grpcService,
                  label: 'gRPC Service Name',
                  hint: 'GrpcService'),

            if (_security == SecurityType.tls ||
                _security == SecurityType.reality) ...[
              _section('TLS / REALITY'),
              _field(
                  controller: _sni,
                  label: 'SNI / Server Name',
                  hint: 'example.com'),
              _field(
                  controller: _fingerprint,
                  label: 'uTLS Fingerprint',
                  hint: 'chrome'),
            ],
            if (_security == SecurityType.reality) ...[
              _field(
                  controller: _publicKey,
                  label: 'Public Key',
                  hint: 'base64…'),
              _field(
                  controller: _shortId,
                  label: 'Short ID',
                  hint: '...'),
              _field(
                  controller: _spiderX,
                  label: 'Spider X',
                  hint: '/'),
            ],
            if (_security == SecurityType.tls ||
                _security == SecurityType.reality)
              _field(
                  controller: _flow,
                  label: 'Flow (Vision)',
                  hint: 'xtls-rprx-vision или пусто'),

            const SizedBox(height: 32),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _save,
                child: Text(_isEditing ? 'Сохранить' : 'Добавить сервер'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ── Link import ──────────────────────────────────────────────────────────

  Widget _buildLinkImport() {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Вставьте VLESS ссылку',
            style: TextStyle(
                color: AppColors.textSecondary, fontSize: 14),
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _linkCtrl,
            maxLines: 5,
            decoration: InputDecoration(
              hintText:
                  'vless://uuid@host:port?type=ws&security=tls#Название',
              errorText: _linkError,
              prefixIcon: const Icon(Icons.link_rounded),
              alignLabelWithHint: true,
            ),
            style: const TextStyle(
                color: AppColors.textPrimary, fontSize: 13),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: _importLink,
              icon: const Icon(Icons.download_rounded),
              label: const Text('Импортировать'),
            ),
          ),
          const SizedBox(height: 40),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppColors.card,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border),
            ),
            child: const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Пример ссылки',
                    style: TextStyle(
                        color: AppColors.textSecondary,
                        fontWeight: FontWeight.w600,
                        fontSize: 12)),
                SizedBox(height: 8),
                Text(
                  'vless://a9cfbfe2-7a5b-4711-89e8-…@srv.example.com:443?type=ws&security=tls&sni=srv.example.com&path=%2Fws#MyServer',
                  style: TextStyle(
                      color: AppColors.textMuted, fontSize: 11),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── Helpers ──────────────────────────────────────────────────────────────

  Widget _section(String title) {
    return Padding(
      padding: const EdgeInsets.only(top: 16, bottom: 8),
      child: Text(title.toUpperCase(),
          style: const TextStyle(
              color: AppColors.primary,
              fontSize: 11,
              fontWeight: FontWeight.w700,
              letterSpacing: 1)),
    );
  }

  Widget _field({
    required TextEditingController controller,
    required String label,
    String? hint,
    IconData? icon,
    TextInputType? keyboardType,
    String? Function(String?)? validator,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: TextFormField(
        controller: controller,
        keyboardType: keyboardType,
        validator: validator,
        decoration: InputDecoration(
          labelText: label,
          hintText: hint,
          prefixIcon: icon != null ? Icon(icon) : null,
        ),
        style:
            const TextStyle(color: AppColors.textPrimary, fontSize: 14),
      ),
    );
  }

  Widget _dropdown<T>({
    required String label,
    required T value,
    required List<T> items,
    required String Function(T) itemLabel,
    required ValueChanged<T?> onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: DropdownButtonFormField<T>(
        value: value,
        decoration: InputDecoration(labelText: label),
        dropdownColor: AppColors.surface,
        style: const TextStyle(color: AppColors.textPrimary),
        items: items
            .map((v) => DropdownMenuItem(
                value: v, child: Text(itemLabel(v))))
            .toList(),
        onChanged: onChanged,
      ),
    );
  }

  String? _required(String? v) =>
      (v == null || v.isEmpty) ? 'Обязательное поле' : null;

  String? _portValidator(String? v) {
    if (v == null || v.isEmpty) return 'Обязательное поле';
    final n = int.tryParse(v);
    if (n == null || n < 1 || n > 65535) return 'Неверный порт';
    return null;
  }

  void _save() {
    if (!(_formKey.currentState?.validate() ?? false)) return;

    final server = VlessServer(
      id: widget.server?.id ?? _uuid.v4(),
      name: _name.text.trim(),
      address: _address.text.trim(),
      port: int.parse(_port.text.trim()),
      uuid: _uuidCtrl.text.trim(),
      flow: _flow.text.trim(),
      network: _network,
      security: _security,
      sni: _sni.text.trim().isEmpty ? null : _sni.text.trim(),
      fingerprint: _fingerprint.text.trim().isEmpty
          ? null
          : _fingerprint.text.trim(),
      path: _path.text.trim().isEmpty ? null : _path.text.trim(),
      host: _host.text.trim().isEmpty ? null : _host.text.trim(),
      publicKey: _publicKey.text.trim().isEmpty
          ? null
          : _publicKey.text.trim(),
      shortId:
          _shortId.text.trim().isEmpty ? null : _shortId.text.trim(),
      spiderX:
          _spiderX.text.trim().isEmpty ? null : _spiderX.text.trim(),
      grpcServiceName: _grpcService.text.trim().isEmpty
          ? null
          : _grpcService.text.trim(),
      isFavorite: widget.server?.isFavorite ?? false,
    );

    final provider = context.read<VpnProvider>();
    if (_isEditing) {
      provider.updateServer(server);
    } else {
      provider.addServer(server);
    }
    Navigator.pop(context);
  }

  void _importLink() {
    final text = _linkCtrl.text.trim();
    if (text.isEmpty) {
      setState(() => _linkError = 'Введите ссылку');
      return;
    }
    try {
      final server = VlessParser.parse(text);
      context.read<VpnProvider>().addServer(server);
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Сервер "${server.displayName}" добавлен'),
          backgroundColor: AppColors.connected,
        ),
      );
    } on VlessParseException catch (e) {
      setState(() => _linkError = e.message);
    }
  }
}
