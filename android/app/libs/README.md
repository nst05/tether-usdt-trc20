# Нативное ядро (libs/)

Сюда кладётся **`libv2ray.aar`** — ядро Xray, собранное через `gomobile bind`
из [AndroidLibXrayLite](https://github.com/2dust/AndroidLibXrayLite).

Актуальный API ядра — `CoreController.startLoop(configContent, tunFd)`: ядро
принимает файловый дескриптор TUN напрямую и мостит трафик внутри. **Отдельный
tun2socks не нужен.**

## Как получить

AAR автоматически собирается в CI — см. `.github/workflows/android.yml`
(job `build-full`, шаг «Build libv2ray.aar»). Ключевой момент — флаг сборки:

```bash
git clone https://github.com/2dust/AndroidLibXrayLite
cd AndroidLibXrayLite
go install golang.org/x/mobile/cmd/gomobile@latest
go install golang.org/x/mobile/cmd/gobind@latest
go mod tidy
# -checklinkname=0 обходит ошибку wlynxg/anet на Go 1.23+
gomobile bind -target=android -androidapi 24 -ldflags="-checklinkname=0" -o libv2ray.aar ./
```

Положите готовый `libv2ray.aar` в этот каталог для флейвора `full`.

> Без AAR флейвор `stub` компилируется на заглушке (UI работает, туннель — нет).
