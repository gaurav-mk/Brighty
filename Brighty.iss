; -- Brighty.iss --
; Inno Setup script for Project Brighty

[Setup]
AppName=Project Brighty
AppVersion=1.0
DefaultDirName={pf}\Project Brighty
DefaultGroupName=Project Brighty
UninstallDisplayIcon={app}\Brighty.exe
Compression=lzma2
SolidCompression=yes
OutputDir=userdocs:Project Brighty\installer
OutputBaseFilename=BrightySetup
SetupIconFile=ui\icon.ico

[Files]
Source: "dist\Brighty.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Project Brighty"; Filename: "{app}\Brighty.exe"
Name: "{commondesktop}\Project Brighty"; Filename: "{app}\Brighty.exe"

[Run]
Filename: "{app}\Brighty.exe"; Description: "Launch Project Brighty"; Flags: nowait postinstall skipifsilent
