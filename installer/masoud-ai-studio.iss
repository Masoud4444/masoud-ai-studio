#define MyAppName "Masoud AI Studio"
#define MyAppVersion "0.3.0"
#define MyAppPublisher "Masoud AI Studio"
#define MyAppExeName "MasoudAIStudio.exe"

[Setup]
AppId={{6C19A821-82A4-4D7D-9C4E-0B0D0E67A241}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Masoud AI Studio
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=output
OutputBaseFilename=Masoud-AI-Studio-Setup-{#MyAppVersion}-x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\MasoudAIStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Masoud AI Studio"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Masoud AI Studio"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Masoud AI Studio"; Flags: postinstall nowait skipifsilent
