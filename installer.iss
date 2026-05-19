; Inno Setup Script — CRM Исламская рассрочка (Мурабаха)
; Требует: Inno Setup 6+ — https://jrsoftware.org/isinfo.php
; Запуск: iscc installer.iss  (или через build_installer.py)

#define AppName    "CRM Исламская рассрочка"
#define AppVersion "1.0"
#define AppExe     "CRM_Murabaha.exe"
#define AppFolder  "dist\CRM_Murabaha"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Мурабаха CRM
DefaultDirName={autopf}\CRM_Murabaha
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=dist\installer
OutputBaseFilename=CRM_Murabaha_Setup
SetupIconFile=
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
; Данные пользователя — в %LOCALAPPDATA%\CRM_Murabaha (авто, см. gui_run.py)
; Установщик только размещает файлы программы.

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon";    Description: "Ярлык на рабочем столе"; GroupDescription: "Дополнительно:"; Flags: checkedonce
Name: "startmenuicon";  Description: "Ярлык в меню Пуск";     GroupDescription: "Дополнительно:"; Flags: checkedonce

[Files]
; Все файлы из папочной сборки PyInstaller
Source: "{#AppFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#AppName}";               Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{group}\{#AppName}";                     Filename: "{app}\{#AppExe}"; Tasks: startmenuicon
Name: "{group}\Удалить {#AppName}";             Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Удаляем только файлы программы; данные пользователя в %LOCALAPPDATA% НЕ трогаем
Type: filesandordirs; Name: "{app}"

[Code]
// Проверка наличия Microsoft Edge WebView2 Runtime (нужен для pywebview)
function IsWebView2Installed(): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(
    HKLM,
    'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', Version
  ) and (Version <> '0.0.0.0') and (Version <> '');
  if not Result then
    Result := RegQueryStringValue(
      HKCU,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', Version
    ) and (Version <> '0.0.0.0') and (Version <> '');
end;

procedure InitializeWizard();
begin
  if not IsWebView2Installed() then
    MsgBox(
      'Внимание: Microsoft Edge WebView2 не найден.' + #13#10 +
      'Приложение требует его для работы.' + #13#10#13#10 +
      'На Windows 10/11 он обычно установлен автоматически.' + #13#10 +
      'Если приложение не запускается — скачайте WebView2 с сайта Microsoft.',
      mbInformation, MB_OK
    );
end;
