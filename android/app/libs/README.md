# Нативное ядро (libs/)

Сюда кладётся **`libv2ray.aar`** — ядро Xray, собранное через `gomobile bind`
из [AndroidLibXrayLite](https://github.com/2dust/AndroidLibXrayLite).

Плюс нативная библиотека **`libtun2socks.so`** (для каждой ABI) — мост TUN↔SOCKS,
кладётся в `app/src/main/jniLibs/<abi>/libtun2socks.so`.

## Как получить

Оба артефакта автоматически собираются в CI — см.
`.github/workflows/android.yml` (job `build-core`). Локально можно:

```bash
# libv2ray.aar
git clone https://github.com/2dust/AndroidLibXrayLite
cd AndroidLibXrayLite
go install golang.org/x/mobile/cmd/gomobile@latest
gomobile init
./gradlew :libv2ray... # либо gomobile bind -target=android -o libv2ray.aar ./
```

`libtun2socks.so` собирается из
[badvpn/tun2socks](https://github.com/heiher/hev-socks5-tunnel) или берётся из
сборки v2rayNG (`app/libs`), где он уже присутствует под каждую ABI.

> Без этих файлов проект компилируется, но туннель работать не будет.
> Заглушка `stub/libv2ray-stub.jar` (см. ниже) позволяет собрать APK для проверки UI.
