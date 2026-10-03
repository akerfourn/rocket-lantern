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
AppName=RL Win/Loss
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\RLWinLoss
DefaultGroupName=RL Win Loss
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDirectory}
OutputBaseFilename=RLWinLoss-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\RLWinLoss.exe
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
Name: "{group}\RL Win Loss"; Filename: "{app}\RLWinLoss.exe"
Name: "{autodesktop}\RL Win Loss"; Filename: "{app}\RLWinLoss.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RLWinLoss.exe"; Description: "Lancer RL Win/Loss"; Flags: nowait postinstall skipifsilent
