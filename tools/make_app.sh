#!/usr/bin/env bash
# Make a double-clickable Mac app with the Go2 icon that opens the panel (no Terminal window).
#   bash tools/make_app.sh               -> ~/Desktop/Go2 Control Panel.app
#   bash tools/make_app.sh /Applications
# Run  bash setup.sh  first. What the panel prints goes to ~/Library/Logs/Go2ControlPanel.log.
# If this folder is inside Desktop, Documents or Downloads, macOS asks once to let the app use that folder.
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$HOME/Desktop}"
APP="$DEST/Go2 Control Panel.app"
[ -x "$HERE/.venv/bin/python" ] || { echo "Run  bash setup.sh  first."; exit 1; }

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# icon: all the sizes macOS wants, packed into one .icns
SET="$(mktemp -d)/AppIcon.iconset"
mkdir -p "$SET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$HERE/tools/panel_icon.png" --out "$SET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s * 2)) $((s * 2)) "$HERE/tools/panel_icon.png" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Go2 Control Panel</string>
  <key>CFBundleDisplayName</key><string>Go2 Control Panel</string>
  <key>CFBundleIdentifier</key><string>local.go2-control-panel</string>
  <key>CFBundleExecutable</key><string>launcher</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSLocalNetworkUsageDescription</key>
  <string>Talks to the Unitree Go2 over the Ethernet cable or its Wi-Fi.</string>
</dict>
</plist>
EOF

cat > "$APP/Contents/MacOS/launcher" <<EOF
#!/bin/bash
# Opens the Go2 Control Panel (made by tools/make_app.sh).
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LANG=en_US.UTF-8 PYTHONIOENCODING=utf-8
cd "$HERE" || exit 1
exec "$HERE/.venv/bin/python" control_panel.py >> "\$HOME/Library/Logs/Go2ControlPanel.log" 2>&1
EOF
chmod +x "$APP/Contents/MacOS/launcher"

codesign --force --deep -s - "$APP" 2>/dev/null || true   # local signature, so macOS remembers its permissions
touch "$APP"
echo "made $APP"
