; Inno Setup — установщик SteadyTranscribe для Windows 10/11
#define AppName "SteadyTranscribe"
#define AppVersion "1.0.0"
#define AppPublisher "SteadyControl"

[Setup]
AppId={{7E6B4A2D-9C31-4F5E-8D2A-4C7F1B9E3A60}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputBaseFilename=SteadyTranscribe-Setup-{#AppVersion}
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

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\SteadyTranscribe.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\SteadyTranscribe.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Run]
Filename: "{app}\SteadyTranscribe.exe"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent
