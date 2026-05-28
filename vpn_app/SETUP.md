# VPN App — Инструкция по сборке

## Требования
- Flutter SDK >= 3.0 (рекомендуется 3.22+)
- Android Studio / Xcode (для мобильных платформ)
- Для iOS: macOS + Apple Developer аккаунт

---

## Быстрый старт

```bash
# 1. Перейти в папку проекта
cd vpn_app

# 2. Установить зависимости
flutter pub get

# 3. Запустить на Android устройстве / эмуляторе
flutter run -d android

# 4. Запустить на iOS симуляторе
flutter run -d ios

# 5. Запустить на Desktop (macOS / Linux / Windows)
flutter run -d macos   # или linux / windows
```

---

## Android — дополнительно

### Разрешения (уже настроены в AndroidManifest.xml)
- `BIND_VPN_SERVICE` — обязательно для VPN туннеля
- `INTERNET`, `FOREGROUND_SERVICE`, `POST_NOTIFICATIONS`

### Подпись для релиза
```bash
# Создать keystore
keytool -genkey -v -keystore release.jks -alias vpn -keyalg RSA -keysize 2048 -validity 10000

# Создать android/key.properties
storePassword=<пароль>
keyPassword=<пароль>
keyAlias=vpn
storeFile=../../release.jks
```

### Сборка APK / AAB
```bash
flutter build apk --release
flutter build appbundle --release
```

---

## iOS — дополнительно

### Требуемые entitlements
В Xcode → Runner → Signing & Capabilities добавьте:
- **Network Extensions** → Packet Tunnel Provider
- **Personal VPN**

### Расширение Network Extension
`flutter_v2ray` требует отдельный target `PacketTunnel` в Xcode.
Подробнее: https://github.com/blankparenthesis/flutter_v2ray

### Сборка для TestFlight
```bash
flutter build ipa --release
```

---

## Desktop (macOS / Linux / Windows)

На десктопе `flutter_v2ray` работает в режиме **системного прокси** 
(не полный VPN-туннель). SOCKS5 / HTTP прокси поднимается на 127.0.0.1.

```bash
# macOS
flutter build macos --release

# Linux
flutter build linux --release

# Windows
flutter build windows --release
```

---

## Структура проекта

```
lib/
├── main.dart                    ← точка входа, инициализация
├── app.dart                     ← MaterialApp + тема
├── core/
│   ├── models/
│   │   ├── server.dart          ← VlessServer модель + xray JSON генератор
│   │   └── vpn_status.dart      ← состояние подключения
│   ├── services/
│   │   ├── vpn_service.dart     ← обёртка над flutter_v2ray
│   │   ├── storage_service.dart ← SharedPreferences хранилище
│   │   └── vless_parser.dart    ← парсер vless:// URI
│   └── providers/
│       └── vpn_provider.dart    ← Provider с бизнес-логикой
└── ui/
    ├── theme/app_theme.dart     ← тёмная тема (GitHub-style)
    ├── screens/
    │   ├── home_screen.dart     ← главный экран с кнопкой подключения
    │   ├── servers_screen.dart  ← список серверов
    │   ├── add_server_screen.dart ← форма добавления / редактирования
    │   └── settings_screen.dart ← настройки прокси и маршрутизации
    └── widgets/
        ├── connection_button.dart ← анимированная кнопка с пульсацией
        ├── stats_card.dart      ← скорость, трафик, время соединения
        └── server_tile.dart     ← карточка сервера с контекстным меню
```

---

## Добавление сервера

### Способ 1 — Вставить vless:// ссылку
```
vless://UUID@host:port?type=ws&security=tls&sni=host&path=%2F#Название
```

### Способ 2 — Вручную
Экран «Серверы» → «+» → «Вручную» → заполнить форму

### Способ 3 — QR-код
Серверы → «+» → «QR-код» → навести камеру

---

## Поддерживаемые конфигурации

| Транспорт | TLS | REALITY | Без шифрования |
|-----------|-----|---------|----------------|
| TCP       | ✅  | ✅      | ✅             |
| WebSocket | ✅  | ✅      | ✅             |
| gRPC      | ✅  | ✅      | ✅             |
| HTTP/2    | ✅  | —       | —              |
| QUIC      | ✅  | —       | ✅             |

XTLS Vision Flow (`xtls-rprx-vision`) поддерживается при REALITY/TLS + TCP.
