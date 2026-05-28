import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../../core/models/vpn_status.dart';
import '../theme/app_theme.dart';

class ConnectionButton extends StatefulWidget {
  final VpnStatus status;
  final VoidCallback onTap;

  const ConnectionButton({
    super.key,
    required this.status,
    required this.onTap,
  });

  @override
  State<ConnectionButton> createState() => _ConnectionButtonState();
}

class _ConnectionButtonState extends State<ConnectionButton>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    );
    _updateAnimation();
  }

  @override
  void didUpdateWidget(ConnectionButton old) {
    super.didUpdateWidget(old);
    if (old.status.state != widget.status.state) {
      _updateAnimation();
    }
  }

  void _updateAnimation() {
    if (widget.status.isConnecting) {
      _pulseController.repeat();
    } else if (widget.status.isConnected) {
      _pulseController.repeat();
    } else {
      _pulseController.stop();
      _pulseController.reset();
    }
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  Color get _buttonColor {
    switch (widget.status.state) {
      case VpnState.connected:
        return AppColors.connected;
      case VpnState.connecting:
      case VpnState.disconnecting:
        return AppColors.connecting;
      case VpnState.error:
        return AppColors.error;
      case VpnState.disconnected:
        return AppColors.primary;
    }
  }

  List<Color> get _gradientColors {
    switch (widget.status.state) {
      case VpnState.connected:
        return [
          AppColors.connectedGradientStart,
          AppColors.connectedGradientEnd,
        ];
      case VpnState.error:
        return [AppColors.error, AppColors.error.withOpacity(0.7)];
      default:
        return [
          AppColors.disconnectedGradientStart,
          AppColors.disconnectedGradientEnd,
        ];
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: widget.status.isConnecting ? null : widget.onTap,
      child: Stack(
        alignment: Alignment.center,
        children: [
          // Pulse rings
          if (widget.status.isConnected || widget.status.isConnecting)
            AnimatedBuilder(
              animation: _pulseController,
              builder: (_, __) {
                return CustomPaint(
                  size: const Size(200, 200),
                  painter: _PulsePainter(
                    progress: _pulseController.value,
                    color: _buttonColor,
                  ),
                );
              },
            ),

          // Main button
          Container(
            width: 140,
            height: 140,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: _gradientColors,
              ),
              boxShadow: [
                BoxShadow(
                  color: _buttonColor.withOpacity(0.4),
                  blurRadius: 30,
                  spreadRadius: 5,
                ),
              ],
            ),
            child: _buildButtonContent(),
          ),
        ],
      ),
    );
  }

  Widget _buildButtonContent() {
    switch (widget.status.state) {
      case VpnState.connecting:
      case VpnState.disconnecting:
        return const Center(
          child: SizedBox(
            width: 40,
            height: 40,
            child: CircularProgressIndicator(
              color: Colors.white,
              strokeWidth: 3,
            ),
          ),
        );
      case VpnState.connected:
        return Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.shield_rounded, color: Colors.white, size: 40),
            const SizedBox(height: 4),
            Text(
              'STOP',
              style: TextStyle(
                color: Colors.white.withOpacity(0.9),
                fontSize: 12,
                fontWeight: FontWeight.w700,
                letterSpacing: 2,
              ),
            ),
          ],
        );
      case VpnState.error:
        return const Icon(Icons.error_outline, color: Colors.white, size: 50);
      case VpnState.disconnected:
        return Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.power_settings_new_rounded,
                color: Colors.white, size: 44),
            const SizedBox(height: 4),
            Text(
              'CONNECT',
              style: TextStyle(
                color: Colors.white.withOpacity(0.9),
                fontSize: 10,
                fontWeight: FontWeight.w700,
                letterSpacing: 2,
              ),
            ),
          ],
        ),
    }
  }
}

class _PulsePainter extends CustomPainter {
  final double progress;
  final Color color;

  _PulsePainter({required this.progress, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);

    for (int i = 0; i < 3; i++) {
      final offset = i / 3;
      final t = ((progress + offset) % 1.0);
      final radius = 70.0 + t * 30;
      final opacity = (1.0 - t).clamp(0.0, 1.0) * 0.3;

      final paint = Paint()
        ..color = color.withOpacity(opacity)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2;

      canvas.drawCircle(center, radius, paint);
    }
  }

  @override
  bool shouldRepaint(_PulsePainter old) =>
      old.progress != progress || old.color != color;
}
