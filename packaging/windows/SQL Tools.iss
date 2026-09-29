#define AppName "SQL Tools"
#define AppExeName "SQL Tools.exe"

#ifndef AppVersion
  #error "Build this installer through build.py so its version is supplied."
#endif
#ifndef AppSource
  #error "Build this installer through build.py so its application path is supplied."
#endif

[Setup]
AppId={{1A6C0A9D-5E26-4C0A-96CB-8A3D5A642AD2}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=SQL Tools Project
DefaultDirName={autopf}\SQL Tools
DefaultGroupName=SQL Tools
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
OutputBaseFilename=SQL Tools Setup {#AppVersion} Windows x64
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=..\..\assets\icon.ico
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\SQL Tools"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\SQL Tools"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch SQL Tools"; Flags: postinstall nowait skipifsilent
