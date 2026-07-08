; Inno Setup — установщик SteadyVoice (SteadyControl) для Windows 10/11
; ВАЖНО: AppName — только ВИДИМОЕ имя. Внутренние контракты (AppId, папка
; установки, имя exe, имя файла установщика) зафиксированы и НЕ меняются —
; иначе сломаются автообновления у установленных копий.
#define AppName "SteadyVoice"
#define AppVersion "1.5.15"
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
; Установка в пользовательскую папку — БЕЗ прав администратора и БЕЗ UAC.
; Это делает авто-обновление тихим и убирает окна безопасности при обновлении.
PrivilegesRequired=lowest
; КОНТРАКТ: папка установки прежняя (SteadyTranscribe) — обновления поверх работают
DefaultDirName={localappdata}\Programs\SteadyTranscribe
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
; Для тихого авто-обновления: закрыть работающее приложение и не спрашивать
CloseApplications=yes
CloseApplicationsFilter=SteadyTranscribe.exe
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

; ЗАДЕЛ НА БУДУЩЕЕ: перед установкой сносим старый код приложения (_internal, exe).
; Иначе от версии к версии копятся устаревшие библиотеки/файлы, и однажды обновление
; «поверх» ломается так, что пользователю приходится переустанавливать вручную.
; {app}\models НЕ трогаем — там может лежать вшитая модель (установка «с моделью»).
[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\SteadyTranscribe.exe"
; ребрендинг SteadyTranscribe → SteadyVoice: убираем СТАРЫЕ ярлыки, чтобы не дублировались
Type: files; Name: "{autodesktop}\SteadyTranscribe.lnk"
Type: filesandordirs; Name: "{autoprograms}\SteadyTranscribe"

[Files]
Source: "..\dist\SteadyTranscribe\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
; отдельный файл иконки для ярлыков: новый путь = свежая иконка МИМО кэша Windows
Source: "..\assets\icon.ico"; DestDir: "{app}"; DestName: "steadyvoice.ico"; Flags: ignoreversion
#ifdef WITHMODEL
Source: "..\model-bundle\*"; DestDir: "{app}\models"; Flags: recursesubdirs ignoreversion
#endif

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\SteadyTranscribe.exe"; IconFilename: "{app}\steadyvoice.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\SteadyTranscribe.exe"; Tasks: desktopicon; IconFilename: "{app}\steadyvoice.ico"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Run]
; Обновить кэш иконок Windows — чтобы новая иконка появилась сразу, без перезагрузки
Filename: "{sys}\ie4uinit.exe"; Parameters: "-show"; Flags: runhidden nowait skipifdoesntexist
; Обычная установка: галочка «Запустить» в конце мастера.
Filename: "{app}\SteadyTranscribe.exe"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent
; Тихое авто-обновление (/VERYSILENT): перезапускаем приложение, КРОМЕ установки
; при выходе (/NORELAUNCH) — пользователь закрыл программу, не открываем её снова.
Filename: "{app}\SteadyTranscribe.exe"; Flags: nowait runasoriginaluser; Check: ShouldRelaunch

; При удалении сносим ВСЮ папку приложения (в т.ч. файлы, созданные во время работы —
; кэш Python и пр., которые иначе не давали удалить папку) и настройки/логи.
[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: files; Name: "{userappdata}\SteadyTranscribe\settings.json"
Type: files; Name: "{userappdata}\SteadyTranscribe\log.txt"
Type: files; Name: "{userappdata}\SteadyTranscribe\crash.txt"

[Code]
// Есть ли параметр в командной строке установщика (регистр не важен)
function CmdLineParamExists(const Value: string): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), Value) = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

// Перезапускать приложение после тихого обновления?
// Да — при обновлении на простое/при запуске. Нет (/NORELAUNCH) — при выходе:
// пользователь закрыл программу, не открываем её заново.
function ShouldRelaunch: Boolean;
begin
  Result := WizardSilent and not CmdLineParamExists('/NORELAUNCH');
end;

// Перед удалением: закрыть запущенное приложение (чтобы файлы не были заняты)
// и предложить удалить данные (модели, история) — по желанию пользователя.
procedure CurUninstallStepChanged(CurStep: TUninstallStep);
var
  DataDir: String;
  ResultCode: Integer;
begin
  if CurStep = usUninstall then
  begin
    // жёстко завершаем все процессы приложения
    Exec('taskkill.exe', '/F /IM SteadyTranscribe.exe /T', '',
         SW_HIDE, ewWaitUntilTerminated, ResultCode);
    DataDir := ExpandConstant('{userappdata}\SteadyTranscribe');
    if DirExists(DataDir) then
    begin
      if MsgBox('Удалить также скачанные модели, историю расшифровок и настройки?' + #13#10 +
                'Да — удалить всё полностью. Нет — оставить модели и историю на диске.',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
