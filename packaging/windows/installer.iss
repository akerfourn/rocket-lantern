#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef BundleDirectory
  #error BundleDirectory is required
#endif
#ifndef OutputDirectory
  #error OutputDirectory is required
#endif

[Setup]
AppId={{A920938C-B23E-46F6-8243-6D0144CD31EB}
AppName=RocketLantern
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\RocketLantern
DefaultGroupName=RocketLantern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDirectory}
OutputBaseFilename=RocketLantern-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\..\src\rocket_lantern\assets\rocket-lantern.ico
UninstallDisplayIcon={app}\RocketLantern.exe
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le bureau"; Flags: unchecked

[Files]
Source: "{#BundleDirectory}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\RocketLantern"; Filename: "{app}\RocketLantern.exe"
Name: "{autodesktop}\RocketLantern"; Filename: "{app}\RocketLantern.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RocketLantern.exe"; Description: "Lancer RocketLantern"; Flags: nowait postinstall skipifsilent
