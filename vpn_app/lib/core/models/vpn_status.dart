enum VpnState { disconnected, connecting, connected, disconnecting, error }

class VpnStatus {
  final VpnState state;
  final String? message;
  final int? uploadSpeed;
  final int? downloadSpeed;
  final int? totalUpload;
  final int? totalDownload;
  final Duration? duration;
  final String? connectedServerId;

  const VpnStatus({
    required this.state,
    this.message,
    this.uploadSpeed,
    this.downloadSpeed,
    this.totalUpload,
    this.totalDownload,
    this.duration,
    this.connectedServerId,
  });

  const VpnStatus.disconnected()
      : state = VpnState.disconnected,
        message = null,
        uploadSpeed = null,
        downloadSpeed = null,
        totalUpload = null,
        totalDownload = null,
        duration = null,
        connectedServerId = null;

  bool get isConnected => state == VpnState.connected;
  bool get isConnecting =>
      state == VpnState.connecting || state == VpnState.disconnecting;
  bool get isDisconnected => state == VpnState.disconnected;

  String get stateLabel {
    switch (state) {
      case VpnState.disconnected:
        return 'Отключён';
      case VpnState.connecting:
        return 'Подключение...';
      case VpnState.connected:
        return 'Подключён';
      case VpnState.disconnecting:
        return 'Отключение...';
      case VpnState.error:
        return 'Ошибка';
    }
  }

  String formatSpeed(int? bytesPerSec) {
    if (bytesPerSec == null) return '0 B/s';
    if (bytesPerSec < 1024) return '$bytesPerSec B/s';
    if (bytesPerSec < 1024 * 1024) {
      return '${(bytesPerSec / 1024).toStringAsFixed(1)} KB/s';
    }
    return '${(bytesPerSec / (1024 * 1024)).toStringAsFixed(2)} MB/s';
  }

  String formatBytes(int? bytes) {
    if (bytes == null) return '0 B';
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) {
      return '${(bytes / (1024 * 1024)).toStringAsFixed(2)} MB';
    }
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(2)} GB';
  }

  String get uploadSpeedFormatted => formatSpeed(uploadSpeed);
  String get downloadSpeedFormatted => formatSpeed(downloadSpeed);
  String get totalUploadFormatted => formatBytes(totalUpload);
  String get totalDownloadFormatted => formatBytes(totalDownload);

  String get durationFormatted {
    if (duration == null) return '00:00:00';
    final h = duration!.inHours.toString().padLeft(2, '0');
    final m = (duration!.inMinutes % 60).toString().padLeft(2, '0');
    final s = (duration!.inSeconds % 60).toString().padLeft(2, '0');
    return '$h:$m:$s';
  }

  VpnStatus copyWith({
    VpnState? state,
    String? message,
    int? uploadSpeed,
    int? downloadSpeed,
    int? totalUpload,
    int? totalDownload,
    Duration? duration,
    String? connectedServerId,
  }) =>
      VpnStatus(
        state: state ?? this.state,
        message: message ?? this.message,
        uploadSpeed: uploadSpeed ?? this.uploadSpeed,
        downloadSpeed: downloadSpeed ?? this.downloadSpeed,
        totalUpload: totalUpload ?? this.totalUpload,
        totalDownload: totalDownload ?? this.totalDownload,
        duration: duration ?? this.duration,
        connectedServerId: connectedServerId ?? this.connectedServerId,
      );
}
