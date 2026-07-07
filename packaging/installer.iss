; Inno Setup — установщик SteadyTranscribe для Windows 10/11
#define AppName "SteadyTranscribe"
#define AppVersion "1.4.0"
#define AppPublisher "Oleg Korkin (SteadyControl automation)"
#define AppURL "https://steadycontrol.com"

[Setup]
AppId={{7E6B4A2D-9C31-4F5E-8D2A-4C7F1B9E3A60}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppContact={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
#ifdef WITHMODEL
OutputBaseFilename=SteadyTranscribe-Setup-{#AppVersion}-with-model
#else
OutputBaseFilename=SteadyTranscribe-Setup-{#AppVersion}
#endif
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\SteadyTranscribe.exe

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "..\dist\SteadyTranscribe\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
#ifdef WITHMODEL
Source: "..\model-bundle\*"; DestDir: "{app}\models"; Flags: recursesubdirs ignoreversion
#endif

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\SteadyTranscribe.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\SteadyTranscribe.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Run]
Filename: "{app}\SteadyTranscribe.exe"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

; При удалении чистим настройки и логи (модели НЕ трогаем — чтобы не качать заново).
; Это устраняет проблему: битые старые настройки переживали переустановку.
[UninstallDelete]
Type: files; Name: "{userappdata}\SteadyTranscribe\settings.json"
Type: files; Name: "{userappdata}\SteadyTranscribe\log.txt"
Type: files; Name: "{userappdata}\SteadyTranscribe\crash.txt"
