from fpdf import FPDF

class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.set_fill_color(20, 20, 30)
        self.set_text_color(0, 200, 100)
        self.cell(0, 12, "NEXUS PENTEST - Instrukciya", fill=True, ln=True, align="C")
        self.ln(3)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Stranica {self.page_no()}", align="C")

    def section(self, title):
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(30, 30, 50)
        self.set_text_color(80, 180, 255)
        self.cell(0, 9, title, fill=True, ln=True)
        self.ln(1)
        self.set_text_color(220, 220, 220)

    def subsection(self, title):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(0, 200, 100)
        self.cell(0, 7, title, ln=True)
        self.set_text_color(220, 220, 220)

    def body(self, text):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(210, 210, 210)
        self.multi_cell(0, 5, text)
        self.ln(1)

    def code(self, text):
        self.set_font("Courier", "", 8)
        self.set_fill_color(15, 15, 25)
        self.set_text_color(0, 230, 120)
        self.multi_cell(0, 5, text, fill=True)
        self.set_text_color(210, 210, 210)
        self.ln(1)


pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=15)
pdf.set_margins(12, 12, 12)
pdf.set_page_background((10, 10, 20))

# --- Page 1: Setup ---
pdf.add_page()

pdf.section("1. USTANOVKA")

pdf.subsection("Shag 1 - Ustanovit Python")
pdf.body("Skachat s python.org, versiya 3.10 ili vyshe.\nPri ustanovke postavit galochku: Add Python to PATH")

pdf.subsection("Shag 2 - Skachat programmu")
pdf.body("Skachat fayly s GitHub ili poluchit napryamuyu.")
pdf.body("Pologit vse tri faylya v odnu papku:")
pdf.code("pentest_gui.py\npentest_core.py\nexploit_engine.py")

pdf.subsection("Shag 3 - Ustanovit zavisimosti")
pdf.body("Otkryt cmd / PowerShell v papke s faylami i vypolnit:")
pdf.code("pip install customtkinter requests httpx paramiko beautifulsoup4 lxml dnspython websocket-client")

pdf.subsection("Shag 4 - Zapusk")
pdf.code("python pentest_gui.py")

pdf.subsection("Vozmozhnye oshibki:")
pdf.body("- 'pip ne yavlyaetsya komandoy' -> python -m pip install ...")
pdf.body("- 'python ne nayden' -> pereustanovit Python s galochkoy Add to PATH")
pdf.body("- 'ModuleNotFoundError' -> pip install nazvanie_modulya")

# --- Page 2: Scanning ---
pdf.add_page()
pdf.section("2. VKLADKA 'SKANIROVANIE'")
pdf.body("1. Vvedi URL tseli: http://localhost.tu\n2. Vyberi moduli v Nastroykakh\n3. Nazhmi 'Zapustit skanirovanie'\n4. Vnizu vidno log v realnom vremeni\n5. Po zavershenii pokazhet: HIGH / MEDIUM / LOW nahodki")

pdf.section("3. VKLADKA 'NAHODKI'")
pdf.body("- Vse uyazvimosti otsortiriovany po kritichnosti\n- HIGH = krasnyy, MEDIUM = zheltyy, LOW = siniy")
pdf.body("- Filtr: vvedi slovo (napr. sqli ili xss)\n- Filtr po ugroze: VSE / HIGH / MEDIUM / LOW\n- Klik na stroku -> poyavyatsya podrobnosti")
pdf.body("PRAVYY KLIK na uyazvimost -> menju ataki:")
pdf.code("SQLi  -> Avto eksployt, Tablitsy, Versiya BD\nXSS   -> Cookie Stealer, Keylogger, Skaner portov\nLFI   -> Chtenie faylov, PHP ishodniki\nCMDi  -> Vypolnit komandu, Reverse Shell")
pdf.body("Knopki HTML / JSON / TXT - eksport otcheta")

pdf.section("4. VKLADKA 'ISTORIYA'")
pdf.body("- Vse HTTP zaprosy kotorye delala programma\n- Klik na zapros -> polnyy Request i Response\n- Zveta: zelenyy 2xx, siniy 3xx, krasnyy 4xx, oranzhevyy 5xx")

pdf.section("5. VKLADKA 'KODIROVSHCHIK'")
pdf.body("1. Vstavit tekst\n2. Vybrat tip: Base64, URL, HTML, Hex, MD5, SHA1, SHA256\n3. Nazhat Kodirovit ili Dekodirovit\n4. Skopirovat rezultat")

# --- Page 3: Exploit ---
pdf.add_page()
pdf.section("6. VKLADKA 'EKSPLOYT'")

pdf.subsection("SQLi Eksployt")
pdf.body("1. Vvedi URL uyazvimoy stranitsy\n2. Vvedi uyazvimyy parametr (napr. q)\n3. Vyberi metod GET ili POST")
pdf.body("Knopki:")
pdf.code("Avto eksployt  -> delaet vse avtomaticheski\nNayti stolbtsy -> opredelyaet kolichestvo stolbtsov\nVersiya BD     -> poluchaet versiyu MySQL\nPolzovatel/BD  -> tekushchiy polzovatel i baza\nTablitsy       -> spisok vsekh tablits\nStolbtsy       -> vvedi tablitsu -> poluchi stolbtsy\nDamp tablitsy  -> vvedi tablitsu i stolbtsy -> vygr uzi")

pdf.subsection("XSS Arsenal")
pdf.body("1. Vvedi URL servera zahvata gde pridut dannye\n2. Knopki generiruyut payloady:\n   - Cookie Stealer: kradet kuki zhertvy\n   - Keylogger: zapisyvaet nazhatiya klavish\n   - Skaner portov: skaniruet set cherez brauzer\n   - CSRF: otpravlyaet formu ot imeni zhertvy\n3. Skopiruy payload i vnedriy v uyazvimyy parametr")

pdf.subsection("LFI Chtenie")
pdf.body("1. Vvedi URL i parametr (napr. page)\n2. Knopki:")
pdf.code("/etc/passwd  -> spisok polzovateley sistemy\n.env         -> paroli BD i klyuchi\nPHP ishodnik -> chitat PHP fayly cherez php://filter\nLog Poisoning -> PHP shell v log -> komandyi")

pdf.subsection("CMDi Vypolnenie")
pdf.body("1. Vvedi URL i parametr\n2. V pole Komanda vvedi chto vypolnit\n3. Knopki: id/whoami, ls -la /, Reverse Shell")
pdf.body("Reverse Shell:")
pdf.code("1. Vvedi svoy IP i port\n2. Zapusti: nc -lvnp 4444\n3. Otpravit payload na server")

pdf.subsection("Adminer Brutfors")
pdf.body("1. Vvedi URL adminer.php\n2. Vvedi servery, polzovateley, paroli (kazhdyy s novoy stroki)\n3. Nazhat Zapustit -> vidish kazhdyu popytku\n4. Pri nahodke: [!!!] VALID: server=... user=... password=...")

pdf.subsection("Server zahvata")
pdf.body("1. Nazhat Zapustit -> HTTP server na portu 7777\n2. Skopiruy URL -> vstavit v XSS payload\n3. Kogda zhertva otkroet stranits u s XSS -> dannye pridut\n4. Nazhat Obnovit -> uvidit IP zhertvy, kuki, dannye form")

# --- Page 4: Business Logic ---
pdf.add_page()
pdf.section("7. VKLADKA 'BIZNES-LOGIKA'")

pdf.subsection("IDOR Skaner")
pdf.body("Proveryaet mozhno li poluchit chuzhie dannye menyaya ID:")
pdf.code("1. URL: http://localhost.tu/order?id=1\n2. Parametr: id\n3. Diapazon: ot 1 do 100\n4. Nazhat Skanirovat")
pdf.body("Programma sravnivaet otvety - esli razmer otlichaetsya -> vozmozhnyy IDOR")

pdf.subsection("Gonka zaprosov")
pdf.body("Proveryaet uyazvimost odnovremennykh zaprosov (Race Condition):")
pdf.code("1. Vvedi URL i parametr\n2. Kolichestvo potokov: 50-100\n3. Nazhat Zapustit gonku\n4. Esli otvety raznye -> vozmozhna uyazvimost")

pdf.subsection("Manipulyatsiya tsenoy")
pdf.body("Proveryaet korektnost obrabotki tsen:")
pdf.code("1. URL korziny / oplaty\n2. Parametr tseny (napr. price, amount)\n3. Knopki testiruyut: -1, 0, 99999999, abc\n4. Smotri otvet servera - prinyal li nekorrektnoye znachenie")

pdf.subsection("Tsepochki eksptoytov")
pdf.body("1. Snachala zapusti skanirovanie\n2. Nazhat Analizirovat nahodki\n3. Pokazhet gotovye tsepochki atak:")
pdf.code("SQLi -> damp paroley -> vzlom kheshey -> vkhod kak admin\nLFI + SQLi -> zapis shell -> vypolnenie komand\nXSS + admin panel -> ugon sessii admina\nCMDi -> reverse shell -> polnyy dostup")

pdf.section("8. VKLADKA 'NASTROYKI'")
pdf.body("Vklyuchi/vyklyuchi moduli skanirovaniya:")
pdf.code("Zagolovki  - proverka security headers\nPuti       - poisk skrytykh faylov\nXSS        - mezhsaytovyy skripting\nSQLi       - SQL in ektsii\nLFI        - vklyuchenie lokalnykh faylov\nSSTI       - in ektsii v shablony\nCMDi       - vypolnenie komand\nBlind SQLi - medlennaya no glubokaya proverka")
pdf.body("Kolichestvo potokov: bolshe = bystree, no zametno dlya servera")

pdf.section("VAZHNOE PRIMECHANIE")
pdf.body("Programma prednaznachena TOLKO dlya testirovaniya SOBSTVENNOGO servera.\nIspolzovanie protiv chuzhikh saytov nezakonne.")

pdf.output("/home/user/tether-usdt-trc20/nexus_pentest_instrukciya.pdf")
print("PDF sozdan!")
