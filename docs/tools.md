# Installation, launch, packaging, and rollback

Tools accept an explicit game directory, with no developer-specific paths or fixed offsets. Run commands from the repository root. Install the SDK separately, close the game before file changes, and back up saves.

## Installer

Requires Python 3.11+. Folder deployment is the format used in multiplayer tests.

```powershell
python SDKMod/tools/install.py --game-dir "E:\Games\Borderlands 2" --enable
python SDKMod/tools/install.py --game-dir "E:\Games\Borderlands 2" --enable --apply
```

Without --apply, installation and rollback are read-only. Without --enable, installation preserves existing enable settings; a new mod must be enabled in Mods. Only four source/license files and optionally sdk_mods/settings/unlimited_coop.json are changed.

Backups default to <game>/unlimited-coop-backups/<timestamp>/, with verified SHA256 and a manifest. --backup-dir selects a new directory. No-op installation creates no backup. Do not store backups under sdk_mods.

The core EXE/Engine/WillowGame hashes must match the tested CL2863302 installation unless --allow-untested-build is explicitly supplied. That override does not establish support. Remove existing unlimited_coop*.sdkmod packages before folder installation. SDK component presence is checked, not its version or authenticity.

Use the exact printed backup directory:

```powershell
python SDKMod/tools/install.py --game-dir "E:\Games\Borderlands 2" --rollback "E:\Games\Borderlands 2\unlimited-coop-backups\YOUR-TIMESTAMP"
python SDKMod/tools/install.py --game-dir "E:\Games\Borderlands 2" --rollback "E:\Games\Borderlands 2\unlimited-coop-backups\YOUR-TIMESTAMP" --apply
```

Rollback checks all current/backup hashes before writes, refuses files modified since installation, restores previous owned files, and removes new owned files. It does not restore saves or SDK dependencies. Keep backups until no longer needed. An interrupted deployment may require manual recovery after inspecting actual files and the manifest; rollback is not a general game repair tool.

## Windows launcher

Requires Windows PowerShell 5.1+ or PowerShell 7.

```powershell
& .\SDKMod\tools\Start-Game.ps1 -GameDirectory "E:\Games\Borderlands 2"
& .\SDKMod\tools\Start-Game.ps1 -GameDirectory "E:\Games\Borderlands 2" -Launch
```

The first command prints a plan. The second starts fullscreen at the configured resolution and exits immediately, without polling or background helpers. Steam must be running and the mod enabled. For a desktop shortcut, target your installed powershell.exe or pwsh.exe with -NoProfile -File "<repository>\SDKMod\tools\Start-Game.ps1" -GameDirectory "<game>" -Launch. Do not lower execution policy globally; normal Steam launch is also supported when installed there.

- -Language rus: use an installed three-letter language code; otherwise preserve normal language selection.
- -Diagnostic -LogDirectory "E:\Test Logs": add -log and a unique quoted -ABSLOG path. Default log directory: <game>/unlimited-coop-logs.
- -AllowUntestedBuild: explicitly accept an untested EXE hash, without claiming compatibility.

Normal launch has no -log, -ABSLOG, -windowed, or forced resolution. Internal game/SDK logs can still be written. The launcher refuses a second Borderlands 2 instance.

## Package

```powershell
python SDKMod/tools/build_package.py
```

SDKMod/dist contains a reproducible unlimited_coop.sdkmod and a checksum manifest, ignored by Git. Only source/license files are included. The SDK imports a .sdkmod only if its single root folder has the archive's name, so the version is not in the file name: it is read from pyproject.toml into the manifest. Copy only the archive into <game>/sdk_mods without renaming it, and remove the folder installation first; the installer refuses to install the folder next to an unlimited_coop*.sdkmod. The archive alone was loaded in-game with 1.4.0; multiplayer tests used the folder.
