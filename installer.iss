; HMZ Video Studio Pro — Inno Setup Installer Script
; Non-admin installation (PrivilegesRequired=lowest), Bilingual Arabic/English, Optional Desktop Shortcut

#define MyAppName "HMZ Video Studio Pro"
; Keep in sync with APP_VERSION in video_studio_i18n.py (or pass /DMyAppVersion=1.2.3 to ISCC)
#ifndef MyAppVersion
#define MyAppVersion "1.0.2"
#endif
#define MyAppPublisher "HMZ-Bytes"
#define MyAppURL "https://hmzbytes.gumroad.com"
#define MyAppExeName "HMZVideoStudioPro.exe"

[Setup]
AppId={{8F4C92B1-7D3A-4E19-9A61-3E92C48D5B10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer_output
OutputBaseFilename=HMZVideoStudioPro_Setup_v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
#if FileExists(CompilerPath + "Languages\Arabic.isl")
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
#elif FileExists(CompilerPath + "Languages\Unofficial\Arabic.isl")
Name: "arabic"; MessagesFile: "compiler:Languages\Unofficial\Arabic.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\HMZVideoStudioPro.exe"; DestDir: "{app}"; Flags: ignoreversion
; Optional signed manifest (only exists when tools\keys\manifest.key was used). Never ship tools\, tests\ or keys.
Source: "dist\integrity.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--remove-integrations"; Flags: runhidden

[UninstallDelete]
; Only the self-extraction cache of the single-file EXE. User data (settings, license, projects) is kept on purpose.
Type: filesandordirs; Name: "{localappdata}\HMZ-Bytes\VideoStudioPro"
